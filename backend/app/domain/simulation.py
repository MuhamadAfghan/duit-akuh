"""Savings and deposit simulation (PRD section 8, FR12, AC07).

This is the one place in the codebase that handles fractions of a
rupiah. It uses :class:`~fractions.Fraction` — exact rational
arithmetic — never ``float`` and not even ``Decimal``.

The PRD asks for intermediate precision to be kept with a single
rounding at the end, and both alternatives break that. ``float`` is the
obvious offender, but ``Decimal`` fails too the moment a tenor like
13/12 is turned into a decimal early: the repeating expansion is cut at
28 digits, and 7,500,000 x 3.33% x 13/12 — exactly 270,562.5 — comes out
as 270,562.4999... and rounds down to the wrong rupiah. A ``Fraction``
holds 13/12 as 13/12, so the division happens once, at the end, against
an exact numerator. The result crossing back into the rest of the app is
an integer again.

Nothing here reads or writes anything. A simulation must not move money
or change a goal until the user applies the plan (AC07).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from ..money import positive_rupiah, rupiah

#: Stamped on every result. A saved plan has to record which formula
#: produced its figures, or a later change silently reinterprets it.
FORMULA_VERSION = "simple-interest-1"


class DayCountBasis(str, Enum):
    """How a tenor becomes a fraction of a year.

    Banks differ, and the difference is real money, so it is an explicit
    input rather than a hidden default. ``MONTHS_12`` is for tenors
    quoted in months, which is how Indonesian deposits usually are.
    """

    ACTUAL_365 = "365"
    ACTUAL_360 = "360"
    MONTHS_12 = "months"


class SimulationError(ValueError):
    """An input the simulation cannot work with."""


def _fraction(value, field: str) -> Fraction:
    """Parse a rate or percentage exactly.

    ``Fraction`` reads "3.33" as 333/100, so a rate quoted in decimal
    stays exact rather than becoming the nearest binary approximation.
    """
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise SimulationError(f"Nilai '{field}' tidak valid: {value!r}") from exc


def year_fraction(
    *, basis: DayCountBasis, days: int | None = None, months: int | None = None
) -> Fraction:
    """The portion of a year a tenor covers, held exactly.

    Returns a ``Fraction`` rather than a decimal so 13/12 stays 13/12
    and the single division happens at the end of the calculation.
    """
    if basis is DayCountBasis.MONTHS_12:
        if months is None:
            raise SimulationError("Tenor dalam bulan harus diisi untuk basis bulan/12")
        if months <= 0:
            raise SimulationError("Tenor harus lebih besar dari nol")
        return Fraction(months, 12)

    if days is None:
        raise SimulationError("Tenor dalam hari harus diisi untuk basis 360/365")
    if days <= 0:
        raise SimulationError("Tenor harus lebih besar dari nol")

    return Fraction(days, 360 if basis is DayCountBasis.ACTUAL_360 else 365)


@dataclass(frozen=True, slots=True)
class DepositResult:
    principal: int
    gross_interest: int
    tax: int
    fees: int
    net_interest: int
    final_value: int
    year_fraction: str
    basis: str
    #: False when a figure the result depends on was not supplied, so the
    #: UI can mark the net figure incomplete rather than imply it is
    #: authoritative (PRD section 8).
    complete: bool
    formula_version: str = FORMULA_VERSION


def simulate_deposit(
    *,
    principal: int,
    annual_rate_percent,
    basis: DayCountBasis = DayCountBasis.MONTHS_12,
    days: int | None = None,
    months: int | None = None,
    tax_percent=None,
    fees: int = 0,
) -> DepositResult:
    """Simple interest on a fixed deposit.

    Formulas are the PRD's, in order:

        gross = principal x annual_rate x year_fraction
        tax   = gross x tax_rate
        net   = gross - tax - fees
        final = principal + net

    ``tax_percent=None`` means "not known yet": the arithmetic proceeds
    with zero tax but the result is flagged ``complete=False``, because
    the PRD forbids presenting a net figure as settled when a component
    is missing. Passing ``0`` explicitly is a confirmed zero and stays
    complete.
    """
    principal = positive_rupiah(principal)
    fees = rupiah(fees)

    if fees < 0:
        raise SimulationError("Biaya tidak boleh negatif")

    rate = _fraction(annual_rate_percent, "bunga tahunan") / 100

    if rate < 0:
        raise SimulationError("Suku bunga tidak boleh negatif")

    fraction = year_fraction(basis=basis, days=days, months=months)

    # Full precision through the chain; rounded once, at the end.
    gross_exact = Fraction(principal) * rate * fraction

    complete = tax_percent is not None
    tax_rate = _fraction(tax_percent if complete else 0, "tarif pajak") / 100

    if tax_rate < 0:
        raise SimulationError("Tarif pajak tidak boleh negatif")

    tax_exact = gross_exact * tax_rate
    net_exact = gross_exact - tax_exact - fees

    gross = _to_rupiah(gross_exact)
    tax = _to_rupiah(tax_exact)
    net = _to_rupiah(net_exact)

    return DepositResult(
        principal=principal,
        gross_interest=gross,
        tax=tax,
        fees=fees,
        net_interest=net,
        final_value=principal + net,
        year_fraction=str(fraction),
        basis=basis.value,
        complete=complete,
    )


def _to_rupiah(value: Fraction) -> int:
    """Round an exact fraction to whole rupiah, half away from zero.

    Done on the fraction itself rather than via a decimal, so no
    intermediate representation can shift a value sitting exactly on .5.
    """
    sign = -1 if value < 0 else 1
    magnitude = abs(value)
    rounded = (magnitude.numerator * 2 + magnitude.denominator) // (magnitude.denominator * 2)
    return sign * rounded


# ----------------------------------------------------------------------
# Regular saving, no interest (PRD section 8 baseline)
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SavingPlanResult:
    target: int
    initial: int
    shortfall: int
    periods: int
    per_period: int
    #: Total actually set aside, which can exceed the shortfall because
    #: the per-period figure is rounded up.
    total_saved: int
    overshoot: int
    formula_version: str = FORMULA_VERSION


def simulate_regular_saving(*, target: int, initial: int = 0, periods: int) -> SavingPlanResult:
    """Flat saving toward a target with no interest.

    The PRD sets zero interest as the MVP baseline and warns against
    comparing results whose methods differ, so this stays deliberately
    plain rather than quietly compounding.
    """
    target = positive_rupiah(target)
    initial = rupiah(initial)

    if initial < 0:
        raise SimulationError("Dana awal tidak boleh negatif")

    if periods <= 0:
        raise SimulationError("Jumlah setoran harus lebih besar dari nol")

    shortfall = max(0, target - initial)
    per_period = -(-shortfall // periods)  # ceiling, so the target is reached
    total = per_period * periods

    return SavingPlanResult(
        target=target,
        initial=initial,
        shortfall=shortfall,
        periods=periods,
        per_period=per_period,
        total_saved=total,
        overshoot=max(0, total - shortfall),
    )
