import os
import json
import re
from datetime import datetime
from dependencies import UPLOAD_DIR, groq_client
from services.map_reduce import batch_document

def load_workspace_caches(workspace_id: str) -> dict:
    """Load all available cache files for a workspace. Returns dict with keys: expiries, fundamental_terms, audit"""
    caches = {}
    
    for report_type in ["extract_expiries", "fundamental_terms", "audit"]:
        cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_{report_type}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    caches[report_type] = json.load(f)
            except Exception:
                pass
    
    return caches

def build_cache_context(caches: dict) -> str:
    """Converts cached JSON into a structured text summary to inject into the AI prompt
    as additional context alongside the raw document text.
    This prevents re-extracting data we already have."""
    if not caches:
        return "No existing cached reports available."
    return json.dumps(caches, indent=2)

async def run_intelligence_pipeline(workspace_id: str, doc_ids: list, filenames: list, full_text: str, caches: dict, db, doc_map: dict = None) -> dict:
    # Build context from caches
    cache_context = build_cache_context(caches)

    # TWO-PASS AI pipeline
    
    # PASS 1: MAP
    map_instruction = """You are a senior legal analyst reviewing commercial lease and franchise agreements.
PREMISES SIZE: Look specifically for m², square metres, or sqm values near the words PREMISES, SHOP, or AREA. These often appear in the schedule or preamble as '+/- 175.3m²' or similar format.

Extract from this section:
1. All clause references with exact text (quote under 20 words)
2. All defined terms and definitions
3. All cross-references to annexures
4. Financial figures with clause source
5. Control rights and approval requirements
6. Conditions attached to any rights
7. Any explicit N/A, None, or exclusions
Return structured JSON with clause references for every extracted value.
NEVER return 'Not specified' — if data is absent note which locations were searched."""

    # We use batch_document from map_reduce to chunk properly
    batches = batch_document(full_text, target_batch_size=15000)
    
    map_results = []
    for i, batch in enumerate(batches):
        prompt = f"{map_instruction}\n\nDocument Text (Part {i+1}):\n{batch}"
        
        try:
            resp = groq_client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.0,
                max_tokens=4000
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
            map_results.append(raw)
        except Exception as e:
            print(f"Error in map phase chunk {i}: {e}")
            map_results.append("{}")

    # PASS 2: REDUCE
    reduce_instruction = """You are a senior occupier intelligence analyst. Using the extracted clause data and existing extraction cache context provided, produce the complete Occupier Intelligence Report.

STRICT ANTI-HALLUCINATION RULES:
1. NEVER invent numbers. If a figure cannot be found in the source documents or calculated from extracted figures, set the field to null and add an assumption entry explaining why.
2. premises_size_sqm must come from the PREMISES clause in the lease schedule. Look for 'm²' or 'square metres'.
3. renewal_fee must be expressed as a formula if stated as a percentage or ratio, not as a calculated amount. Example: '100% of then-current upfront license fee (currently R120,000)'
4. monthly_variable_estimate and exit_cost_estimate must be null unless explicitly calculable from extracted figures. Add assumption entries instead.
5. total_occupancy_exposure fields must only contain values derivable from extracted numbers. If turnover is unknown, variable costs cannot be estimated — say so in assumptions.
6. premises_size_sqm: Search specifically for numeric values followed by m², sqm, or 'square metres' near any PREMISES definition. Common formats: '175.3m²', '+/- 175m²', 'approximately 175 square metres'. If found, use the exact number. If genuinely not found after searching main body, schedule, preamble and annexures, add to missing_critical_fields.
7. renewal_fee: If the renewal fee is stated as a percentage of another fee (e.g. '100% of the then current Upfront License Fee'), express it EXACTLY as that formula with the current fee amount in brackets. Example output: '100% of then-current Upfront License Fee (currently R120,000.00 per Annexure A item 1)'. Do NOT say Not specified if a formula is stated — the formula IS the specification.
8. current_monthly_rent: This is the BASE RENT payable monthly. It must NOT be confused with the security deposit, key deposit, or any lump sum payment. The monthly rent is typically stated as 'R X per m² per month' multiplied by the premises size, OR as a fixed monthly amount in the rental schedule. The security deposit is a once-off amount held by the landlord — it is NOT rent.

CONTRADICTIONS RULE:
Only populate contradictions when you have direct evidence from BOTH documents showing different values for the same field. Both values must appear in source_evidence. NEVER fabricate a contradiction. If you cannot find both values in the source text, do not add a contradiction entry.
A value of 'Not specified' or 'null' in one document does NOT constitute a contradiction with a value in another document. Contradictions only occur when BOTH documents explicitly state DIFFERENT values for the same field.

SOURCE EVIDENCE RULE:
The 'text' field in every source_evidence entry must be an EXACT verbatim quote from the document, under 25 words. Do NOT paraphrase or summarise. Do NOT write 'The landlord has approval rights over...' if the contract says 'The Lessee shall not cede, transfer, pledge or in any way dispose of...' Copy the actual words from the contract.

CONFIDENCE CALIBRATION:
0.95+ = exact figure found verbatim in text
0.85-0.94 = figure found but requires minor calculation (e.g. date arithmetic)
0.70-0.84 = figure inferred from multiple clauses with supporting evidence
below 0.70 = uncertain — flag for review
Do NOT assign low confidence to values that are clearly and explicitly stated in the document text.

ACTION ITEMS TIMING RULE:
due_date for action items must be set BEFORE the relevant deadline, not at it.
For renewal notices: set due_date to the EARLIEST notice date (latest start of notice window).
Example: if notice window is 2027-10-01 to 2028-01-01, set due_date to 2027-10-01.
For lease expiry with no renewal: set due_date to 12 months before expiry to allow renegotiation time.

CRITICAL RULES:
1. field_type must be accurate:
   extracted = directly from document
   derived = calculated from extracted
   inferred = logical conclusion from multiple clauses — include all evidence
2. Never use 'Not specified' — use missing_critical_fields with searched_locations instead
3. Every value needs source_evidence with document, clause, text, page
4. requires_human_review = true if any confidence below 0.70 OR any Critical risk
5. For dependency_map and control_analysis use field_type: inferred and include ALL supporting source evidence

Output ONLY the Intelligence Report JSON. It must match exactly this schema:

{
  "workspace_id": "uuid",
  "generated_at": "ISO datetime",
  "schema_version": "1.0",
  "documents_analysed": [
    {
      "filename": "string",
      "doc_type": "Lease | Franchise Agreement",
      "extraction_confidence": 0.85
    }
  ],

  "review_status": {
    "requires_human_review": true,
    "review_reason": "string",
    "approved_by": null,
    "approved_at": null
  },

  "dependency_map": {
    "field_type": "inferred",
    "lease_depends_on_franchise": true,
    "franchise_depends_on_lease": true,
    "franchisor_controls_lease_assignment": true,
    "term_mismatch_days": 1,
    "term_mismatch_flag": true,
    "dependency_notes": "string",
    "confidence": 0.9,
    "source_evidence": [
      {
        "document": "filename.pdf",
        "clause": "clause 16.6",
        "text": "exact quote under 20 words",
        "page": "5"
      }
    ]
  },

  "risk_summary": [
    {
      "risk_id": "RISK-001",
      "field_type": "derived | inferred",
      "category": "Renewal | Financial | Control | Compliance | Operational",
      "severity": "Critical | High | Medium | Low",
      "title": "string",
      "description": "string",
      "recommendation": "string",
      "confidence": 0.9,
      "source_evidence": [
        {
          "document": "filename.pdf",
          "clause": "clause ref",
          "text": "exact quote under 20 words",
          "page": "page number"
        }
      ]
    }
  ],

  "financial_model": {
    "lease_costs": {
      "field_type": "extracted",
      "base_rent_per_sqm": "string",
      "premises_size_sqm": "string",
      "current_monthly_rent": "string",
      "escalation_rate": "string",
      "escalation_type": "compound | simple",
      "projected_rent_at_expiry": "string",
      "confidence": 0.95,
      "source_evidence": [
        {
          "document": "filename.pdf",
          "clause": "Schedule item 8",
          "text": "exact quote",
          "page": "3"
        }
      ]
    },
    "franchise_costs": {
      "field_type": "extracted",
      "upfront_license_fee": "string",
      "monthly_franchise_fee_pct": "string",
      "marketing_fee_pct": "string",
      "renewal_fee": "string",
      "confidence": 0.9,
      "source_evidence": [
        {
          "document": "filename.pdf",
          "clause": "Annexure A items 1-4",
          "text": "exact quote",
          "page": "32"
        }
      ]
    },
    "total_occupancy_exposure": {
      "field_type": "derived",
      "monthly_fixed": "string",
      "monthly_variable_estimate": "string",
      "renewal_cost_exposure": "string",
      "exit_cost_estimate": "string"
    },
    "assumptions": [
      {
        "assumption": "string",
        "impact": "string",
        "confidence": 1.0
      }
    ]
  },

  "control_analysis": {
    "field_type": "inferred",
    "lease_control": {
      "party": "string",
      "approval_rights": ["string"],
      "source_evidence": [{"document":"","clause":"","text":"","page":""}]
    },
    "brand_control": {
      "party": "string",
      "approval_rights": ["string"],
      "source_evidence": [{"document":"","clause":"","text":"","page":""}]
    },
    "assignment_control": {
      "can_tenant_assign_lease": false,
      "franchisor_approval_required": true,
      "source_evidence": [{"document":"","clause":"","text":"","page":""}]
    }
  },

  "action_items": [
    {
      "priority": "Critical | High | Medium | Low",
      "field_type": "derived | inferred",
      "owner": "Tenant | Landlord | Franchisor | Legal | Finance",
      "action": "string",
      "due_date": "YYYY-MM-DD or null",
      "reason": "string",
      "source_evidence": [{"document":"","clause":"","text":"","page":""}]
    }
  ],

  "data_quality": {
    "overall_confidence": 0.85,
    "missing_critical_fields": [
      {
        "field": "string",
        "document": "string",
        "searched_locations": [
          "main body","schedules",
          "annexures","definitions"
        ],
        "impact": "string"
      }
    ],
    "low_confidence_fields": [
      {
        "field": "string",
        "value": "string",
        "confidence": 0.0,
        "reason": "string"
      }
    ],
    "contradictions": [
      {
        "field": "string",
        "field_type": "extracted",
        "document_a_value": "string",
        "document_b_value": "string",
        "severity": "Critical | Warning"
      }
    ]
  }
}"""

    reduce_payload = (
        f"=== WORKSPACE ID ===\n{workspace_id}\n\n"
        f"=== DOCUMENTS BEING ANALYSED ===\n"
        + "\n".join([f"- {f}" for f in filenames])
        + f"\n\n=== CACHE CONTEXT ===\n{cache_context}\n\n"
    )
    if doc_map:
        reduce_payload += f"=== DOCUMENT MAP ===\n{json.dumps(doc_map, indent=2)}\n\n"
        
    reduce_payload += f"=== EXTRACTED DATA (MAP PHASE) ===\n"
    for idx, res in enumerate(map_results):
        reduce_payload += f"--- Part {idx+1} ---\n{res}\n\n"
        
    prompt = f"{reduce_instruction}\n\n{reduce_payload}"
    
    try:
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=8000,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content.strip()
        try:
            report = json.loads(raw)
            report = validate_intelligence_report(report, caches, full_text)
            return report
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                report = json.loads(match.group())
                report = validate_intelligence_report(report, caches, full_text)
                return report
            return {
                "error": "Failed to parse intelligence report",
                "raw_response": raw[:500]
            }
    except Exception as e:
        print(f"Error in reduce phase: {e}")
        return {"error": str(e)}

