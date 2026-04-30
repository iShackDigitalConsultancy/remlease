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

CRITICAL RULES:
1. field_type must be accurate:
   extracted = directly from document
   derived = calculated from extracted
   inferred = logical conclusion from multiple clauses — include all evidence
2. Never use 'Not specified' — use missing_critical_fields with searched_locations instead
3. Every value needs source_evidence with document, clause, text, page
4. Confidence scores:
   0.9+ = explicit in text
   0.7-0.9 = requires inference
   below 0.7 = uncertain, flag review
5. requires_human_review = true if any confidence below 0.7 OR any Critical risk
6. For dependency_map and control_analysis use field_type: inferred and include ALL supporting source evidence
7. action_items must have specific due dates calculated from extracted dates

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
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {
                "error": "Failed to parse intelligence report",
                "raw_response": raw[:500]
            }
    except Exception as e:
        print(f"Error in reduce phase: {e}")
        return {"error": str(e)}

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
