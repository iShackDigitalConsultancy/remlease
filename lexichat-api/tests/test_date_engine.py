import pytest
from services.date_engine import (
    calculate_expiry,
    calculate_renewal_window,
    check_renewal_window_status,
    subtract_months,
    normalize_expiry_date,
    days_between,
    is_beneficial_occupation_significant
)

def test_1_5_year_anniversary_expiry():
    # Test 1: 5-year anniversary expiry
    result = calculate_expiry("2023-07-01", 5)
    assert result["date"] == "2028-06-30"

def test_2_exact_anniversary():
    # Test 2: Exact anniversary  
    result = calculate_expiry("2023-07-01", 5, "exact")
    assert result["date"] == "2028-07-01"

def test_3_month_subtraction_across_year_boundary():
    # Test 3: Month subtraction across year boundary
    result = subtract_months("2028-07-01", 9)
    assert result["date"] == "2027-10-01"

def test_4_end_of_month_handling():
    # Test 4: End of month handling
    result = subtract_months("2028-09-30", 6)
    assert result["date"] == "2028-03-30"

def test_5_31_march_minus_6_months():
    # Test 5: 31 March minus 6 months
    result = subtract_months("2028-03-31", 6)
    assert result["date"] == "2027-09-30"

def test_6_leap_year_handling():
    # Test 6: Leap year handling
    result = subtract_months("2025-02-28", 12)
    assert result["date"] == "2024-02-28"

def test_7_renewal_window_calculation():
    # Test 7: Renewal window calculation
    result = calculate_renewal_window("2028-07-01", 6, 9)
    assert result["renewal_notice_latest"] == "2028-01-01"
    assert result["renewal_notice_earliest"] == "2027-10-01"

def test_8_renewal_window_status_too_early():
    # Test 8: Renewal window status — too early
    result = check_renewal_window_status("2028-07-01", 6, 9, "2026-01-01")
    assert result["status"] == "too_early"

def test_9_renewal_window_status_open():
    # Test 9: Renewal window status — open
    result = check_renewal_window_status("2028-07-01", 6, 9, "2027-11-01")
    assert result["status"] == "window_open"

def test_10_renewal_window_status_too_late():
    # Test 10: Renewal window status — too late
    result = check_renewal_window_status("2028-07-01", 6, 9, "2028-02-01")
    assert result["status"] == "window_closed_renewal_possible"

def test_11_rights_lapsed():
    # Test 11: Rights lapsed
    result = check_renewal_window_status("2028-07-01", 6, 9, "2028-08-01")
    assert result["status"] == "too_late_rights_lapsed"

def test_12_days_between():
    # Test 12: days_between
    result = days_between("2023-07-01", "2028-06-30")
    assert result["days"] == 1826

def test_13_beneficial_occupation_significant():
    # Test 13: Beneficial occupation significant
    result = is_beneficial_occupation_significant("2023-06-01", "2023-07-01")
    assert result["is_significant"] == True
    assert result["days_difference"] == 30
    assert result["flag"] is not None

def test_14_beneficial_occupation_not_significant():
    # Test 14: Beneficial occupation not significant
    result = is_beneficial_occupation_significant("2023-06-25", "2023-07-01")
    assert result["is_significant"] == False

def test_15_end_of_month_february():
    # Test 15: End of month February
    result = subtract_months("2024-08-31", 6)
    assert result["date"] == "2024-02-29"

def test_16_normalize_expiry_prefers_calculated():
    # When commencement + duration is known,
    # calculated date should be used even if
    # raw_date from rental schedule differs
    result = normalize_expiry_date(
        raw_date="2028-10-01",  # wrong date
                                # from rental table
        agreement_type="Lease Agreement",
        commencement_date="2023-07-01",
        duration_years=5
    )
    # Should use calculated date, not raw
    assert result["date"] == "2028-06-30"
    # Basis should mention the mismatch
    assert "Mismatch" in result["basis"] or \
           "day_before" in result["basis"]
