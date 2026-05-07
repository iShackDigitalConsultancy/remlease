from typing import Optional

# Scoring weights
WEIGHTS = {
    "no_lease_renewal": 35,
    "franchise_outlives_lease": 25,
    "renewal_window_expired": 40,
    "renewal_window_closing_soon": 20,
    "manual_renewal_required": 10,
    "mutual_renewal_dependency": 15,
    "missing_commencement_data": 10,
    "low_clause_confidence": 15,
    "franchise_unprotected": 30,
    "no_renewal_either": 20,
    "days_until_expiry_critical": 35,
    "days_until_expiry_high": 20,
    "days_until_expiry_medium": 10,
}

def score_to_severity(score: int) -> str:
    if score >= 75:
        return "critical"
    elif score >= 50:
        return "high"
    elif score >= 25:
        return "medium"
    return "low"

def normalize_score(raw: int) -> int:
    return min(100, max(0, raw))

def calculate_renewal_risk_score(
    expiries: list,
    mismatch: dict
) -> dict:
    """
    Scores renewal risk for a workspace.
    Higher = more risk.
    """
    raw_score = 0
    factors = []
    
    lease = next(
        (e for e in expiries 
         if e.get("doc_type") == 
         "Lease Agreement"), None)
    franchise = next(
        (e for e in expiries 
         if e.get("doc_type") == 
         "Franchise Agreement"), None)
    
    # No lease renewal rights
    if lease and lease.get(
        "renewal_type") == "none":
        raw_score += WEIGHTS[
            "no_lease_renewal"]
        factors.append(
            "Lease contains no renewal rights"
        )
    
    # Franchise unprotected
    mismatch_type = mismatch.get(
        "mismatch_type")
    if mismatch_type == \
       "franchise_renewal_unprotected":
        raw_score += WEIGHTS[
            "franchise_unprotected"]
        factors.append(
            "Franchise renewal exists but "
            "lease has no renewal right"
        )
    
    # Neither can renew
    if mismatch_type == "no_renewal":
        raw_score += WEIGHTS[
            "no_renewal_either"]
        factors.append(
            "Neither agreement has "
            "renewal rights"
        )
    
    # Franchise outlives lease
    rules = mismatch.get(
        "rules_triggered", [])
    rule_ids = [r.get("rule") 
                for r in rules]
    if "RULE-002" in rule_ids:
        raw_score += WEIGHTS[
            "franchise_outlives_lease"]
        factors.append(
            "Franchise rights extend beyond "
            "lease expiry date"
        )
    
    # Renewal window status
    for exp in expiries:
        status = exp.get(
            "renewal_window_status")
        days = exp.get(
            "days_until_expiry", 9999)
        doc = exp.get("document", "")
        
        if status == "too_late_rights_lapsed":
            raw_score += WEIGHTS[
                "renewal_window_expired"]
            factors.append(
                f"Renewal window expired: "
                f"{doc}"
            )
        elif status == "window_closing_soon":
            raw_score += WEIGHTS[
                "renewal_window_closing_soon"]
            factors.append(
                f"Renewal window closing "
                f"soon: {doc}"
            )
        
        # Days until expiry
        if days is not None:
            if days <= 180:
                raw_score += WEIGHTS[
                    "days_until_expiry_critical"]
                factors.append(
                    f"Expiry within 6 months: "
                    f"{doc}"
                )
            elif days <= 365:
                raw_score += WEIGHTS[
                    "days_until_expiry_high"]
                factors.append(
                    f"Expiry within 12 months: "
                    f"{doc}"
                )
            elif days <= 730:
                raw_score += WEIGHTS[
                    "days_until_expiry_medium"]
                factors.append(
                    f"Expiry within 24 months: "
                    f"{doc}"
                )
    
    # Manual renewal required
    for exp in expiries:
        if exp.get("renewal_type") == "manual":
            raw_score += WEIGHTS[
                "manual_renewal_required"]
            factors.append(
                f"Manual renewal notice "
                f"required: "
                f"{exp.get('document','')}"
            )
    
    # Missing commencement data
    for exp in expiries:
        if not exp.get(
            "raw_commencement_date"):
            raw_score += WEIGHTS[
                "missing_commencement_data"]
            factors.append(
                f"Missing commencement date: "
                f"{exp.get('document','')}"
            )
    
    # Low clause confidence
    for exp in expiries:
        conf = exp.get("clause_confidence")
        if conf is not None and conf < 0.7:
            raw_score += WEIGHTS[
                "low_clause_confidence"]
            factors.append(
                f"Low extraction confidence "
                f"({conf}): "
                f"{exp.get('document','')}"
            )
    
    score = normalize_score(raw_score)
    return {
        "score": score,
        "severity": score_to_severity(score),
        "contributing_factors": factors,
        "explanation": 
            f"Renewal risk score {score}/100. "
            f"{len(factors)} risk factors "
            f"identified.",
        "confidence": 0.95,
        "trend": "stable"
    }

