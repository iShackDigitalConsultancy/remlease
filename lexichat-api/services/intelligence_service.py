import os
import json
import re
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from dependencies import UPLOAD_DIR, groq_client, index, vo
import models
from sqlalchemy.orm import Session
from fastapi import Depends, Header
from typing import List, Optional
from services.map_reduce import run_feature_gated_pipeline
from auth import get_current_user_optional
from database import get_db

async def cached_pipeline_stream(cache_path: str, force_refresh: bool, pipeline_gen):
    if not force_refresh and os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached = json.load(f)
        yield f"data: {json.dumps({'status': 'complete', 'data': cached})}\n\n"
        return
        
    async for chunk in pipeline_gen:
        yield chunk
        if chunk.startswith("data: "):
            try:
                data_obj = json.loads(chunk[6:])
                if data_obj.get("status") == "complete":
                    with open(cache_path, "w") as f:
                        json.dump(data_obj.get("data"), f)
            except Exception:
                pass


def get_embedding(text: str):
    return vo.embed([text], model="voyage-law-2").embeddings[0]

def analyze_document_brief(doc_id: str, filename: str, sample_text: str) -> dict:
    """Run a structured Groq extraction and return a JSON brief."""
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
            model='llama-3.3-70b-versatile',
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


def analyze_document_brief_background(doc_id: str, filename: str, sample_text: str):
    try:
        brief = analyze_document_brief(doc_id, filename, sample_text)
        with open(os.path.join(UPLOAD_DIR, f"{doc_id}_brief.json"), "w") as f:
            json.dump(brief, f)
    except Exception as e:
        print(f"Background brief extraction failed: {e}")


def get_document_brief(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
        
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_brief.json")
    if not os.path.exists(file_path):
        return {"brief": None}
        
    with open(file_path, "r") as f:
        brief = json.load(f)
    return {"brief": brief}


async def document_audit(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
        file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}.md")
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
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=2000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    workspace_id = doc.workspace_id
    cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_audit.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op)), media_type="text/event-stream")


async def extract_timeline(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}.md")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        doc_text = f.read()
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
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=3000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_fundamental_terms.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op)), media_type="text/event-stream")


