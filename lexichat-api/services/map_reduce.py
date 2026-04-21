import os
import re
import json
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from groq import AsyncGroq, RateLimitError

async_groq_client = None

def get_async_groq_client():
    global async_groq_client
    if async_groq_client is None:
        async_groq_client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
    return async_groq_client

CLAUSE_PATTERN = re.compile(
    r'(?:^|\n)(?='
    r'\d+\.\d+|'          # 12.1  / 1.2.3
    r'\d+\.|'             # 1.
    r'\([a-zA-Z]\)|'      # (a)
    r'WHEREAS|'           # WHEREAS
    r'NOW,?\s+THEREFORE|' # NOW THEREFORE
    r'SCHEDULE|'          # SCHEDULE
    r'ANNEXURE|'
    r'[A-Z]{4,}\s*:)'     # ALL CAPS HEADING:
)

def batch_document(text: str, target_batch_size: int = 20000) -> list[str]:
    raw_splits = CLAUSE_PATTERN.split(text)
    splits = [s.strip() for s in raw_splits if s and s.strip()]
    if not splits:
        splits = [text]

    batches = []
    current_batch = ""

    for split in splits:
        if len(current_batch) + len(split) <= target_batch_size:
            current_batch += ("\n\n" if current_batch else "") + split
        else:
            if current_batch:
                batches.append(current_batch)
                current_batch = ""
            
            if len(split) > target_batch_size:
                sentences = re.split(r'(?<=[.!?])\s+', split)
                for sentence in sentences:
                    if len(current_batch) + len(sentence) <= target_batch_size:
                        current_batch += (" " if current_batch else "") + sentence
                    else:
                        if current_batch:
                            batches.append(current_batch)
                        current_batch = sentence
            else:
                current_batch = split

    if current_batch:
        batches.append(current_batch)

    return batches

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RateLimitError),
    reraise=True
)
async def map_phase(batch_text: str, instruction: str) -> dict:
    client = get_async_groq_client()
    prompt = f"""You are an analytical module performing a MAP phase extraction on a segment of a larger legal document.

INSTRUCTION:
{instruction}

DOCUMENT SEGMENT:
{batch_text}

Extract only the relevant facts or provisions. If nothing is relevant to the instruction, return an empty object {{}}.
Output ONLY valid JSON. Do not include markdown fences like ```json."""

    response = await client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0.0,
        max_tokens=2000
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
    
    try:
        return json.loads(raw)
    except Exception:
        return {"raw_unparsed": raw}

async def reduce_phase(map_results: list[dict], instruction: str) -> dict:
    client = get_async_groq_client()
    aggregated_json = json.dumps(map_results, indent=2)
    # Ensure it fits within massive context bounds safely
    aggregated_json = aggregated_json[:80000] 
    
    prompt = f"""You are an analytical module performing the final REDUCE phase synthesis for a legal document.

INSTRUCTION:
{instruction}

CRITICAL REQUIREMENT:
You MUST EXPLICITLY flag any sections where content was thin, ambiguous, or uncertain. Do NOT paper over gaps with confident-sounding language.

AGGREGATED MAP PHASE RESULTS:
{aggregated_json}

Synthesize these findings into the final requested structured JSON output.
Output ONLY valid JSON. Do not include markdown fences like ```json."""

    response = await client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0.0,
        max_tokens=4000
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
    
    try:
        return json.loads(raw)
    except Exception as e:
        return {"error": "Failed to parse synthesized JSON", "raw": raw}

async def run_map_reduce_stream(full_text: str, map_instruction: str, reduce_instruction: str):
    """
    Async generator that yields SSE events detailing map-reduce progress.
    """
    batches = batch_document(full_text)
    total_batches = len(batches)
    map_results = []
    
    for i, batch in enumerate(batches):
        batch_num = i + 1
        yield f"data: {json.dumps({'status': 'processing', 'message': f'Analysing section {batch_num} of {total_batches}...'})}\n\n"
        
        res = await map_phase(batch, map_instruction)
        map_results.append(res)
        
        await asyncio.sleep(0.5)

    yield f"data: {json.dumps({'status': 'processing', 'message': 'Synthesizing final document...'})}\n\n"
    
    final_result = await reduce_phase(map_results, reduce_instruction)
    
    yield f"data: {json.dumps({'status': 'complete', 'data': final_result})}\n\n"

async def run_feature_gated_pipeline(full_text: str, map_instruction: str, reduce_instruction: str, legacy_func):
    """
    Reads USE_MAP_REDUCE. If true runs map_reduce_stream. 
    If false yields a legacy SSE with data generated by legacy_func().
    """
    use_map_reduce = os.environ.get("USE_MAP_REDUCE", "False").lower() in ("true", "1", "yes")
    
    if use_map_reduce:
        print("[FEATURE FLAG] Executing Map-Reduce Pipeline")
        async for chunk in run_map_reduce_stream(full_text, map_instruction, reduce_instruction):
            yield chunk
    else:
        yield f"data: {json.dumps({'status': 'processing', 'message': 'Analysing document (Legacy Mode)...'})}\n\n"
        try:
            # Execute the legacy sync/async logic
            if asyncio.iscoroutinefunction(legacy_func):
                result = await legacy_func()
            else:
                result = legacy_func()
            yield f"data: {json.dumps({'status': 'complete', 'data': result})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

