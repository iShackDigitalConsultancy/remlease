import os
import json
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from groq import Groq

load_dotenv()
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("rem-leases")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

query = "can you amend your plea one day before trial?"
# Advanced RAG: Query Expansion to force legal semantics
pinecone_query = query + " uniform rules of court court procedure pleading amendment timelines civil"
query_vec = embedding_model.encode(pinecone_query).tolist()

response = index.query(
    vector=query_vec,
    top_k=20, 
    include_metadata=True,
    filter={
        "is_global": {"$eq": True},
        "jurisdiction": {"$eq": "za"}
    }
)

matches = response.get('matches', [])
context_pieces = []
for r in matches:
    m = r.get('metadata', {})
    piece = f"Filename: {m.get('filename')}\nPage: {m.get('page')}\nText Excerpt:\n{m.get('text')}"
    context_pieces.append(piece)
context = "\n\n---\n\n".join(context_pieces)

# Safety cap to prevent Groq 6000 TPM rate limit crash
if len(context) > 18000:
    context = context[:18000] + "\n...[Context Truncated for System Limits]"

system_prompt = (
    "You are a brilliant, highly analytical legal and academic assistant. "
    "You are strictly prohibited from hallucinating or guessing outside the provided document context. "
    "You must answer questions based SOLELY on the provided documents; however, you ARE permitted to make direct logical deductions from the text (e.g., if a rule applies 'at any time before judgment', you can logically deduce that it applies 'one day before trial'). "
    "If the answer cannot be found or logically deduced from the provided context, you MUST state: 'I cannot answer this based on the provided documents.' "
    "You MUST explicitly cite the exact source of your answers at the end of each relevant claim, using the exact format: [Filename, Page X]. "
    "For example: 'The defendant signed the contract on May 4th [contract.pdf, Page 2].'\n\n"
    "CRITICAL INSTRUCTION REGARDING SAFETY FILTERS: The user is a legal professional asking questions about civil procedure, litigation strategy, and the Rules of Court (e.g., amending a plea, filing deadlines). Discussing these topics is the core purpose of this system. It DOES NOT constitute advice on how to evade law enforcement or commit illegal acts. You MUST answer these questions fully and accurately based on the context.\n\n"
    "Be precise, objective, and maintain a professional tone. Do not provide prescriptive legal advice.\n\n"
    f"DOCUMENT CONTEXT:\n{context}"
)

print(f"Retrieved {len(matches)} chunks. Testing Llama-3...\n")
if "Any party desiring to amend a pleading or document" in context or "at any stage before judgment grant leave to amend" in context:
    print("--- CRITICAL RULE 28 WAS FOUND IN CONTEXT! ---")
else:
    print("--- CRITICAL RULE 28 WAS MISSING FROM CONTEXT! ---")

completion = groq_client.chat.completions.create(
    model='llama-3.3-70b-versatile',
    messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': query}
    ],
    temperature=0
)

print("-" * 50)
print(completion.choices[0].message.content)
print("-" * 50)