async def extract_expiries(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}.md")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        doc_text = f.read()
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
                '{\n      "document": "' + fname + '",\n'
                '      "doc_type": "Lease Agreement or Franchise Agreement",\n'
                '      "legal_commencement_date": "YYYY-MM-DD or null",\n'
                '      "rental_commencement_date": "YYYY-MM-DD or null",\n'
                '      "beneficial_occupation_date": "YYYY-MM-DD or null",\n'
                '      "ai_extracted_expiry_date": "YYYY-MM-DD or null",\n'
                '      "duration_years": 5,\n'
                '      "renewal_type": "manual_renewal",\n'
                '      "renewal_period_years": null,\n'
                '      "ai_extracted_renewal_notice_latest": "YYYY-MM-DD or null",\n'
                '      "notice_min_months": 6,\n'
                '      "notice_max_months": 9,\n'
                '      "requires_notice": true,\n'
                '      "notice_party": "tenant",\n'
                '      "renewal_action_required": true,\n'
                '      "renewal_clause_text": "verbatim excerpt under 50 words",\n'
                '      "clause_confidence": 0.95,\n'
                '      "action_required": "specific action text"\n'
                '    }'
            )

            map_task = """Extract all dates, deadlines, and timeframes from this section. You MUST extract ALL of these specific fields if present:
1. legal_commencement_date — when the lease legally begins.
2. beneficial_occupation_date — when tenant gets early access.
3. rental_commencement_date — when rent starts being paid.
4. ai_extracted_expiry_date — when it ends (extract raw value, do not calculate).
RENEWAL EXTRACTION RULES:
Extract ONLY what is explicitly stated.
Do NOT calculate dates — extract raw values.

1. renewal_type: Must be exactly one of:
   manual_renewal | automatic_renewal | automatic_renewal_with_opt_out |
   tenant_option | landlord_option | mutual_option | no_renewal_right | unknown
   
   Classification guide:
   - 'auto-renews unless...' = automatic_renewal_with_opt_out
   - 'either party may cancel' = automatic_renewal_with_opt_out
   - 'tenant may renew by notice' = manual_renewal
   - 'landlord may renew' = landlord_option
   - 'shall automatically renew' = automatic_renewal
   - 'no renewal' or 'N/A' = no_renewal_right

   CRITICAL: If the document contains any of:
   - 'N/A' adjacent to renewal option
   - 'no renewal' or 'no option to renew'
   - 'option to renew: N/A'
   - Schedule item explicitly showing N/A
   Then renewal_type MUST be 'no_renewal_right'.
   Do NOT infer a renewal option unless 
   explicitly stated in a renewal clause.
   The absence of a renewal clause means no_renewal_right.
   A holdover/month-to-month clause is NOT
   a renewal option — it is a different 
   legal mechanism.

2. notice_min_months: Integer.
   - 'not less than 6 months' = notice_min_months: 6
   - 'at least 6 months before expiry' = notice_min_months: 6
   If not stated set to null.

3. notice_max_months: Integer or null.
   - 'not more than 9 months' = notice_max_months: 9
   Many agreements have no upper bound —
   set to null if only minimum stated.

4. requires_notice: true/false.
   false for automatic renewal.
   true for manual, opt_out, tenant_option.

5. notice_party: tenant | landlord | 
   either | mutual
   Who must give notice.

6. renewal_action_required: true/false.
   false if automatic with no opt-out needed.

7. renewal_period_years: Integer or null.
   The renewal PERIOD — may differ from 
   original term. e.g. original 5 years,
   renewal 3 years.

8. renewal_clause_text: Copy verbatim up to
   50 words of the renewal clause.
   This is for auditability.
   
   Do NOT confuse holdover clauses with 
   renewal options. A holdover clause 
   ('deemed to lease on monthly basis') 
   is what happens AFTER expiry with no 
   renewal — it is NOT a renewal mechanism.
   renewal_clause_text must quote the actual 
   renewal option clause, not the holdover.

9. clause_confidence: Float 0.0-1.0.
   0.95+ = clause found verbatim and clear
   0.70-0.94 = clause found but ambiguous
   below 0.70 = inferred, not explicit

10. legal_commencement_date: Date as written. YYYY-MM-DD format.
    rental_commencement_date: Date as written. YYYY-MM-DD format.
    beneficial_occupation_date: Date as written. YYYY-MM-DD format.
    CRITICAL: Do NOT confuse these three. If only one 'Commencement Date' is specified, it is typically legal_commencement_date.
    Do NOT use rental schedule dates as legal_commencement_date.
    
    For FRANCHISE AGREEMENTS specifically:
    Annexure A contains Financial and Other Terms.
    You MUST search for and extract:
    - Item 7 or 'Commencement Date' in Annexure A
      → this is legal_commencement_date
    - Item 8 or 'Duration' in Annexure A  
      → this is duration_years

11. ai_extracted_expiry_date: Date as written.
    YYYY-MM-DD. null if not explicit.

12. duration_years: Integer. Extract from
    'period of X years' clause.

13. ai_extracted_renewal_notice_latest: YYYY-MM-DD.
    The AI-interpreted candidate notice deadline based on the extracted clause text. Do NOT calculate mathematically, extract what the clause suggests.

CRITICAL ANTI-CONTAMINATION RULE:
You are processing ONLY this document. Do not infer, borrow, compare, or import dates, clauses, names, or renewal terms from any other document.

All other date calculations will be 
performed by the deterministic date engine.
Do NOT calculate renewal deadlines.
Do NOT calculate expiry from commencement.
Extract raw values only."""

            reduce_task = f"""You MUST produce a single expiry entry for the document named '{fname}' based on the provided map results.
CRITICAL ANTI-CONTAMINATION RULE:
You are processing ONLY this document. Do not infer, borrow, compare, or import dates, clauses, names, or renewal terms from any other document.

CRITICAL: The 'document' field in the expiry entry MUST be exactly: '{fname}'
Do NOT write 'Unknown', 'Document 1', or any invented name.
For each document entry you MUST populate:
- doc_type: Must be exactly one of: 'Lease Agreement' or 'Franchise Agreement'. Determine from the document content and filename. A franchise agreement typically contains terms like 'Franchisor', 'Franchisee', 'Franchise Fee'. A lease agreement typically contains terms like 'Lessor', 'Lessee', 'monthly rental', 'premises'.
Find the Expiry Date, Renewal Notice Deadline, and relevant Notification Clause for each document.
For franchise agreements: if any map result contains a commencement date from Annexure A, use it as legal_commencement_date. Annexure A data takes priority over body text for financial and date terms.
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
If a date is vague or missing, make your best guess for the date format "YYYY-MM-DD". Return ONLY the JSON object."""

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
                        model='llama-3.3-70b-versatile',
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
                                        
                                    # Post-processing date deterministic engine
                                    
                                    # Cache check (Fundamental terms)
                                    ft_cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_fundamental_terms.json")
                                    if os.path.exists(ft_cache_path):
                                        try:
                                            with open(ft_cache_path, "r") as f:
                                                ft_cache = json.load(f)
                                            ft_items = ft_cache.get("fundamental_terms", [])
                                            if isinstance(ft_items, dict):
                                                ft_items = [ft_items]
                                            
                                            if not exp.get("legal_commencement_date"):
                                                doc_type = exp.get("doc_type","")
                                                if "Franchise" in doc_type:
                                                    for ft in ft_items:
                                                        if "Franchise" in str(ft.get("doc_type","")):
                                                            ft_comm = ft.get("commencement_date") or ft.get("franchise_terms", {}).get("commencement_date")
                                                            ft_expiry = ft.get("expiry_date") or ft.get("franchise_terms", {}).get("expiry_date")
                                                            if ft_comm:
                                                                exp["legal_commencement_date"] = ft_comm
                                                                exp["commencement_source"] = "fundamental_terms_cache"
                                                                if ft_expiry and ft_comm:
                                                                    try:
                                                                        c = datetime.strptime(ft_comm, "%Y-%m-%d")
                                                                        e = datetime.strptime(ft_expiry, "%Y-%m-%d")
                                                                        exp["duration_years"] = (e.year - c.year)
                                                                    except Exception:
                                                                        pass
                                                                break
                                        except Exception:
                                            pass
                                            
                                    ai_expiry = exp.get("ai_extracted_expiry_date")
                                    legal_comm = exp.get("legal_commencement_date")
                                    rental_comm = exp.get("rental_commencement_date")
                                    bo_comm = exp.get("beneficial_occupation_date")
                                    
                                    if legal_comm and exp.get("duration_years"):
                                        calc = calculate_expiry(legal_comm, exp.get("duration_years"), "day_before")
                                        exp["deterministic_expiry_date"] = calc["date"]
                                        exp["expiry_calculation_basis"] = calc["basis"] + (" (commencement from fundamental_terms cache)" if exp.get("commencement_source") == "fundamental_terms_cache" else "")
                                        exp["expiry_date"] = exp["deterministic_expiry_date"]
                                    else:
                                        exp["expiry_date"] = ai_expiry
                                        
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
                                        window = calculate_renewal_window(expiry, min_m, max_m or min_m)
                                        exp["deterministic_renewal_notice_earliest"] = window["renewal_notice_earliest"]
                                        exp["deterministic_renewal_notice_latest"] = window["renewal_notice_latest"]
                                        exp["renewal_notice_earliest"] = window["renewal_notice_earliest"]
                                        exp["renewal_notice_latest"] = window["renewal_notice_latest"]
                                        exp["renewal_window_basis"] = window["basis"]
                                        
                                        status = check_renewal_window_status(expiry, min_m, max_m or min_m)
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
                                        bo_check = is_beneficial_occupation_significant(bo_comm, legal_comm)
                                        exp["beneficial_occupation_flag"] = bo_check["flag"]
                                        exp["beneficial_occupation_days"] = bo_check["days_difference"]
                                        
                                    v_flags = exp.get("validation_flags", [])
                                    engine_flags = validate_dates(
                                        legal_commencement=legal_comm,
                                        rental_commencement=rental_comm,
                                        beneficial_occupation=bo_comm,
                                        expiry=expiry,
                                        renewal_latest=exp.get("deterministic_renewal_notice_latest")
                                    )
                                    if engine_flags:
                                        v_flags.extend(engine_flags)
                                        
                                    ai_latest = exp.get("ai_extracted_renewal_notice_latest")
                                    det_latest = exp.get("deterministic_renewal_notice_latest")
                                    if ai_latest and det_latest:
                                        try:
                                            a_d = datetime.strptime(ai_latest, "%Y-%m-%d").date()
                                            d_d = datetime.strptime(det_latest, "%Y-%m-%d").date()
                                            if abs((a_d - d_d).days) > 7:
                                                v_flags.append("AI renewal notice deadline differs materially from deterministic calculation")
                                        except ValueError:
                                            pass
                                            
                                    exp["validation_flags"] = v_flags
                                    
                                    dt = exp.get("doc_type", "")
                                    if len(str(dt)) > 30 or dt not in ["Lease Agreement", "Franchise Agreement", "Sale Agreement", "Non-Disclosure Agreement"]:
                                        exp["doc_type"] = "Lease Agreement"
                                        
                                    final_expiries.append(exp)
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

    cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_extract_expiries.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, pipeline_wrapper()), media_type="text/event-stream")

