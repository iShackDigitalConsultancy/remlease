from config.model_versions import PRODUCTION_PINECONE_NAMESPACE
from config.model_versions import VOYAGE_EMBEDDING_MODEL
from config.model_versions import GROQ_EXTRACTION_MODEL
import os
import json
import re
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from dependencies import safe_query, UPLOAD_DIR, groq_client, index, vo
import models
from sqlalchemy.orm import Session
from fastapi import Depends, Header
from typing import List, Optional
from services.map_reduce import run_feature_gated_pipeline
from auth import get_current_user_optional
from database import get_db

def harvest_annexure_orphans(text: str) -> str:
    import re
    try:
        if "ANNEXURE A" not in text or "FINANCIAL AND OTHER TERMS" not in text:
            return text
            
        lines = text.split("\n")
        
        target_idx = -1
        for i, line in enumerate(lines):
            if "FINANCIAL AND OTHER TERMS" in line:
                target_idx = i
                
        if target_idx == -1:
            return text
            
        last_item_idx = target_idx
        for i in range(target_idx, min(target_idx + 150, len(lines))):
            if "ANNEXURE B" in lines[i] or "SURETYSHIP" in lines[i]:
                break
            if re.match(r'^\d+\.\s*$', lines[i].strip()) or re.match(r'^\d+\.', lines[i].strip()):
                last_item_idx = i
                
        scan_start = last_item_idx
        scan_end = min(last_item_idx + 80, len(lines))
        
        dates = []
        address_fragments = []
        
        month_pattern = r'^\s*\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*$'
        
        first_date_idx = -1
        
        for i in range(scan_start, scan_end):
            line = lines[i]
            
            if re.match(month_pattern, line, re.IGNORECASE):
                if i + 1 < len(lines):
                    next_line = lines[i+1]
                    if re.match(r'^\s*\d{2}\s*$', next_line):
                        if first_date_idx == -1:
                            first_date_idx = i
                        day_month = line.strip()
                        year_frag = next_line.strip()
                        dates.append(f"{day_month} 20{year_frag}")
                        
            line_str = line.strip()
            if not line_str:
                continue
                
            if re.search(r'Shop\s*\d+', line_str, re.IGNORECASE) or \
               re.match(r'^\s*\d+\s+\w+.*(?:Avenue|Road|Street|Drive)', line_str, re.IGNORECASE):
                if line_str not in address_fragments:
                    address_fragments.append(line_str)
                    
        if first_date_idx != -1 and first_date_idx > scan_start:
            prev_line = lines[first_date_idx - 1].strip()
            if prev_line and not re.match(r'^\d+$', prev_line) and prev_line not in address_fragments:
                address_fragments.insert(0, prev_line)
                
        if not dates and not address_fragments:
            return text
            
        date_1 = dates[0] if len(dates) > 0 else "Not found"
        date_2 = dates[1] if len(dates) > 1 else "Not found"
        address_str = ", ".join(address_fragments) if address_fragments else "Not found"
        
        injection = (
            "\n\n--- ANNEXURE A FILLED FIELDS (HARVESTED) ---\n"
            f"Commencement Date (Item 7): {date_1}\n"
            f"Opening Date (Item 8): {date_2}\n"
            f"Premises Address: {address_str}\n"
            "--- END HARVESTED FIELDS ---\n"
        )
        
        lines.insert(target_idx + 1, injection)
        return "\n".join(lines)
    except Exception:
        return text

def merge_verified_edits(cache_data: dict, verified_edits: dict, report_type: str) -> dict:
    import copy
    merged = copy.deepcopy(cache_data)

    if report_type == "expiries":
        edits = verified_edits.get("edits", {})
        for expiry in merged.get("expiries", []):
            doc_name = expiry.get("document", "")
            if doc_name in edits:
                for field, value in edits[doc_name].items():
                    expiry[field] = value
                # Mark this entry as verified
                expiry["_verified"] = True

    elif report_type == "timeline":
        edits = verified_edits.get("edits", {})
        ft = merged.get("fundamental_terms", {})
        for field, value in edits.items():
            keys = field.split(".")
            target = ft
            for key in keys[:-1]:
                target = target.get(key, {})
            if isinstance(target, dict):
                target[keys[-1]] = value

    return merged

async def cached_pipeline_stream(
    cache_path: str,
    force_refresh: bool,
    pipeline_gen,
    workspace_id: str = None
):
    def apply_overrides(data):
        if not workspace_id:
            return data
        from dependencies import UPLOAD_DIR
        override_path = os.path.join(
            UPLOAD_DIR,
            f"{workspace_id}_overrides.json")
        if not os.path.exists(override_path):
            return data
        try:
            with open(override_path) as f:
                overrides = json.load(f)
            expiries = data.get("expiries", [])
            for exp in expiries:
                doc_id = (
                    exp.get("pinecone_doc_id")
                    or exp.get("document_id")
                )
                if doc_id and \
                   doc_id in overrides:
                    doc_ov = overrides[doc_id]
                    field_map = {
                        "commencement_date":
                            "raw_commencement_date",
                        "expiry_date":
                            "expiry_date",
                        "renewal_type":
                            "renewal_type",
                        "notice_min_months":
                            "notice_min_months",
                        "notice_max_months":
                            "notice_max_months",
                        "renewal_deadline":
                            "renewal_deadline",
                    }
                    for field, ov in \
                        doc_ov.items():
                        cf = field_map.get(
                            field, field)
                        exp[cf] = ov["value"]
                        exp[f"{cf}_source"] = \
                            "manual_user_verified"
                    # Set commencement_source
                    if "commencement_date" \
                       in doc_ov:
                        exp["commencement_source"]\
                            = "manual_user_verified"
                        exp["commencement_date"]\
                            = doc_ov[
                            "commencement_date"
                            ]["value"]
        except Exception as e:
            print(f"Override apply: {e}")
        return data

    if not force_refresh and \
       os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached = json.load(f)
        # Apply overrides to cached data
        cached = apply_overrides(cached)
        
        # Overlay verified edits if they exist
        endpoint_name = "expiries" if "extract_expiries" in cache_path else "timeline"
        if endpoint_name == "expiries":
            verified_path = cache_path.replace("extract_expiries.json", "verified_expiries.json")
        else:
            verified_path = cache_path.replace("fundamental_terms.json", "verified_timeline.json")
            
        if os.path.exists(verified_path):
            with open(verified_path, "r") as vf:
                verified = json.load(vf)
            cached = merge_verified_edits(
                cached, verified, endpoint_name)
                
        yield f"data: {json.dumps({'status': 'complete', 'data': cached})}\n\n"
        return

    async for chunk in pipeline_gen:
        # Apply overrides to fresh data too
        if chunk.startswith("data: "):
            try:
                obj = json.loads(chunk[6:])
                if obj.get("status") == "complete":
                    obj["data"] = apply_overrides(obj.get("data", {}))
                    yield f"data: {json.dumps(obj)}\n\n"
                    # Save updated cache
                    with open(cache_path, "w") as f:
                        json.dump(obj.get("data"), f)
                    continue
            except Exception:
                pass
        yield chunk


def get_embedding(text: str):
    return vo.embed([text], model=VOYAGE_EMBEDDING_MODEL).embeddings[0]

def analyze_document_brief(doc_id: str, filename: str, sample_text: str, cache_dir: str = None) -> dict:
    """Run a structured Groq extraction and return a JSON brief."""
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    prompt = (
        "You are a senior South African legal analyst. Analyse the following document extract, "
        "which may contain dirty OCR from a signed/scanned lease or contract. "
        "Read carefully through any garbled text to find the core entities.\n\n"
        "Respond with ONLY valid JSON — no markdown fences, no commentary.\n"
        "Return exactly this structure:\n"
        '{\n'
        '  "doc_type": "short document type e.g. Commercial Lease, Sale of Shares, NDA",\n'
        '  "parties": ["Party A Name", "Party B Name"],\n'
        '  "obligations": ["Key obligation 1", "Key obligation 2"],\n'
        '  "financial_terms": ["Rent/Payment amounts", "Deposits", "Escalations if any"],\n'
        '  "key_dates": [{"label": "Commencement/Effective Date", "value": "1 March 2024"}],\n'
        '  "execution_status": "Briefly state if signatures appear present or if it looks like an unsigned draft",\n'
        '  "summary": "Two-sentence plain English summary of the document."\n'
        '}\n\n'
        f"DOCUMENT: {filename}\n\nEXTRACT:\n{sample_text[:8000]}"
    )
    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_EXTRACTION_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
            max_tokens=800
        )
        raw = resp.choices[0].message.content.strip()
        # Strip accidental markdown fences
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)
    except Exception as e:
        print(f"Brief generation failed: {e}")
        return {
            "doc_type": "Legal Document", 
            "parties": [], 
            "obligations": [], 
            "financial_terms": [], 
            "key_dates": [], 
            "execution_status": "Unknown", 
            "summary": ""
        }


