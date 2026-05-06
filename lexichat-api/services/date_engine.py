from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
from typing import Optional

def _parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

def calculate_expiry(commencement_date: str, duration_years: int, anniversary_type: str = "day_before") -> dict:
    d = _parse_date(commencement_date)
    if not d:
        return {"date": None, "basis": "Invalid commencement date", "confidence": 0.0}
    
    exact_anniversary = d + relativedelta(years=duration_years)
    
    if anniversary_type == "day_before":
        expiry = exact_anniversary - timedelta(days=1)
        basis = f"{duration_years} years from {commencement_date} using day_before convention = {expiry.isoformat()}"
    else:
        expiry = exact_anniversary
        basis = f"{duration_years} years from {commencement_date} using exact convention = {expiry.isoformat()}"
        
    return {"date": expiry.isoformat(), "basis": basis, "confidence": 1.0}

def calculate_renewal_window(expiry_date: str, notice_min_months: int, notice_max_months: int) -> dict:
    d = _parse_date(expiry_date)
    if not d:
        return {
            "renewal_notice_latest": None, 
            "renewal_notice_earliest": None, 
            "basis": "Invalid expiry date", 
            "confidence": 0.0
        }
    
    latest = d - relativedelta(months=notice_min_months)
    earliest = d - relativedelta(months=notice_max_months)
    
    basis = f"Renewal window: {notice_max_months} to {notice_min_months} months prior to expiry {expiry_date}"
    return {
        "renewal_notice_latest": latest.isoformat(),
        "renewal_notice_earliest": earliest.isoformat(),
        "basis": basis,
        "confidence": 1.0
    }

def check_renewal_window_status(expiry_date: str, notice_min_months: int, notice_max_months: int, as_of_date: str = None) -> dict:
    today = _parse_date(as_of_date) if as_of_date else date.today()
    
    window = calculate_renewal_window(expiry_date, notice_min_months, notice_max_months)
    if window["confidence"] == 0.0:
        return {
            "status": None,
            "days_until_window_opens": None,
            "days_until_window_closes": None,
            "days_until_expiry": None,
            "basis": "Invalid expiry date for status check",
            "urgency": "Low"
        }
    
    earliest_date = _parse_date(window["renewal_notice_earliest"])
    latest_date = _parse_date(window["renewal_notice_latest"])
    exp_date = _parse_date(expiry_date)
    
    days_to_expiry = (exp_date - today).days
    days_to_open = (earliest_date - today).days
    days_to_close = (latest_date - today).days
    
    if today < earliest_date:
        status = "too_early"
        urgency = "Low"
        basis = "Current date is before the renewal window opens"
    elif earliest_date <= today <= latest_date:
        if days_to_close <= 30:
            status = "window_closing_soon"
            urgency = "Critical"
            basis = "Renewal window is open but closing within 30 days"
        else:
            status = "window_open"
            urgency = "High"
            basis = "Renewal window is currently open"
    elif latest_date < today <= exp_date:
        status = "window_closed_renewal_possible"
        urgency = "High"
        basis = "Renewal window closed but expiry has not passed; late renewal might be possible"
    else:
        status = "too_late_rights_lapsed"
        urgency = "Critical"
        basis = "Expiry date has passed, rights lapsed"
        
    return {
        "status": status,
        "days_until_window_opens": days_to_open if days_to_open > 0 else None,
        "days_until_window_closes": days_to_close if days_to_close > 0 else None,
        "days_until_expiry": days_to_expiry,
        "basis": basis,
        "urgency": urgency
    }

def normalize_expiry_date(raw_date: str, agreement_type: str, commencement_date: str = None, duration_years: int = None) -> dict:
    agr_type = agreement_type.lower()
    if ("franchise" in agr_type or "lease" in agr_type) and commencement_date and duration_years:
        calculated = calculate_expiry(commencement_date, duration_years, "day_before")
        calc_date = calculated.get("date")
        
        if raw_date and calc_date:
            rd = _parse_date(raw_date)
            cd = _parse_date(calc_date)
            if rd and cd:
                diff = abs((rd - cd).days)
                if diff > 1:
                    basis = f"Mismatch: Provided raw_date {raw_date} differs from calculated {calc_date} by {diff} days"
                    return {"date": calc_date, "basis": basis, "confidence": 1.0}
        
        return {"date": calc_date, "basis": calculated["basis"], "confidence": 1.0}
    
    if raw_date:
        parsed = _parse_date(raw_date)
        if parsed:
            return {"date": parsed.isoformat(), "basis": "Used provided raw_date directly", "confidence": 1.0}
            
    return {"date": None, "basis": "Insufficient information to determine expiry", "confidence": 0.0}

def subtract_months(from_date: str, months: int) -> dict:
    d = _parse_date(from_date)
    if not d:
        return {"date": None, "basis": "Invalid date", "confidence": 0.0}
    
    result = d - relativedelta(months=months)
    basis = f"{from_date} minus {months} months = {result.isoformat()}"
    return {"date": result.isoformat(), "basis": basis, "confidence": 1.0}

def days_between(date_a: str, date_b: str) -> dict:
    da = _parse_date(date_a)
    db = _parse_date(date_b)
    
    if not da or not db:
        return {"days": None, "basis": "Invalid dates", "confidence": 0.0}
        
    diff = (db - da).days
    return {"days": diff, "basis": f"{abs(diff)} days between {date_a} and {date_b}", "confidence": 1.0}

def is_beneficial_occupation_significant(beneficial_occupation_date: str, legal_commencement_date: str, threshold_days: int = 30) -> dict:
    days_diff_result = days_between(beneficial_occupation_date, legal_commencement_date)
    if days_diff_result["confidence"] == 0.0:
        return {"is_significant": False, "days_difference": 0, "basis": "Invalid dates", "flag": None}
        
    diff = days_diff_result["days"]
    
    is_significant = diff >= threshold_days
    flag = "Pre-trading occupation exposure" if is_significant else None
    basis = f"Beneficial occupation is {diff} days before commencement" if diff > 0 else f"Beneficial occupation is {-diff} days after commencement"
    if is_significant:
        basis += f", which meets or exceeds the {threshold_days} day threshold"
        
    return {
        "is_significant": is_significant,
        "days_difference": diff,
        "basis": basis,
        "flag": flag
    }