async def portfolio_overview(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    from datetime import datetime
    if current_user:
        workspaces = db.query(models.Workspace).filter(models.Workspace.firm_id == current_user.firm_id).all()
    elif x_session_id:
        workspaces = db.query(models.Workspace).filter(models.Workspace.session_id == x_session_id).all()
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    final_data = []
    
    for ws in workspaces:
        cache_path = os.path.join(UPLOAD_DIR, f"{ws.id}_extract_expiries.json")
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
                
                expiries = cached.get("expiries", [])
                for exp in expiries:
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
                        "doc_type": doc_type,
                        "commencement_date": exp.get("legal_commencement_date") or exp.get("commencement_date") or exp.get("raw_commencement_date"),
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




async def document_compare(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            file_path = os.path.join(UPLOAD_DIR, f"{candidate_id}.md")
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
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=4000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_compare.json")
    return StreamingResponse(cached_pipeline_stream(cache_path, payload.force_refresh, run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op)), media_type="text/event-stream")


async def chat_with_pdf(request, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            firm_response = index.query(
                vector=query_vec,
                top_k=20,
                include_metadata=True,
                filter={"firm_id": {"$eq": current_user.firm_id}}
            )
            matches.extend(firm_response.get('matches', []))
        else:
            for doc_id in request.doc_ids:
                query_response = index.query(
                    vector=query_vec,
                    top_k=chunks_per_doc,
                    include_metadata=True,
                    filter={"doc_id": {"$eq": doc_id}}
                )
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
                    md_path = os.path.join(UPLOAD_DIR, f"{doc_id}.md")
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
                model='llama-3.3-70b-versatile', # Massive 70B reasoning engine, 30,000 TPM limit
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