def analyze_document_brief_background(doc_id: str, filename: str, sample_text: str, cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    try:
        brief = analyze_document_brief(doc_id, filename, sample_text)
        with open(os.path.join(cache_dir, f"{doc_id}_brief.json"), "w") as f:
            json.dump(brief, f)
    except Exception as e:
        print(f"Background brief extraction failed: {e}")


def get_document_brief(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    if current_user:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
            models.Workspace.firm_id == current_user.firm_id
        ).first()
    else:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
            models.Workspace.session_id == x_session_id
        ).first()
        
    if not doc:
        raise HTTPException(status_code=403, detail="Access denied")
        
    file_path = os.path.join(cache_dir, f"{doc_id}_brief.json")
    if not os.path.exists(file_path):
        return {"brief": None}
        
    with open(file_path, "r") as f:
        brief = json.load(f)
    return {"brief": brief}


async def document_audit(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    # 1. Verify access to the document
    if current_user:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == payload.doc_id) | (models.WorkspaceDocument.id == payload.doc_id),
            models.Workspace.firm_id == current_user.firm_id
        ).first()
    else:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == payload.doc_id) | (models.WorkspaceDocument.id == payload.doc_id),
            models.Workspace.session_id == x_session_id
        ).first()
        
    if not doc:
        raise HTTPException(status_code=403, detail="Access denied for document audit")
        
    doc_text = None
    for candidate_id in [payload.doc_id, getattr(doc, "pinecone_doc_id", None), getattr(doc, "id", None)]:
        if not candidate_id: continue
        file_path = os.path.join(cache_dir, f"{candidate_id}.md")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    doc_text = f.read()
                break
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
                
    if not doc_text:
        raise HTTPException(status_code=404, detail="Underlying document markdown file not found")
    full_text = doc_text

    map_task = f"Extract all policy clauses, compliance obligations, and risk provisions from this section. Also extract: Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building., parties, and any compliance obligations per party."
    reduce_task = f"""Produce a structured audit report flagging all compliance risks and policy gaps against this strictly provided policy:
{payload.policy}

Deduplicate identical violations found across different sections.
Output ONLY valid JSON matching this exact array structure:
{{
  "document_context": {{
    "location": "Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building.",
    "parties": [
      {{"role": "Landlord/Lessor/Franchisor/etc", "name": "Full legal entity name"}}
    ],
    "obligations": [
      {{
        "party": "Party name",
        "category": "Financial | Operational | Maintenance | Compliance",
        "obligation": "Description of the obligation",
        "clause_reference": "e.g. 4.2.3 or Schedule 1"
      }}
    ]
  }},
  "audit": [
    {{
      "check": "Rule 1 from the policy",
      "status": "PASS", 
      "explanation": "Brief explanation of why it passed, quoting the text if possible.",
      "clause_reference": "e.g. 1.2"
    }},
    {{
      "check": "Rule 2 from the policy",
      "status": "FAIL", 
      "explanation": "Explanation of why it failed or is missing.",
      "clause_reference": "e.g. 1.2"
    }}
  ]
}}
Use "PASS", "FAIL", or "REVIEW" for the status. Output nothing but the JSON object."""

    def legacy_op():
        doc_text = str(full_text)[:18000]
        prompt = f"""You are a senior legal auditor reviewing a document against a strict Compliance Policy.
    
POLICY TO CHECK THE DOCUMENT AGAINST:
{payload.policy}

DOCUMENT TEXT:
{doc_text}

INSTRUCTIONS:
Evaluate the document strictly against the policy above. 
Output ONLY valid JSON matching this exact structure:
{{
  "document_context": {{
    "location": "Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building.",
    "parties": [
      {{"role": "Landlord/Lessor/Franchisor/etc", "name": "Full legal entity name"}}
    ],
    "obligations": [
      {{
        "party": "Party name",
        "category": "Financial | Operational | Maintenance | Compliance",
        "obligation": "Description of the obligation",
        "clause_reference": "e.g. 4.2.3 or Schedule 1"
      }}
    ]
  }},
  "audit": [
    {{
      "check": "Rule 1 from the policy",
      "status": "PASS", 
      "explanation": "Brief explanation of why it passed, quoting the text if possible.",
      "clause_reference": "e.g. 1.2"
    }},
    {{
      "check": "Rule 2 from the policy",
      "status": "FAIL", 
      "explanation": "Explanation of why it failed or is missing.",
      "clause_reference": "e.g. 1.2"
    }}
  ]
}}

Use "PASS", "FAIL", or "REVIEW" for the status. Output nothing but the JSON object."""
        resp = groq_client.chat.completions.create(
            model=GROQ_EXTRACTION_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=2000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    workspace_id = doc.workspace_id
    cache_path = os.path.join(cache_dir, f"{workspace_id}_audit.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op)), media_type="text/event-stream")


async def extract_timeline(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="No documents selected")
        
    full_text: str = ""
    workspace_id = None
    for doc_id in payload.doc_ids:
        # Verify access
        if current_user is not None:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
                models.Workspace.firm_id == current_user.firm_id
            ).first()
        else:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
                models.Workspace.session_id == x_session_id
            ).first()
            
        if not doc:
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        if workspace_id is None:
            workspace_id = str(doc.workspace_id)
            
        for candidate_id in [doc_id, getattr(doc, "pinecone_doc_id", None), getattr(doc, "id", None)]:
            if not candidate_id: continue
            file_path = os.path.join(cache_dir, f"{candidate_id}.md")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        doc_text = f.read()
                    doc_text = harvest_annexure_orphans(doc_text)
                    full_text += f"\n--- DOCUMENT START: {doc.filename} ---\n{doc_text}\n"
                    break
                except Exception as e:
                    print(f"Failed to read {file_path}: {e}")
                
    if not workspace_id:
        workspace_id = payload.doc_ids[0]

    if not full_text:
        raise HTTPException(status_code=404, detail="No text could be extracted from selected documents.")

    map_task = "Extract all fundamental lease terms from this section. Look for: party names and registration numbers, Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building., lease period, commencement date, expiry date, beneficial occupation date, rental amounts per period, escalation rate, permitted use, trading hours, security deposit, Extract banking/payment details including: bank name, branch name, branch code, account number, account type, and account holder name., renewal options, special conditions, and suretyship details. If the document uses a PREAMBLE or numbered clause format instead of a schedule table, extract the same information from those sections. Look for LESSOR/LESSEE definitions, PREMISES description in clause 1, COMMENCEMENT DATE in clause 3, EXPIRY DATE in clause 3, BASIC MONTHLY RENTAL in clause 4 tables, DEPOSITS in clause 8, SPECIAL CONDITIONS in clause 16. For FRANCHISE AGREEMENTS specifically: - Extract Annexure A 'Financial and Other Terms' - Item 1: Upfront License Fee amount - Item 2: Franchise Fee percentage - Item 3: Renewal Fee - Item 4: Marketing Fee percentage - Item 7: Commencement Date - Item 8: Duration/Period - Item 10: Premises/Location Calculate expiry = commencement + duration"
    fundamental_terms_schema = """{
  "fundamental_terms": [
    {
      "document": "filename.pdf",
      "doc_type": "Lease Agreement or Franchise Agreement",
      "lessor": {"name": "string", "registration": "string", "representative": "string", "domicilium": "string"},
      "lessee": {"name": "string", "registration": "string", "representative": "string", "domicilium": "string"},
      "premises": {"description": "string", "address": "string", "erf": "string"},
      "lease_period": "string",
      "commencement_date": "YYYY-MM-DD",
      "expiry_date": "YYYY-MM-DD",
      "beneficial_occupation_date": "YYYY-MM-DD or null",
      "renewal_option": "If document states N/A, None, or Nil — return 'None'. If document has a renewal option return the exact terms e.g. '1 x 5 years'. Never return 'Not specified' if the document explicitly addresses renewal.",
      "escalation_rate": "string",
      "permitted_use": "string",
      "security_deposit": "string",
      "rental_schedule": [{"period": "string", "amount": "string", "note": "string"}],
      "trading_hours": {"monday_thursday": "string", "friday": "string", "saturday": "string", "sunday_public_holidays": "string"},
      "payment_details": {
        "bank": "string",
        "branch": "string", 
        "branch_code": "string",
        "account_holder": "string",
        "account_number": "string",
        "account_type": "string"
      },
      "special_conditions": ["string"],
      "suretyship": "Must be a plain text string describing the surety arrangement. Example: 'Cornelius Gerhard Lotriet, ID/Reg 2023/608635/07' NEVER return suretyship as a JSON object. Flatten all surety details into one sentence.",
      "franchise_terms": {"commencement_date": "YYYY-MM-DD or null", "expiry_date": "YYYY-MM-DD or null", "term_length": "string or null", "renewal_option": "string or null", "upfront_license_fee": "string or null", "monthly_franchise_fee": "string or null", "renewal_fee": "string or null", "marketing_fee": "string or null"}
    }
  ]
}"""

    reduce_task = f'''Produce a comprehensive summary of all fundamental lease terms.
JSON SCHEMA REQUIREMENT:
{fundamental_terms_schema}

Return one fundamental_terms entry per document. Each entry must reflect ONLY the data from that specific document.
Do not mix lease data with franchise data. The document field must match the filename from the --- DOCUMENT START --- marker.

If a document is a lease agreement only, set all franchise_terms fields to null.
For franchise agreements, Annexure A contains the Financial and Other Terms.
Item 7 is the Commencement Date — extract it.
Item 8 is the Duration — use it to calculate expiry date.
Item 1 is the Upfront License Fee — extract the exact rand amount.
Item 2 is the Franchise Fee — extract the exact percentage.
These are CRITICAL fields — do not leave them null if the document is a franchise agreement.

If the document is a LEASE AGREEMENT (not a franchise agreement), do NOT include a franchise_terms section at all — omit it entirely from that entry.

CRITICAL: The 'document' field in each fundamental_terms entry MUST be the exact filename from the --- DOCUMENT START: filename --- marker found in the input text.
NEVER write 'filename.pdf' literally.
NEVER invent a filename.
Copy it exactly as it appears after 'DOCUMENT START:' in the input.

Return ONLY the raw JSON object.'''

    def legacy_op():
        old_full_text = str(full_text)[:18000]
        prompt = f"""You are a master commercial real estate attorney. Extract the fundamental terms of the provided lease or franchise agreement.

DOCUMENTS TEXT:
{old_full_text}

INSTRUCTIONS:
Output ONLY valid JSON matching this exact structure:
{fundamental_terms_schema}

Return one fundamental_terms entry per document.
Each entry must reflect ONLY the data from that specific document.
Do not mix lease data with franchise data.
If a document is a lease only, set all franchise_terms fields to null.

CRITICAL: The 'document' field in each fundamental_terms entry MUST be the exact filename from the --- DOCUMENT START: filename --- marker found in the input text.
NEVER write 'filename.pdf' literally.
NEVER invent a filename.
Copy it exactly as it appears after 'DOCUMENT START:' in the input."""
        resp = groq_client.chat.completions.create(
            model=GROQ_EXTRACTION_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=3000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    cache_path = os.path.join(cache_dir, f"{workspace_id}_fundamental_terms.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op)), media_type="text/event-stream")


async def extract_expiries(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="No documents selected")
        
    documents_to_process = []
    workspace_id = None
    
    for doc_id in payload.doc_ids:
        if current_user is not None:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
                models.Workspace.firm_id == current_user.firm_id
            ).first()
        else:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
                models.Workspace.session_id == x_session_id
            ).first()
            
        if not doc:
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        if not workspace_id:
            workspace_id = str(doc.workspace_id)
            
        doc_text = None
        for candidate_id in [doc_id, getattr(doc, "pinecone_doc_id", None), getattr(doc, "id", None)]:
            if not candidate_id: continue
            file_path = os.path.join(cache_dir, f"{candidate_id}.md")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        doc_text = f.read()
                    doc_text = harvest_annexure_orphans(doc_text)
                    break
                except Exception as e:
                    print(f"Failed to read {file_path}: {e}")
                    
        if doc_text:
            documents_to_process.append({
                "id": str(getattr(doc, "id", "")),
                "pinecone_doc_id": str(getattr(doc, "pinecone_doc_id", "")),
                "filename": str(doc.filename),
                "text": doc_text
            })

    if not documents_to_process:
        raise HTTPException(status_code=404, detail="No text could be extracted from selected documents.")
        
    documents_to_process.sort(key=lambda d: 1 if "franchise" in d["filename"].lower() or "fa_" in d["filename"].lower() else 0)

    async def pipeline_wrapper():
        from datetime import datetime
        from services.date_engine import (
            calculate_expiry,
            calculate_renewal_window,
            check_renewal_window_status,
            is_beneficial_occupation_significant,
            validate_dates,
            calculate_renewal_date
        )
        
        final_expiries = []
        final_context = None
        
        for doc_info in documents_to_process:
            fname = doc_info["filename"]
            doc_text = doc_info["text"]
            full_text = f"\n--- DOCUMENT START: {fname} ---\n{doc_text}\n"
            
            example_expiries = (
                '{\n'
                '      "document": "' + fname + '",\n'
                '      "doc_type": "Lease Agreement or Franchise Agreement",\n'
                '      "candidate_legal_commencement_dates": [\n'
                '        { "value": "YYYY-MM-DD", "confidence": 0.95, "source_text": "...", "source_page": 1, "source_clause": "...", "source_label": "Lease Period", "extraction_method": "explicit_schedule", "priority": 1 }\n'
                '      ],\n'
                '      "candidate_rental_commencement_dates": [],\n'
                '      "candidate_beneficial_occupation_dates": [],\n'
                '      "candidate_expiry_dates": [],\n'
                '      "candidate_duration_years": [],\n'
                '      "candidate_renewal_types": [\n'
                '        { "value": "automatic_renewal_with_opt_out", "confidence": 0.95, "source_text": "...", "source_page": 2, "source_clause": "...", "source_label": "Renewal", "extraction_method": "explicit_clause", "priority": 1 }\n'
                '      ],\n'
                '      "candidate_notice_min_months": [],\n'
                '      "candidate_notice_max_months": [],\n'
                '      "requires_notice": true,\n'
                '      "notice_party": "tenant",\n'
                '      "renewal_action_required": true,\n'
                '      "renewal_clause_text": "verbatim excerpt under 50 words",\n'
                '      "action_required": "specific action text"\n'
                '    }'
            )

            map_task = """Extract all dates, deadlines, and timeframes from this section as EVIDENCE OBJECTS.
For each field, extract an array of candidates if multiple apply.

EVIDENCE HIERARCHY ENGINE (Assign priority 1-5):

For Dates (Commencement, Expiry, Occupation, Notice):
Priority 1: Explicit expiry or commencement in schedule/annexure, or Fundamental Terms section.
Priority 2: Defined terms section, specific lease period clause.
Priority 3: Commencement + explicit duration calculation in text.
Priority 4: Rental schedules/tables.
Priority 5: Inferred operational text.

For Renewal Type (candidate_renewal_types):
Priority 1: Detailed operative renewal clause.
Priority 2: Clause heading and clause body containing renewal mechanics.
Priority 3: Schedule/annexure summary that includes full renewal mechanism.
Priority 4: Vague schedule/annexure phrase like "renewal option".
Priority 5: Inferred wording.

CRITICAL INSTRUCTIONS:
- Schedule/Fundamental Terms fields ("Beneficial Occupation Date", "Lease Period", "Commencement Date", "Expiry Date") OUTRANK rental tables.
- N1 Lease Example:
  If Schedule says: Beneficial Occupation Date: 2025-09-01, Lease period / expiry: 2025-09-01 to 2030-09-30, but Rental schedule starts 2025-10-01.
  Correct extraction: legal_commencement_date=2025-09-01 (Priority 1), beneficial_occupation_date=2025-09-01, rental_commencement_date=2025-10-01, expiry_date=2030-09-30.
- N1 Franchise Example:
  If wording says "automatically renews unless notice is given", renewal_type MUST be "automatic_renewal_with_opt_out" (NOT tenant_option).

Extract candidate arrays for:
1. candidate_legal_commencement_dates
2. candidate_beneficial_occupation_dates
3. candidate_rental_commencement_dates
4. candidate_expiry_dates
5. candidate_duration_years
6. candidate_renewal_types
   Must be: manual_renewal | automatic_renewal | automatic_renewal_with_opt_out | tenant_option | landlord_option | mutual_option | no_renewal_right | unknown
   If clause says "N/A" or "no option to renew", value MUST be "no_renewal_right".
7. candidate_notice_min_months (Integer)
8. candidate_notice_max_months (Integer)

Every candidate object MUST have:
"value", "confidence" (0.0-1.0), "source_text", "source_page", "source_clause", "source_label" (e.g. "Lease Period", "Rental Commencement Date"), "extraction_method", "priority" (1-5).
"""

            reduce_task = f"""You MUST produce a single expiry entry for the document named '{fname}' based on the provided map results.
CRITICAL ANTI-CONTAMINATION RULE:
You are processing ONLY this document. Do not infer, borrow, compare, or import dates, clauses, names, or renewal terms from any other document.

CRITICAL: The 'document' field in the expiry entry MUST be exactly: '{fname}'
Aggregate ALL evidence candidates from the map results. DO NOT discard conflicting dates. Put them in the candidate arrays so the deterministic engine can resolve them.
Output ONLY valid JSON matching this exact structure:
{{
  "document_context": {{
    "location": "...",
    "parties": [ {{"role": "...", "name": "..."}} ],
    "obligations": []
  }},
  "expiries": [
    {example_expiries}
  ]
}}
Return ONLY the JSON object."""



            def create_legacy_op(t):
                def legacy_op():
                    old_full_text = str(t)[:18000]
                    prompt = f"""You are a senior legal analyst extracting crucial dates from multiple contracts to trigger calendar/SmartBuilding events.
CRITICAL ANTI-CONTAMINATION RULE:
You are processing ONLY this document. Do not infer, borrow, compare, or import dates, clauses, names, or renewal terms from any other document.

DOCUMENTS TEXT:
{old_full_text}

INSTRUCTIONS:
Find the Expiry Date, Renewal Notice Deadline, and relevant Notification Clause for each document.
Output ONLY valid JSON matching this exact structure:
{{
  "document_context": {{
    "location": "Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building.",
    "parties": [
      {{"role": "Landlord/Lessor/Franchisor/etc", "name": "Full legal entity name"}}
    ],
    "obligations": [
      {{
        "party": "Party name",
        "category": "Financial | Operational | Maintenance | Compliance",
        "obligation": "Description of the obligation",
        "clause_reference": "e.g. 4.2.3 or Schedule 1"
      }}
    ]
  }},
  "expiries": [
    {example_expiries}
  ]
}}

If a date is vague or missing, make your best guess for the date format "YYYY-MM-DD". Perform strict date arithmetic if the contract specifies a start date and term duration. Return ONLY the JSON object."""
                    resp = groq_client.chat.completions.create(
                        model=GROQ_EXTRACTION_MODEL,
                        messages=[{'role': 'user', 'content': prompt}],
                        temperature=0.0,
                        max_tokens=2000
                    )
                    raw = resp.choices[0].message.content.strip()
                    raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
                    return json.loads(raw)
                return legacy_op

            try:
                doc_complete = False
                async for chunk in run_feature_gated_pipeline(full_text, map_task, reduce_task, create_legacy_op(full_text)):
                    if chunk.startswith("data: "):
                        try:
                            data_obj = json.loads(chunk[6:])
                            if data_obj.get("status") == "complete":
                                result = data_obj.get("data", {})
                                doc_complete = True
                                
                                # Set context if not already set
                                if not final_context and result.get("document_context"):
                                    final_context = result.get("document_context")
                                    
                                expiries = result.get("expiries", [])
                                # We expect 1 expiry per document but loop just in case

                                ALLOWED_RENEWAL_TYPES = {
                                    "manual_renewal", "automatic_renewal", "automatic_renewal_with_opt_out", 
                                    "tenant_option", "landlord_option", "mutual_option", "no_renewal_right", "unknown"
                                }
                                
                                def is_iso_date(val):
                                    if not isinstance(val, str): return False
                                    try:
                                        from datetime import datetime
                                        datetime.strptime(val, "%Y-%m-%d")
                                        return True
                                    except Exception:
                                        return False

                                def resolve_candidates(field_key, candidates, v_flags):
                                    if not candidates: return None
                                    if not isinstance(candidates, list): return candidates
                                    
                                    sorted_cands = sorted(candidates, key=lambda x: x.get("priority", 99) if isinstance(x, dict) else 99)
                                    
                                    # Conflict detection
                                    valid_vals = []
                                    for c in sorted_cands:
                                        if isinstance(c, dict) and "value" in c:
                                            v = c["value"]
                                            if field_key.endswith("date") or "notice" in field_key:
                                                if is_iso_date(v): valid_vals.append(v)
                                            elif field_key == "renewal_type":
                                                if v in ALLOWED_RENEWAL_TYPES: valid_vals.append(v)
                                            else:
                                                valid_vals.append(v)
                                                
                                    if len(set(valid_vals)) > 1:
                                        from datetime import datetime
                                        conflict = False
                                        if field_key.endswith("date") or "notice" in field_key:
                                            dates = [datetime.strptime(v, "%Y-%m-%d").date() for v in set(valid_vals)]
                                            max_diff = (max(dates) - min(dates)).days
                                            if "expiry" in field_key and max_diff > 30: conflict = True
                                            elif "expiry" not in field_key and max_diff > 7: conflict = True
                                        else:
                                            conflict = True
                                            
                                        if conflict:
                                            v_flags.append(f"Multiple conflicting candidates found for {field_key} — review source evidence")
                                    
                                    if field_key == "renewal_type":
                                        for cand in sorted_cands:
                                            if not isinstance(cand, dict): continue
                                            if cand.get("value") in ALLOWED_RENEWAL_TYPES:
                                                return cand
                                            else:
                                                if "Invalid renewal_type candidate ignored" not in v_flags:
                                                    v_flags.append("Invalid renewal_type candidate ignored")
                                        return {"value": "unknown", "priority": 99}
                                        
                                    return sorted_cands[0]
                                    
                                for exp in expiries:
                                    exp["document_id"] = doc_info["id"]
                                    exp["pinecone_doc_id"] = doc_info["pinecone_doc_id"]
                                    exp["workspace_id"] = workspace_id
                                    
                                    if exp.get("document") != fname:
                                        exp["document"] = fname
                                        v_flags = exp.get("validation_flags", [])
                                        if "Filename hallucination corrected" not in v_flags:
                                            v_flags.append("Filename hallucination corrected")
                                        exp["validation_flags"] = v_flags
                                        
                                    v_flags = exp.get("validation_flags", [])
                                        
                                    # Resolve candidates
                                    for key in ["legal_commencement_date", "rental_commencement_date", "beneficial_occupation_date", "expiry_date", "duration_years", "renewal_type", "notice_min_months", "notice_max_months"]:

                                        if key == "expiry_date": cand_key = "candidate_expiry_dates"
                                        elif key.endswith("s"): cand_key = f"candidate_{key}"
                                        else: cand_key = f"candidate_{key}s"
                                        candidates = exp.get(cand_key, [])
                                        resolved = resolve_candidates(key, candidates, v_flags)
                                        if resolved and isinstance(resolved, dict):
                                            exp[f"{key}_evidence"] = resolved
                                            val = resolved.get("value")
                                            if key.endswith("date") or "notice" in key:
                                                if is_iso_date(val):
                                                    exp[key] = val
                                                else:
                                                    exp[key] = None
                                            else:
                                                exp[key] = val
                                            # Also keep candidates array
                                            exp[cand_key] = candidates
                                        elif resolved is not None:
                                            if key.endswith("date") or "notice" in key:
                                                if is_iso_date(resolved):
                                                    exp[key] = resolved
                                                else:
                                                    exp[key] = None
                                            else:
                                                exp[key] = resolved

                                    dt = exp.get("doc_type", "")
                                    fname_lower = fname.lower()
                                    is_franchise = "franchise" in dt.lower() or "franchise" in fname_lower or "fa_" in fname_lower
                                    
                                    if is_franchise and not exp.get("legal_commencement_date"):
                                        found_lease_date = None
                                        
                                        # 1. Check current execution memory (if lease was processed just before this franchise)
                                        for prev_exp in final_expiries:
                                            if "franchise" not in prev_exp.get("doc_type", "").lower() and prev_exp.get("legal_commencement_date"):
                                                found_lease_date = prev_exp["legal_commencement_date"]
                                                break
                                                
                                        # 2. Check disk cache if not found in memory
                                        if not found_lease_date:
                                            cache_file = os.path.join(cache_dir, f"{workspace_id}_extract_expiries.json")
                                            if os.path.exists(cache_file):
                                                try:
                                                    with open(cache_file, "r") as f:
                                                        cache_data = json.load(f)
                                                        for cached_exp in cache_data.get("expiries", []):
                                                            if "franchise" not in cached_exp.get("doc_type", "").lower() and cached_exp.get("legal_commencement_date"):
                                                                found_lease_date = cached_exp["legal_commencement_date"]
                                                                break
                                                except:
                                                    pass
                                        
                                        if found_lease_date:
                                            exp["legal_commencement_date"] = found_lease_date
                                            exp["date_resolution_status"] = "inferred_from_aligned_lease"
                                            exp["date_dependency"] = "franchise date inferred from same-site lease date"
                                            v_flags.append("Franchise date inferred from aligned lease — verify against franchise Annexure A")
                                        else:
                                            exp["date_resolution_status"] = "dependency_required"
                                            exp["date_dependency"] = "requires legal_commencement_date"
                                            v_flags.append("Date value unresolved — dependency required")

                                    ai_expiry = exp.get("expiry_date")
                                    legal_comm = exp.get("legal_commencement_date")
                                    rental_comm = exp.get("rental_commencement_date")
                                    bo_comm = exp.get("beneficial_occupation_date")
                                    
                                    if legal_comm and exp.get("duration_years"):
                                        calc = calculate_expiry(legal_comm, exp.get("duration_years"), "day_before")
                                        exp["deterministic_expiry_date"] = calc["date"]
                                        exp["expiry_calculation_basis"] = calc["basis"]
                                        
                                        if exp.get("date_resolution_status") == "inferred_from_aligned_lease":
                                            exp["expiry_date_resolution_status"] = "calculated_from_inferred_commencement"
                                            exp["expiry_date_dependency"] = "uses inferred legal_commencement_date from aligned lease"
                                            v_flags.append("Expiry calculated from inferred franchise commencement — verify against franchise Annexure A")
                                        
                                        # Explicit Expiry Precedence
                                        if ai_expiry:
                                            from datetime import datetime
                                            try:
                                                a_d = datetime.strptime(ai_expiry, "%Y-%m-%d").date()
                                                d_d = datetime.strptime(calc["date"], "%Y-%m-%d").date()
                                                if abs((a_d - d_d).days) > 45:
                                                    v_flags.append("Calculated expiry differs materially from explicit expiry — verify commencement/duration inputs")
                                                    exp["expiry_date"] = ai_expiry
                                                    exp["expiry_determination"] = "explicit_overrode_deterministic"
                                                elif abs((a_d - d_d).days) > 1:
                                                    exp["expiry_date"] = ai_expiry
                                                    exp["expiry_determination"] = "explicit_minor_deviation"
                                                else:
                                                    exp["expiry_date"] = calc["date"]
                                                    exp["expiry_determination"] = "deterministic_aligned_with_explicit"
                                            except Exception:
                                                exp["expiry_date"] = ai_expiry
                                                exp["expiry_determination"] = "explicit_fallback"
                                        else:
                                            exp["expiry_date"] = calc["date"]
                                            exp["expiry_determination"] = "deterministic_calculated"
                                    else:
                                        exp["expiry_date"] = ai_expiry
                                        exp["expiry_determination"] = "explicit_only"
                                        
                                    expiry = exp.get("expiry_date")
                                    
                                    if expiry:
                                        ren_calc = calculate_renewal_date(expiry)
                                        exp["deterministic_renewal_date"] = ren_calc["date"]
                                        exp["renewal_date"] = ren_calc["date"]
                                        
                                    r_type = exp.get("renewal_type", "")
                                    if r_type == "manual": exp["renewal_type"] = "manual_renewal"
                                    elif r_type == "automatic": exp["renewal_type"] = "automatic_renewal"
                                    elif r_type == "opt_out": exp["renewal_type"] = "automatic_renewal_with_opt_out"
                                    elif r_type == "none": exp["renewal_type"] = "no_renewal_right"
                                    
                                    min_m = exp.get("notice_min_months")
                                    max_m = exp.get("notice_max_months")
                                    if expiry and min_m:
                                        window = calculate_renewal_window(expiry, int(min_m), int(max_m) if max_m else int(min_m))
                                        exp["deterministic_renewal_notice_earliest"] = window["renewal_notice_earliest"]
                                        exp["deterministic_renewal_notice_latest"] = window["renewal_notice_latest"]
                                        exp["renewal_notice_earliest"] = window["renewal_notice_earliest"]
                                        exp["renewal_notice_latest"] = window["renewal_notice_latest"]
                                        exp["renewal_window_basis"] = window["basis"]
                                        
                                        status = check_renewal_window_status(expiry, int(min_m), int(max_m) if max_m else int(min_m))
                                        exp["renewal_window_status"] = status["status"]
                                        exp["renewal_urgency"] = status["urgency"]
                                        exp["days_until_expiry"] = status["days_until_expiry"]
                                        
                                    if expiry and not exp.get("days_until_expiry"):
                                        from services.date_engine import days_between
                                        from datetime import date
                                        today = date.today().isoformat()
                                        db_result = days_between(today, expiry)
                                        if db_result.get("days") is not None:
                                            exp["days_until_expiry"] = db_result["days"]
                                            
                                    if bo_comm and legal_comm:
                                        if bo_comm == legal_comm:
                                            pass
                                        else:
                                            from datetime import datetime
                                            try:
                                                b_d = datetime.strptime(bo_comm, "%Y-%m-%d")
                                                l_d = datetime.strptime(legal_comm, "%Y-%m-%d")
                                                if b_d < l_d:
                                                    if rental_comm and legal_comm == rental_comm:
                                                        v_flags.append("Rent-free/beneficial occupation period detected — verify lease commencement vs rental commencement")
                                                    else:
                                                        v_flags.append("Beneficial occupation starts before legal commencement")
                                            except Exception:
                                                pass
                                        
                                    engine_flags = validate_dates(
                                        legal_commencement=legal_comm,
                                        rental_commencement=rental_comm,
                                        beneficial_occupation=bo_comm,
                                        expiry=expiry,
                                        renewal_latest=exp.get("deterministic_renewal_notice_latest")
                                    )
                                    if engine_flags:
                                        for f in engine_flags:
                                            if "Expiry date is before commencement date" in f or "Renewal notice deadline is after expiry date" in f:
                                                v_flags.append(f)
                                        
                                    exp["validation_flags"] = v_flags
                                    
                                    dt = exp.get("doc_type", "")
                                    if len(str(dt)) > 30 or dt not in ["Lease Agreement", "Franchise Agreement", "Sale Agreement", "Non-Disclosure Agreement"]:
                                        exp["doc_type"] = "Lease Agreement"
                                        
                                    final_expiries.append(exp)
                                
                                # Normalize variant field names to 
                                # canonical schema
                                for exp in expiries:
                                    # Commencement date variants
                                    if not exp.get("raw_commencement_date"):
                                        exp["raw_commencement_date"] = (
                                            exp.get("legal_commencement_date")
                                            or exp.get("commencement_date")
                                            or None
                                        )
                                    
                                    # Expiry date — may already be set
                                    if not exp.get("expiry_date"):
                                        exp["expiry_date"] = (
                                            exp.get("raw_expiry_date")
                                            or None
                                        )
                                    
                                    # Duration years
                                    if not exp.get("duration_years"):
                                        ev = exp.get("duration_years_evidence")
                                        if ev and isinstance(ev, dict):
                                            exp["duration_years"] = ev.get(
                                                "value")
                                    
                                    # Notice months — AI sometimes sets
                                    # null despite having evidence
                                    if not exp.get("notice_min_months"):
                                        ev = exp.get(
                                            "notice_min_months_evidence")
                                        if ev and isinstance(ev, dict):
                                            val = ev.get("value")
                                            if val and isinstance(val, int) \
                                               and val > 0:
                                                exp["notice_min_months"] = val
                                    
                                    if not exp.get("notice_max_months"):
                                        ev = exp.get(
                                            "notice_max_months_evidence")
                                        if ev and isinstance(ev, dict):
                                            val = ev.get("value")
                                            if val and isinstance(val, int) \
                                               and val > 0:
                                                exp["notice_max_months"] = val
                                    
                                    # Renewal type normalization
                                    rt = exp.get("renewal_type")
                                    if rt:
                                        # Map variant values to canonical
                                        rt_map = {
                                            "no_renewal_right": "none",
                                            "automatic_renewal_with_opt_out": 
                                                "opt_out",
                                            "manual_renewal": "manual",
                                        }
                                        if rt in rt_map:
                                            exp["renewal_type"] = rt_map[rt]
                                    
                                    # Beneficial occupation
                                    if not exp.get(
                                        "beneficial_occupation_date"):
                                        ev = exp.get(
                                            "beneficial_occupation_date_evidence")
                                        if ev and isinstance(ev, dict):
                                            val = ev.get("value")
                                            # Only use if it looks like a date
                                            if val and len(str(val)) == 10 \
                                               and "-" in str(val):
                                                exp["beneficial_occupation_date"]\
                                                    = val
                                    
                                    # Clause confidence
                                    if not exp.get("clause_confidence"):
                                        ev = exp.get(
                                            "renewal_type_evidence")
                                        if ev and isinstance(ev, dict):
                                            exp["clause_confidence"] = \
                                                ev.get("confidence", 0.0)
                                    
                                    # Renewal clause text
                                    if not exp.get("renewal_clause_text"):
                                        ev = exp.get(
                                            "renewal_type_evidence")
                                        if ev and isinstance(ev, dict):
                                            exp["renewal_clause_text"] = \
                                                ev.get("source_text")

                            else:
                                msg = data_obj.get("message", "")
                                yield f"data: {json.dumps({'status': 'processing', 'message': f'[{fname}] {msg}'})}\n\n"
                        except Exception:
                            pass
                if not doc_complete:
                    raise Exception("Document extraction failed to yield a complete result")
            except Exception as e:
                print(f"Extraction failed for {fname}: {e}")
                final_expiries.append({
                    "document_id": doc_info["id"],
                    "pinecone_doc_id": doc_info["pinecone_doc_id"],
                    "workspace_id": workspace_id,
                    "document": fname,
                    "doc_type": "Unknown",
                    "extraction_failed": True,
                    "clause_confidence": 0.0,
                    "action_required": "Document extraction failed — manual review required",
                    "validation_flags": ["Document extraction failed — manual review required"]
                })
                
        # Consolidate all results
        from services.risk_engine import calculate_workspace_risk_scores
        
        cache_file = os.path.join(cache_dir, f"{workspace_id}_extract_expiries.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    existing_data = json.load(f)
                    existing_expiries = existing_data.get("expiries", [])
                    new_doc_ids = [e.get("pinecone_doc_id") for e in final_expiries]
                    for e in existing_expiries:
                        if e.get("pinecone_doc_id") not in new_doc_ids:
                            final_expiries.append(e)
            except:
                pass


        ws_summary_docs = []
        for exp in final_expiries:
            ws_summary_docs.append({
                "filename": exp.get("document"),
                "doc_type": exp.get("doc_type"),
                "commencement_date": exp.get("legal_commencement_date") or exp.get("commencement_date") or exp.get("raw_commencement_date"),
                "expiry_date": exp.get("deterministic_expiry_date") or exp.get("expiry_date") or exp.get("raw_expiry_date"),
                "renewal_deadline": exp.get("deterministic_renewal_notice_latest") or exp.get("renewal_notice_latest") or exp.get("renewal_deadline"),
                "renewal_option_period": exp.get("renewal_period_years") or exp.get("renewal_option_period"),
                "action_required": exp.get("action_required"),
                "renewal_type": exp.get("renewal_type"),
                "renewal_window_status": exp.get("renewal_window_status"),
                "renewal_urgency": exp.get("renewal_urgency"),
                "days_until_expiry": exp.get("days_until_expiry"),
                "renewal_notice_earliest": exp.get("deterministic_renewal_notice_earliest") or exp.get("renewal_notice_earliest"),
                "renewal_notice_latest": exp.get("deterministic_renewal_notice_latest") or exp.get("renewal_notice_latest"),
                "notice_min_months": exp.get("notice_min_months"),
                "notice_max_months": exp.get("notice_max_months")
            })

        def detect_renewal_mismatch(docs: list) -> dict:
            if not docs: return {"status": "ok"}
            lease = next((d for d in docs if d.get("doc_type") == "Lease Agreement"), None)
            franchise = next((d for d in docs if d.get("doc_type") == "Franchise Agreement"), None)
            if not lease or not franchise: return {"status": "ok"}
            
            rules_triggered = []
            mismatch_detected = False
            
            l_type = lease.get("renewal_type")
            f_type = franchise.get("renewal_type")
            if l_type == "no_renewal_right" and f_type != "no_renewal_right":
                mismatch_detected = True
                rules_triggered.append("Franchise has renewal option but Lease has no renewal right")
            
            l_dl = lease.get("renewal_notice_latest")
            f_dl = franchise.get("renewal_notice_latest")
            if l_dl and f_dl:
                try:
                    ld = datetime.strptime(l_dl, "%Y-%m-%d")
                    fd = datetime.strptime(f_dl, "%Y-%m-%d")
                    if fd < ld:
                        mismatch_detected = True
                        rules_triggered.append(f"Franchise renewal deadline ({f_dl}) is BEFORE Lease deadline ({l_dl})")
                except:
                    pass
                    
            if mismatch_detected:
                return {"status": "mismatch", "rules_triggered": rules_triggered}
            return {"status": "ok"}

        mismatch = detect_renewal_mismatch(ws_summary_docs)
        risk_scores = calculate_workspace_risk_scores(ws_summary_docs, mismatch)
        
        final_data = {
            "workspace_id": workspace_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "document_context": final_context or {},
            "expiries": final_expiries,
            "rules_triggered": mismatch.get("rules_triggered", []),
            "renewal_mismatch": mismatch,
            "risk_scores": risk_scores,
            "overall_risk_score": risk_scores.get("overall_risk_score"),
            "overall_severity": risk_scores.get("overall_severity"),
            "earliest_deadline": min((e.get("renewal_deadline") for e in ws_summary_docs if e.get("renewal_deadline") and e.get("renewal_deadline") not in ["null", None, ""]), default=None)
        }
        
        yield f"data: {json.dumps({'status': 'complete', 'data': final_data})}\n\n"

    cache_path = os.path.join(cache_dir, f"{workspace_id}_extract_expiries.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, pipeline_wrapper(), workspace_id=str(workspace_id)), media_type="text/event-stream")

async def portfolio_overview(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    from datetime import datetime
    if current_user:
        workspaces = db.query(models.Workspace).filter(models.Workspace.firm_id == current_user.firm_id).all()
    elif x_session_id:
        workspaces = db.query(models.Workspace).filter(models.Workspace.session_id == x_session_id).all()
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    final_data = []
    
    for ws in workspaces:
        cache_path = os.path.join(cache_dir, f"{ws.id}_extract_expiries.json")
        ws_summary = {
            "workspace_id": str(ws.id),
            "workspace_name": ws.name,
            "documents": [],
            "property_location": None,
            "parties": [],
            "cache_available": False,
            "last_scanned": None
        }
        
        if os.path.exists(cache_path):
            try:
                ws_summary["cache_available"] = True
                ws_summary["last_scanned"] = datetime.fromtimestamp(os.path.getmtime(cache_path)).isoformat()
                with open(cache_path, "r") as f:
                    cached = json.load(f)
                
                doc_context = cached.get("document_context", {})
                ws_summary["property_location"] = doc_context.get("location")
                ws_summary["parties"] = doc_context.get("parties", [])
                
                override_path = os.path.join(cache_dir, f"{ws.id}_overrides.json")
                overrides = {}
                if os.path.exists(override_path):
                    try:
                        with open(override_path, "r") as f:
                            overrides = json.load(f)
                    except Exception:
                        pass
                        
                verified_path = os.path.join(cache_dir, f"{ws.id}_verified_expiries.json")
                if os.path.exists(verified_path):
                    try:
                        with open(verified_path, "r") as vf:
                            verified_data = json.load(vf)
                        cached = merge_verified_edits(cached, verified_data, "expiries")
                    except Exception:
                        pass
                
                expiries = cached.get("expiries", [])
                for exp in expiries:
                    doc_id = exp.get("pinecone_doc_id") or exp.get("document_id")
                    if doc_id and doc_id in overrides:
                        doc_overrides = overrides[doc_id]
                        for field, override in doc_overrides.items():
                            # Map override field to cache field
                            field_map = {
                                "commencement_date": "raw_commencement_date",
                                "expiry_date": "expiry_date",
                                "renewal_type": "renewal_type",
                                "notice_min_months": "notice_min_months",
                                "notice_max_months": "notice_max_months",
                            }
                            cache_field = field_map.get(field, field)
                            exp[cache_field] = override["value"]
                            exp[f"{cache_field}_source"] = "manual_user_verified"
                            
                    doc_name = str(exp.get("document", ""))
                    # Prefer AI-extracted doc_type from cache
                    ai_doc_type = exp.get("doc_type")
                    if ai_doc_type in [
                        "Lease Agreement", 
                        "Franchise Agreement"
                    ]:
                        doc_type = ai_doc_type
                    else:
                        # Fallback: filename-based detection
                        doc_name_lower = doc_name.lower()
                        doc_type = (
                            "Franchise Agreement" 
                            if (
                                "franchise" in doc_name_lower or
                                "_fa_" in doc_name_lower or
                                "_fa." in doc_name_lower or
                                " fa " in doc_name_lower or
                                "fa_" in doc_name_lower
                            )
                            else "Lease Agreement"
                        )
                    
                    ws_summary["documents"].append({
                        "filename": doc_name,
                        "_verified": exp.get("_verified", False),
                        "doc_type": doc_type,
                        "commencement_date": (
                            exp.get("raw_commencement_date")
                            or exp.get("legal_commencement_date")
                            or exp.get("commencement_date")
                        ),
                        "commencement_source": (
                            exp.get("raw_commencement_date_source")
                            or exp.get("commencement_source")
                            or "ai_extracted"
                        ),
                        "expiry_date": exp.get("deterministic_expiry_date") or exp.get("expiry_date") or exp.get("raw_expiry_date"),
                        "renewal_deadline": exp.get("deterministic_renewal_notice_latest") or exp.get("renewal_notice_latest") or exp.get("renewal_deadline"),
                        "renewal_option_period": exp.get("renewal_option_period"),
                        "action_required": exp.get("action_required"),
                        "renewal_type": exp.get("renewal_type"),
                        "renewal_window_status": exp.get("renewal_window_status"),
                        "renewal_urgency": exp.get("renewal_urgency"),
                        "days_until_expiry": exp.get("days_until_expiry"),
                        "renewal_notice_earliest": exp.get("renewal_notice_earliest"),
                        "renewal_notice_latest": exp.get("renewal_notice_latest"),
                        "notice_min_months": exp.get("notice_min_months"),
                        "notice_max_months": exp.get("notice_max_months")
                    })
                
                mismatch = detect_renewal_mismatch(ws_summary["documents"])
                
                from services.risk_engine import \
                    calculate_workspace_risk_scores
                risk_scores = calculate_workspace_risk_scores(
                    ws_summary["documents"], mismatch)
                
                ws_summary["rules_triggered"] = \
                    mismatch.get("rules_triggered", [])
                ws_summary["renewal_mismatch"] = mismatch
                ws_summary["risk_scores"] = risk_scores
                ws_summary["overall_risk_score"] = \
                    risk_scores.get("overall_risk_score")
                ws_summary["overall_severity"] = \
                    risk_scores.get("overall_severity")
                ws_summary["earliest_deadline"] = min(
                    (e.get("renewal_deadline") 
                     for e in ws_summary["documents"] 
                     if e.get("renewal_deadline") 
                     and e.get("renewal_deadline") 
                     not in ["null", None, ""]),
                    default=None
                )
            except Exception as e:
                print(f"Error reading cache for workspace {ws.id}: {e}")
                
        final_data.append(ws_summary)

    async def generate_response():
        yield f"data: {json.dumps({'status': 'complete', 'data': final_data})}\n\n"

    return StreamingResponse(generate_response(), media_type="text/event-stream")




async def document_compare(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    if payload.doc_id_a == payload.doc_id_b:
        raise HTTPException(status_code=400, detail="Must select two different documents to compare")
        
    doc_texts = {}
    workspace_id = None
    
    for doc_id in [payload.doc_id_a, payload.doc_id_b]:
        if current_user:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                models.WorkspaceDocument.pinecone_doc_id == doc_id,
                models.Workspace.firm_id == current_user.firm_id
            ).first()
        else:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                models.WorkspaceDocument.pinecone_doc_id == doc_id,
                models.Workspace.session_id == x_session_id
            ).first()
            
        if not doc:
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        if not workspace_id:
            workspace_id = doc.workspace_id
            
        doc_text = None
        for candidate_id in [doc_id, doc.pinecone_doc_id, doc.id]:
            if not candidate_id: continue
            file_path = os.path.join(cache_dir, f"{candidate_id}.md")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        doc_text = f.read()
                    break
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to extract text from {doc.filename}: {str(e)}")
        if not doc_text:
            raise HTTPException(status_code=404, detail=f"Source markdown for {doc.filename} not found.")
        doc_texts[doc_id] = str(doc_text)

    full_text = f"--- DOCUMENT A START: {payload.doc_id_a} ---\n{doc_texts[payload.doc_id_a]}\n--- DOCUMENT B START: {payload.doc_id_b} ---\n{doc_texts[payload.doc_id_b]}"

    map_task = "Extract all material terms, obligations, and risk clauses from this section. Retain context of which document this belongs to (Document A or Document B). Also extract: Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building. and all party names and roles."
    reduce_task = """Produce a forensic redline diff of ADDED, MODIFIED, and DELETED provisions between the two documents. Flag any sections where comparison was limited by content quality.
JSON SCHEMA REQUIREMENT:
{{
  "document_context": {{
    "location": "Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building.",
    "parties": [
      {{"role": "Landlord/Lessor/Franchisor/etc", "name": "Full legal entity name"}}
    ],
    "obligations": [
      {{
        "party": "Party name",
        "category": "Financial | Operational | Maintenance | Compliance",
        "obligation": "Description of the obligation",
        "clause_reference": "e.g. 4.2.3 or Schedule 1"
      }}
    ]
  }},
  "risk_summary": "A 2-3 sentence executive summary explaining how the risk profile has shifted from Document A to Document B.",
  "changes": [
    {{
      "type": "ADDED",
      "original_text": null,
      "new_text": "Exact text added to Document B",
      "impact": "High/Med/Low impact: Short explanation of legal implication.",
      "clause_reference": "e.g. 4.2"
    }},
    {{
      "type": "DELETED",
      "original_text": "Exact text removed from Document A",
      "new_text": null,
      "impact": "High/Med/Low impact: Short explanation of legal implication.",
      "clause_reference": "e.g. 4.2"
    }},
    {{
      "type": "MODIFIED",
      "original_text": "Exact original clause in Document A",
      "new_text": "Exact new clause in Document B",
      "impact": "High/Med/Low impact: Short explanation of how the modification shifts obligation.",
      "clause_reference": "e.g. 4.2"
    }}
  ]
}}

Return ONLY the raw JSON object."""

    def legacy_op():
        doc_a_old = str(doc_texts[payload.doc_id_a])[:9000]
        doc_b_old = str(doc_texts[payload.doc_id_b])[:9000]
        prompt = f"""You are a master legal analyst conducting a forensic "redline" comparison between an original document and a modified draft. 
    
DOCUMENT A (Original / Base Document):
{doc_a_old}

DOCUMENT B (Modified / Counter-party Draft):
{doc_b_old}

INSTRUCTIONS:
Carefully compare the documents. Output a structured forensic difference report in valid JSON.
Ignore cosmetic or stylistic wording changes (like whitespace or font). Focus strictly on substantive legal/obligational changes.

JSON SCHEMA REQUIREMENT:
{{
  "document_context": {{
    "location": "Extract ONLY the physical store/shop premises address — this is where the business actually trades from. Look for fields labeled 'PREMISES', 'Shop No', 'Store Location', or 'Location' in the schedule or annexure. Do NOT extract company registered addresses, head office addresses, domicilium addresses, or postal addresses. The premises address is typically a shop number in a shopping centre or building.",
    "parties": [
      {{"role": "Landlord/Lessor/Franchisor/etc", "name": "Full legal entity name"}}
    ],
    "obligations": [
      {{
        "party": "Party name",
        "category": "Financial | Operational | Maintenance | Compliance",
        "obligation": "Description of the obligation",
        "clause_reference": "e.g. 4.2.3 or Schedule 1"
      }}
    ]
  }},
  "risk_summary": "A 2-3 sentence executive summary explaining how the risk profile has shifted from Document A to Document B.",
  "changes": [
    {{
      "type": "ADDED",
      "original_text": null,
      "new_text": "Exact text added to Document B",
      "impact": "High/Med/Low impact: Short explanation of legal implication.",
      "clause_reference": "e.g. 4.2"
    }},
    {{
      "type": "DELETED",
      "original_text": "Exact text removed from Document A",
      "new_text": null,
      "impact": "High/Med/Low impact: Short explanation of legal implication.",
      "clause_reference": "e.g. 4.2"
    }},
    {{
      "type": "MODIFIED",
      "original_text": "Exact original clause in Document A",
      "new_text": "Exact new clause in Document B",
      "impact": "High/Med/Low impact: Short explanation of how the modification shifts obligation.",
      "clause_reference": "e.g. 4.2"
    }}
  ]
}}

Return ONLY the raw JSON object. Do not wrap in markdown code blocks."""
        resp = groq_client.chat.completions.create(
            model=GROQ_EXTRACTION_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=4000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    cache_path = os.path.join(cache_dir, f"{workspace_id}_compare.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op)), media_type="text/event-stream")


async def chat_with_pdf(request, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db), cache_dir: str = None):
    cache_dir = UPLOAD_DIR if cache_dir is None else cache_dir
    try:
        # Enforce freemium limit for anonymous users
        if not current_user:
            if not x_session_id:
                raise HTTPException(status_code=401, detail="Authentication or Session ID required")
                
            # Freemium cap: 3 queries for anonymous users, then prompt to register
            anon_session = db.query(models.AnonymousSession).filter(models.AnonymousSession.id == x_session_id).first()
            if not anon_session:
                anon_session = models.AnonymousSession(id=x_session_id, query_count=0)
                db.add(anon_session)
                db.commit()
            if anon_session.query_count >= 3:
                raise HTTPException(status_code=402, detail="limit_reached")
            anon_session.query_count += 1
            db.commit()


        # Verify access
        for doc_id in request.doc_ids:
            if current_user:
                doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                    models.WorkspaceDocument.pinecone_doc_id == doc_id,
                    models.Workspace.firm_id == current_user.firm_id
                ).first()
            else:
                doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                    models.WorkspaceDocument.pinecone_doc_id == doc_id,
                    models.Workspace.session_id == x_session_id
                ).first()
                
            if not doc:
                raise HTTPException(status_code=403, detail="Access denied for one or more documents")

        if not request.doc_ids and not request.jurisdictions and not request.is_firm_search:
            return {"answer": "Please upload a document or select a Knowledge Base to get started.", "context_used": 0}
        if request.is_timeline:
            # Override query to specifically hunt for dates and timeline events
            query_vec = get_embedding("dates, deadlines, chronological sequence of events, important milestones, timeline")
            chunks_per_doc = 15 # Cap slightly lower to prevent RAM OOM
        else:
            query_vec = get_embedding(request.query)
            # Rollback context window: max 12 chunks per file to strictly prevent Cross-Encoder PyTorch SIGKILL on 512MB RAM
            chunks_per_doc = max(4, 12 // len(request.doc_ids)) if request.doc_ids else 6
        
        # Search Pinecone for top matches from EACH selected document individually to ensure diverse cross-document context
        matches = []
        
        if request.is_firm_search:
            if not current_user or not current_user.firm_id:
                raise HTTPException(status_code=403, detail="Firm Precedent Search requires a registered firm account.")
            firm_response = safe_query(index, query_vec, 20, True, {"firm_id": {"$eq": current_user.firm_id}}, PRODUCTION_PINECONE_NAMESPACE)
            matches.extend(firm_response.get('matches', []))
        else:
            for doc_id in request.doc_ids:
                query_response = safe_query(index, query_vec, chunks_per_doc, True, {"doc_id": {"$eq": doc_id}}, PRODUCTION_PINECONE_NAMESPACE)
                matches.extend(query_response.get('matches', []))
            
            # Regional Knowledge Base Sweeps (The Law)
            for jur in request.jurisdictions:
                jur_response = index.query(
                    vector=query_vec,
                    top_k=20, 
                    include_metadata=True,
                    filter={
                        "is_global": {"$eq": True},
                        "jurisdiction": {"$eq": jur}
                    }
                )
                matches.extend(jur_response.get('matches', []))
        
        if not matches:
            context = "No relevant context found in the document."
        else:
            query_text = request.query
            candidates = [r.get('metadata', {}).get('text', '') for r in matches]
            reranked = vo.rerank(query_text, candidates, model="rerank-2", top_k=12)
            top_matches = [matches[r.index] for r in reranked.results]

            # Force-anchor Page 1 definition contexts to bypass violent vector filtering failures
            page_one_anchors = []
            for doc_id in request.doc_ids:
                try:
                    md_path = os.path.join(cache_dir, f"{doc_id}.md")
                    if os.path.exists(md_path):
                        with open(md_path, "r") as f:
                            p1_text = f.read(1500) # Load the absolutely critical opening definitions
                            if p1_text.strip():
                                # We lack the original filename trivially here, but the LLM knows it's the primary doc
                                page_one_anchors.append(f"[Critical Page 1 Definitions / Header]\n{p1_text}")
                except Exception:
                    pass
                    
            context_pieces = page_one_anchors.copy()
            
            for r in top_matches:
                m = r.get('metadata', {})
                piece = f"[{m.get('filename')}, Page {m.get('page')}]\n{m.get('text')}"
                context_pieces.append(piece)
            context = "\n\n---\n\n".join(context_pieces)
            
            # Safety cap to prevent Groq 6000 TPM rate limit crash
            if len(context) > 18000:
                context = context[:18000] + "\n...[Context Truncated for System Limits]"
                
        if request.is_timeline:
            system_prompt = (
                "You are an expert legal assistant. Your task is to extract every single date, deadline, "
                "or chronological event mentioned in the provided document context and construct a comprehensive Timeline.\n\n"
                "Format the output strictly as a Markdown Chronological Timeline. For example:\n"
                "**May 4th, 2024:** The defendant signed the initial contract. [contract.pdf, Page 2]\n\n"
                "Order the events from oldest to most recent. If no dates are found, state that no chronological events could be extracted. "
                "You MUST cite the source filename and page number for every event.\n\n"
                f"DOCUMENT CONTEXT:\n{context}"
            )
        else:
            system_prompt = (
                "You are a brilliant, highly analytical legal and real estate assistant (Real Estate Meta / REM). "
                "You are strictly prohibited from hallucinating or guessing outside the provided document context. "
                "You must answer questions based SOLELY on the provided documents; however, you ARE permitted to make direct logical deductions from the text. "
                "If the answer cannot be found or logically deduced from the provided context, you MUST state: 'I cannot answer this based on the provided documents.' "
                "You MUST explicitly cite the exact source of your answers at the end of each relevant claim, using the exact format: [Filename, Page X]. "
                "For example: 'The tenant signed the lease on May 4th [contract.pdf, Page 2].'\n\n"
                "CRITICAL INSTRUCTION: The user is a professional reviewing corporate documents, Shareholder Agreements, and Commercial Real Estate Leases. You must expertly analyze clauses, identities, liabilities, and terms. You MUST answer these questions fully and accurately based on the context.\n\n"
                "Be precise, objective, and maintain a professional tone. Do not provide prescriptive legal advice.\n\n"
                f"DOCUMENT CONTEXT:\n{context}"
            )
        
        def generate():
            response = groq_client.chat.completions.create(
                model=GROQ_EXTRACTION_MODEL, # Massive 70B reasoning engine, 30,000 TPM limit
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': request.query}
                ],
                stream=True
            )
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
                    
        return StreamingResponse(generate(), media_type="text/event-stream")
        
        return StreamingResponse(generate(), media_type="text/event-stream")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


