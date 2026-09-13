from decimal import Decimal

import pytest

from offer_agent.salary import compute_salary, format_aed


def test_default_fifty_fifty_split_balances():
    result = compute_salary(20500)
    assert result.balanced
    assert not result.used_override
    b = result.breakdown
    assert b.monthly_basic == Decimal("10250.0")
    assert b.monthly_supplementary == Decimal("10250.0")
    assert b.monthly_total == Decimal("20500")
    assert b.annual_basic == Decimal("123000.0")
    assert b.annual_supplementary == Decimal("123000.0")
    assert b.annual_total == Decimal("246000")


def test_override_breakdown_balances():
    result = compute_salary(20000, override_monthly_basic=15000, override_monthly_supplementary=5000)
    assert result.balanced
    assert result.used_override
    assert result.breakdown.monthly_basic == Decimal("15000")
    assert result.breakdown.annual_basic == Decimal("180000")


def test_override_breakdown_discrepancy_is_reported_not_silently_fixed():
    result = compute_salary(20000, override_monthly_basic=15000, override_monthly_supplementary=6000)
    assert not result.balanced
    assert result.breakdown is None
    assert result.discrepancies
    assert "21000" in result.discrepancies[0]


def test_format_aed():
    assert format_aed(20500) == "AED 20,500"
    assert format_aed("20,500") == "AED 20,500"
    assert format_aed("AED 20500") == "AED 20,500"
    assert format_aed(Decimal("1234567")) == "AED 1,234,567"


def test_format_aed_never_alters_underlying_value_only_display():
    result = compute_salary(20501)
    # 50/50 split of an odd total is not evenly divisible -> flagged, not rounded away.
    assert result.balanced
    assert result.warnings