def calculate_continuity_risk_score(
    expiries: list,
    mismatch: dict
) -> dict:
    """
    Scores operational continuity risk.
    Can the business continue operating 
    after expiry?
    """
    raw_score = 0
    factors = []
    
    mismatch_type = mismatch.get(
        "mismatch_type")
    
    if mismatch_type == \
       "franchise_renewal_unprotected":
        raw_score += 40
        factors.append(
            "Franchise continuation depends "
            "on renegotiating lease"
        )
    
    if mismatch_type == "no_renewal":
        raw_score += 50
        factors.append(
            "No renewal path for either "
            "agreement — business must "
            "relocate or renegotiate"
        )
    
    # Check RULE-002 and RULE-005
    rules = mismatch.get(
        "rules_triggered", [])
    for rule in rules:
        if rule.get("rule") == "RULE-002":
            raw_score += 20
            factors.append(
                "Lease expires before franchise"
                " — occupation gap risk"
            )
        if rule.get("rule") == "RULE-005":
            raw_score += 35
            factors.append(
                "Renewal window missed — "
                "continuity at risk"
            )
    
    score = normalize_score(raw_score)
    return {
        "score": score,
        "severity": score_to_severity(score),
        "contributing_factors": factors,
        "explanation":
            f"Continuity risk score "
            f"{score}/100.",
        "confidence": 0.9,
        "trend": "stable"
    }

def calculate_data_confidence_score(
    expiries: list
) -> dict:
    """
    Scores how complete and trustworthy
    the extracted data is.
    Lower score = less confidence.
    This is INVERTED — high score = 
    high confidence.
    """
    raw_score = 100
    factors = []
    
    for exp in expiries:
        if not exp.get(
            "raw_commencement_date"):
            raw_score -= 15
            factors.append(
                f"Missing commencement: "
                f"{exp.get('document','')}"
            )
        if not exp.get("expiry_date"):
            raw_score -= 15
            factors.append(
                f"Missing expiry: "
                f"{exp.get('document','')}"
            )
        if not exp.get("renewal_type") or \
           exp.get("renewal_type") == "none":
            raw_score -= 5
            factors.append(
                f"No renewal type: "
                f"{exp.get('document','')}"
            )
        conf = exp.get("clause_confidence")
        if conf is not None and conf < 0.8:
            raw_score -= 10
            factors.append(
                f"Low clause confidence: "
                f"{exp.get('document','')}"
            )
        if exp.get("commencement_source") == \
           "fundamental_terms_cache":
            raw_score -= 5
            factors.append(
                "Commencement date recovered "
                "from cache (DocuSign form)"
            )
    
    score = normalize_score(raw_score)
    return {
        "score": score,
        "severity": score_to_severity(
            100 - score),
        "contributing_factors": factors,
        "explanation":
            f"Data confidence score "
            f"{score}/100. Higher is better.",
        "confidence": 1.0,
        "trend": "stable"
    }

def calculate_workspace_risk_scores(
    expiries: list,
    mismatch: dict
) -> dict:
    """
    Master function — calculates all 
    risk scores for a workspace.
    Returns complete risk scorecard.
    """
    renewal_risk = calculate_renewal_risk_score(
        expiries, mismatch)
    continuity_risk = \
        calculate_continuity_risk_score(
            expiries, mismatch)
    data_confidence = \
        calculate_data_confidence_score(expiries)
    
    # Overall portfolio risk 
    # weighted average
    overall = int(
        (renewal_risk["score"] * 0.4) +
        (continuity_risk["score"] * 0.4) +
        ((100 - data_confidence["score"]) * 0.2)
    )
    
    return {
        "renewal_risk": renewal_risk,
        "continuity_risk": continuity_risk,
        "data_confidence": data_confidence,
        "overall_risk_score": overall,
        "overall_severity": 
            score_to_severity(overall),
        "schema_version": "1.0"
    }