def validate_intelligence_report(
    report: dict, 
    caches: dict, 
    full_text: str
) -> dict:
    """
    Deterministic post-processing validator.
    Runs after AI JSON parsing, before cache write.
    The AI analyses. The validator polices.
    """
    
    # FIX 1 — Remove invalid contradictions
    if "data_quality" in report:
        valid_contradictions = []
        for c in report["data_quality"].get("contradictions", []):
            val_a = c.get("document_a_value")
            val_b = c.get("document_b_value")
            null_values = {None, "null", "Not specified", "", "not specified", "N/A", "n/a"}
            if val_a not in null_values and val_b not in null_values and val_a != val_b:
                valid_contradictions.append(c)
        report["data_quality"]["contradictions"] = valid_contradictions

    # FIX 2 — Convert all "null" strings to None
    def clean_nulls(obj):
        if isinstance(obj, dict):
            return {k: clean_nulls(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_nulls(i) for i in obj]
        elif obj in ("null", "Null", "NULL", "Not specified", "not specified"):
            return None
        return obj
    
    report = clean_nulls(report)

    # FIX 3 — Rent vs deposit confusion
    fm = report.get("financial_model", {})
    lc = fm.get("lease_costs", {})
    current_rent = lc.get("current_monthly_rent")
    deposit_indicators = ["deposit", "security deposit", "key deposit", "Deposit"]
    
    if current_rent:
        rent_str = str(current_rent).lower()
        rent_evidence = []
        for ev in lc.get("source_evidence", []):
            ev_text = str(ev.get("text","")).lower()
            if any(d in ev_text for d in deposit_indicators):
                rent_evidence.append(ev)
        
        ft_cache = caches.get("fundamental_terms", {})
        security_deposit = None
        if isinstance(ft_cache, list) and ft_cache:
            security_deposit = ft_cache[0].get("security_deposit")
        elif isinstance(ft_cache, dict):
            items = ft_cache.get("fundamental_terms", [])
            if items and isinstance(items, list):
                security_deposit = items[0].get("security_deposit")
        
        rent_clean = str(current_rent).replace(" ", "").replace(",", "")
        deposit_clean = str(security_deposit or "").replace(" ", "").replace(",", "")
        
        if rent_evidence or (deposit_clean and deposit_clean in rent_clean):
            report.setdefault("financial_model", {}).setdefault("lease_costs", {})["current_monthly_rent"] = None
            assumptions = report.setdefault("financial_model", {}).setdefault("assumptions", [])
            assumptions.append({
                "assumption": "Monthly rent could not be confirmed — value may have been confused with security deposit. Manual verification required.",
                "impact": "Current monthly rent shown as null pending verification.",
                "confidence": 1.0
            })
            report["financial_model"]["assumptions"] = assumptions

    # FIX 4 — Premises size sanity check
    premises_sqm = lc.get("premises_size_sqm")
    if premises_sqm is None:
        import re
        sqm_pattern = re.compile(r'(\d+\.?\d*)\s*m[²2]|(\d+\.?\d*)\s*square\s*met', re.IGNORECASE)
        matches = sqm_pattern.findall(full_text)
        if matches:
            for match in matches:
                val = match[0] or match[1]
                if val and float(val) > 10:
                    report.setdefault("financial_model", {}).setdefault("lease_costs", {})["premises_size_sqm"] = f"{val}m²"
                    break
        
        dq = report.get("data_quality", {})
        missing = dq.get("missing_critical_fields", [])
        already_flagged = any("premises" in str(m.get("field","")).lower() for m in missing)
        if not already_flagged:
            missing.append({
                "field": "premises_size_sqm",
                "document": "Lease Agreement",
                "searched_locations": ["main body", "schedule", "preamble", "annexures"],
                "impact": "Cannot calculate total monthly rent from rate per m² without premises size"
            })
            report.setdefault("data_quality", {})["missing_critical_fields"] = missing

    # FIX 5 — Renewal fee formula check
    fc = fm.get("franchise_costs", {})
    renewal_fee = fc.get("renewal_fee")
    if renewal_fee is None:
        import re
        renewal_pattern = re.compile(r'renewal\s+fee|upfront\s+licen[sc]e\s+fee', re.IGNORECASE)
        if renewal_pattern.search(full_text):
            report.setdefault("data_quality", {}).setdefault("missing_critical_fields", []).append({
                "field": "renewal_fee",
                "document": "Franchise Agreement",
                "searched_locations": ["main body", "Annexure A", "schedules", "definitions"],
                "impact": "Renewal cost exposure cannot be calculated"
            })

    return report

async def generate_intelligence_report(workspace_id: str, doc_ids: list, filenames: list, full_text: str, db, doc_map: dict = None) -> dict:
    """Generate the full Intelligence Report"""
    # Load existing caches
    caches = load_workspace_caches(workspace_id)
    
    # Build the report using AI
    report = await run_intelligence_pipeline(
        workspace_id=workspace_id,
        doc_ids=doc_ids,
        filenames=filenames,
        full_text=full_text,
        caches=caches,
        db=db,
        doc_map=doc_map
    )
    
    # Ensure generated_at and workspace_id are injected
    report["workspace_id"] = workspace_id
    report["generated_at"] = datetime.utcnow().isoformat() + "Z"
    
    # Cache result to {workspace_id}_intelligence_report.json
    cache_path = os.path.join(UPLOAD_DIR, f"{workspace_id}_intelligence_report.json")
    with open(cache_path, "w") as f:
        json.dump(report, f, indent=2)
    
    return report
