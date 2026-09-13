"""Salary calculation and validation.

Currency is always AED. Figures are never converted or altered — this
module only computes the basic/supplementary split (50/50 unless an
approved override breakdown is supplied) and the per-annum equivalents
(monthly x 12), then validates that the parts sum to the whole.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional


class InvalidSalaryInputError(ValueError):
    """Raised when a salary figure cannot be parsed as a numeric amount."""


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        # Strip common formatting the caller might pass through by mistake
        # (thousands separators, currency prefix, whitespace). This does
        # NOT invent or guess a value — it only tolerates formatting of an
        # already-resolved figure.
        if isinstance(value, str):
            cleaned = value.strip()
            for prefix in ("AED", "aed", "Aed"):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
            cleaned = cleaned.replace(",", "").strip()
        else:
            cleaned = value
        return Decimal(str(cleaned))
    except (InvalidOperation, TypeError) as exc:
        raise InvalidSalaryInputError(f"Not a valid numeric salary amount: {value!r}") from exc


@dataclass
class SalaryBreakdown:
    monthly_basic: Decimal
    monthly_supplementary: Decimal
    monthly_total: Decimal
    annual_basic: Decimal
    annual_supplementary: Decimal
    annual_total: Decimal


@dataclass
class SalaryResult:
    breakdown: Optional[SalaryBreakdown]
    balanced: bool
    used_override: bool
    discrepancies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_salary(
    monthly_total: object,
    override_monthly_basic: Optional[object] = None,
    override_monthly_supplementary: Optional[object] = None,
) -> SalaryResult:
    """Compute the full monthly/annual salary breakdown.

    ``monthly_total`` is the Proposed Salary from the hiring approval (the
    monthly Total Salary), unless the user has explicitly overridden it.

    If both ``override_monthly_basic`` and ``override_monthly_supplementary``
    are supplied (an approved override breakdown), they are used as-is
    instead of the default 50/50 split. If they do not sum to
    ``monthly_total``, the discrepancy is reported and correction is
    required before the offer can proceed — this function never silently
    adjusts the figures to force a balance.
    """
    total = to_decimal(monthly_total)
    used_override = (
        override_monthly_basic is not None and override_monthly_supplementary is not None
    )

    if used_override:
        basic = to_decimal(override_monthly_basic)
        supplementary = to_decimal(override_monthly_supplementary)
    else:
        basic = total * Decimal("0.5")
        supplementary = total * Decimal("0.5")

    annual_basic = basic * 12
    annual_supplementary = supplementary * 12
    annual_total = total * 12

    discrepancies: list[str] = []

    monthly_sum = basic + supplementary
    if monthly_sum != total:
        discrepancies.append(
            "Monthly basic salary (AED {}) + supplementary allowance (AED {}) = "
            "AED {}, which does not equal monthly Total Salary (AED {}).".format(
                basic, supplementary, monthly_sum, total
            )
        )

    annual_sum = annual_basic + annual_supplementary
    if annual_sum != annual_total:
        discrepancies.append(
            "Annual basic salary (AED {}) + supplementary allowance (AED {}) = "
            "AED {}, which does not equal annual Total Salary (AED {}).".format(
                annual_basic, annual_supplementary, annual_sum, annual_total
            )
        )

    balanced = not discrepancies

    breakdown = SalaryBreakdown(
        monthly_basic=basic,
        monthly_supplementary=supplementary,
        monthly_total=total,
        annual_basic=annual_basic,
        annual_supplementary=annual_supplementary,
        annual_total=annual_total,
    ) if balanced else None

    warnings: list[str] = []
    if balanced:
        for label, value in (
            ("basic salary", basic),
            ("supplementary allowance", supplementary),
            ("Total Salary", total),
        ):
            if value != value.to_integral_value():
                warnings.append(
                    f"Monthly {label} (AED {value}) is not a whole AED amount; "
                    "displayed using the AED #,##0 format without altering the "
                    "underlying approved figure."
                )

    return SalaryResult(
        breakdown=breakdown,
        balanced=balanced,
        used_override=used_override,
        discrepancies=discrepancies,
        warnings=warnings,
    )


def format_aed(value: object) -> str:
    """Format a numeric amount as ``AED #,##0`` for display in the contract.

    This affects display only — it never mutates the stored/approved
    figure used in calculations or the audit record.
    """
    amount = to_decimal(value)
    quantized = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"AED {quantized:,}"
