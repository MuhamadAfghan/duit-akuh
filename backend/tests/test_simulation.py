"""Deposit and savings simulation (PRD section 8, FR10–FR12, AC07).

The PRD's worked example is the anchor: Rp10,000,000 at 4% a year for
6/12 of a year with 20% tax and no fees gives gross Rp200,000, tax
Rp40,000, net Rp160,000, final Rp10,160,000.

The other thing worth proving is that the arithmetic uses decimals, not
binary floats — the PRD asks for intermediate precision with a single
rounding at the end, which is the opposite of what float gives.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from app.domain.capacity import MINIMUM_MONTHS, CapacityInputs, compute_capacity
from app.domain.simulation import (
    FORMULA_VERSION,
    DayCountBasis,
    SimulationError,
    simulate_deposit,
    simulate_regular_saving,
    year_fraction,
)
from app.money import MoneyError

from .conftest import requires_db

# ----------------------------------------------------------------------
# AC07 - the PRD's worked example
# ----------------------------------------------------------------------


def test_ac07_the_prd_deposit_example():
    result = simulate_deposit(
        principal=10_000_000,
        annual_rate_percent=4,
        basis=DayCountBasis.MONTHS_12,
        months=6,
        tax_percent=20,
        fees=0,
    )

    assert result.gross_interest == 200_000
    assert result.tax == 40_000
    assert result.net_interest == 160_000
    assert result.final_value == 10_160_000
    assert result.complete is True


def test_every_figure_comes_back_as_whole_rupiah():
    result = simulate_deposit(principal=10_000_000, annual_rate_percent=4, months=6, tax_percent=20)

    for value in (
        result.gross_interest,
        result.tax,
        result.net_interest,
        result.final_value,
    ):
        assert isinstance(value, int)


def test_the_result_records_which_formula_produced_it():
    """A saved plan must not be silently reinterpreted by a later change."""
    result = simulate_deposit(principal=1_000_000, annual_rate_percent=5, months=12)

    assert result.formula_version == FORMULA_VERSION


# ----------------------------------------------------------------------
# Precision
# ----------------------------------------------------------------------


def test_a_value_sitting_exactly_on_half_a_rupiah_rounds_up():
    """Regression guard for a real precision bug.

    7,500,000 x 3.33% x 13/12 is exactly 270,562.5, so half-up rounding
    owes 270,563. An earlier version turned 13/12 into a decimal first;
    the repeating expansion was cut at 28 digits, the product came out
    as 270,562.4999..., and it rounded down. Holding the tenor as an
    exact fraction and dividing once, at the end, is what fixes it.
    """
    result = simulate_deposit(
        principal=7_500_000, annual_rate_percent="3.33", months=13, tax_percent=0
    )

    assert result.gross_interest == 270_563


def test_exact_arithmetic_across_awkward_tenors():
    """Every tenor whose year fraction repeats in decimal."""
    for months in (1, 5, 7, 11, 13, 17, 19, 23):
        result = simulate_deposit(
            principal=7_500_000, annual_rate_percent="3.33", months=months, tax_percent=0
        )
        exact = Fraction(7_500_000) * Fraction("3.33") / 100 * Fraction(months, 12)
        expected = (exact.numerator * 2 + exact.denominator) // (exact.denominator * 2)

        assert result.gross_interest == expected, f"{months} bulan"


def test_a_fractional_rate_is_accepted_as_a_string_or_decimal():
    as_string = simulate_deposit(
        principal=10_000_000, annual_rate_percent="4.25", months=12, tax_percent=0
    )
    as_decimal = simulate_deposit(
        principal=10_000_000, annual_rate_percent=Decimal("4.25"), months=12, tax_percent=0
    )

    assert as_string.gross_interest == as_decimal.gross_interest == 425_000


def test_a_float_rate_is_read_at_its_displayed_value():
    """A rate is a percentage, not an amount, so a float is allowed here.

    Amounts stay integer-only - `principal` and `fees` still go through
    the money guards. A rate is parsed via its repr, which is the
    shortest string that round-trips, so 4.25 is read as exactly 17/4
    rather than as the binary value slightly beside it.
    """
    from fractions import Fraction

    as_float = simulate_deposit(
        principal=10_000_000, annual_rate_percent=4.25, months=12, tax_percent=0
    )

    assert as_float.gross_interest == 425_000
    assert Fraction(str(4.25)) == Fraction(17, 4)


def test_a_float_principal_is_still_refused():
    """Amounts are money and stay integer rupiah, rate or no rate."""
    with pytest.raises(MoneyError):
        simulate_deposit(principal=10_000_000.5, annual_rate_percent=4, months=12, tax_percent=0)


def test_rounding_is_half_up_at_the_final_step():
    # 1,000,000 x 1% x 1/12 = 833.33...
    result = simulate_deposit(principal=1_000_000, annual_rate_percent=1, months=1, tax_percent=0)

    assert result.gross_interest == 833


# ----------------------------------------------------------------------
# Day-count bases
# ----------------------------------------------------------------------


def test_the_basis_changes_the_answer_which_is_why_it_is_explicit():
    common = {"principal": 100_000_000, "annual_rate_percent": 6, "tax_percent": 0}

    by_360 = simulate_deposit(**common, basis=DayCountBasis.ACTUAL_360, days=90)
    by_365 = simulate_deposit(**common, basis=DayCountBasis.ACTUAL_365, days=90)

    assert by_360.gross_interest == 1_500_000
    assert by_365.gross_interest == 1_479_452
    assert by_360.gross_interest != by_365.gross_interest


@pytest.mark.parametrize(
    ("basis", "kwargs", "expected"),
    [
        (DayCountBasis.MONTHS_12, {"months": 6}, Fraction(1, 2)),
        (DayCountBasis.ACTUAL_360, {"days": 180}, Fraction(1, 2)),
        (DayCountBasis.ACTUAL_365, {"days": 365}, Fraction(1)),
    ],
)
def test_year_fraction(basis, kwargs, expected):
    assert year_fraction(basis=basis, **kwargs) == expected


def test_a_tenor_in_the_wrong_unit_is_refused_rather_than_guessed():
    with pytest.raises(SimulationError):
        simulate_deposit(
            principal=1_000_000,
            annual_rate_percent=4,
            basis=DayCountBasis.ACTUAL_365,
            months=6,  # days are needed for a day-count basis
        )


@pytest.mark.parametrize("tenor", [0, -1])
def test_a_non_positive_tenor_is_refused(tenor):
    with pytest.raises(SimulationError):
        simulate_deposit(principal=1_000_000, annual_rate_percent=4, months=tenor)


# ----------------------------------------------------------------------
# Incomplete inputs (PRD section 8)
# ----------------------------------------------------------------------


def test_an_unknown_tax_rate_marks_the_result_incomplete():
    """The PRD forbids presenting a net figure as settled when tax is unknown."""
    result = simulate_deposit(principal=10_000_000, annual_rate_percent=4, months=6)

    assert result.complete is False
    assert result.tax == 0
    assert result.net_interest == 200_000, "arithmetic still runs, but is flagged"


def test_a_confirmed_zero_tax_is_complete():
    result = simulate_deposit(principal=10_000_000, annual_rate_percent=4, months=6, tax_percent=0)

    assert result.complete is True


def test_fees_reduce_the_net_result():
    result = simulate_deposit(
        principal=10_000_000, annual_rate_percent=4, months=6, tax_percent=20, fees=25_000
    )

    assert result.gross_interest == 200_000
    assert result.net_interest == 135_000
    assert result.final_value == 10_135_000


def test_a_deposit_can_lose_money_to_fees_and_says_so():
    result = simulate_deposit(
        principal=1_000_000, annual_rate_percent=1, months=1, tax_percent=0, fees=10_000
    )

    assert result.net_interest == -9_167
    assert result.final_value == 990_833, "the loss is shown, not floored at the principal"


@pytest.mark.parametrize("bad", [0, -1_000, 10_000.5])
def test_an_invalid_principal_is_refused(bad):
    with pytest.raises(MoneyError):
        simulate_deposit(principal=bad, annual_rate_percent=4, months=6)


def test_a_negative_rate_is_refused():
    with pytest.raises(SimulationError):
        simulate_deposit(principal=1_000_000, annual_rate_percent=-1, months=6)


def test_an_unparseable_rate_is_refused():
    with pytest.raises(SimulationError):
        simulate_deposit(principal=1_000_000, annual_rate_percent="empat persen", months=6)


# ----------------------------------------------------------------------
# Regular saving, zero interest (the MVP baseline)
# ----------------------------------------------------------------------


def test_regular_saving_matches_the_goal_calculator():
    """Same figures as AC06, reached by the simulator rather than the goal."""
    plan = simulate_regular_saving(target=15_000_000, initial=3_000_000, periods=6)

    assert plan.shortfall == 12_000_000
    assert plan.per_period == 2_000_000
    assert plan.overshoot == 0


def test_regular_saving_rounds_up_and_reports_the_overshoot():
    plan = simulate_regular_saving(target=10_000, initial=0, periods=3)

    assert plan.per_period == 3_334
    assert plan.total_saved == 10_002
    assert plan.overshoot == 2


def test_a_target_already_met_needs_nothing():
    plan = simulate_regular_saving(target=1_000_000, initial=1_500_000, periods=6)

    assert plan.shortfall == 0
    assert plan.per_period == 0


def test_zero_periods_is_refused():
    with pytest.raises(SimulationError):
        simulate_regular_saving(target=1_000_000, periods=0)


# ----------------------------------------------------------------------
# Capacity (FR10)
# ----------------------------------------------------------------------


def test_capacity_subtracts_outgoings_and_reserves_then_commitments():
    capacity = compute_capacity(
        CapacityInputs(
            reliable_income=10_000_000,
            cash_expenses=6_000_000,
            obligations=1_000_000,
            reserves=500_000,
            committed_deposits=1_000_000,
        ),
        months_observed=3,
    )

    assert capacity.gross == 2_500_000
    assert capacity.available == 1_500_000
    assert capacity.reliable is True
    assert capacity.notes == []


def test_too_short_a_history_is_flagged_rather_than_presented_as_measured():
    capacity = compute_capacity(
        CapacityInputs(reliable_income=5_000_000, cash_expenses=3_000_000, obligations=0),
        months_observed=1,
    )

    assert capacity.reliable is False
    assert any("perkiraan" in note for note in capacity.notes)
    assert MINIMUM_MONTHS == 3


def test_spending_more_than_you_earn_shows_a_negative_capacity():
    """A zero here would imply breaking even, which is not the same thing."""
    capacity = compute_capacity(
        CapacityInputs(reliable_income=5_000_000, cash_expenses=7_000_000, obligations=0),
        months_observed=3,
    )

    assert capacity.gross == -2_000_000
    assert any("melebihi pemasukan" in note for note in capacity.notes)


def test_overcommitted_goals_are_called_out():
    capacity = compute_capacity(
        CapacityInputs(
            reliable_income=5_000_000,
            cash_expenses=3_000_000,
            obligations=0,
            committed_deposits=3_000_000,
        ),
        months_observed=3,
    )

    assert capacity.gross == 2_000_000
    assert capacity.available == -1_000_000
    assert any("melebihi kapasitas" in note for note in capacity.notes)


# ----------------------------------------------------------------------
# Over HTTP, and AC07's second half: a simulation changes nothing
# ----------------------------------------------------------------------


@requires_db
@pytest.mark.integration
def test_ac07_a_simulation_leaves_the_ledger_untouched(engine, monkeypatch):
    import uuid as _uuid

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app
    from app.models import (
        Account,
        AuditEvent,
        Entry,
        LoginAttempt,
        Session,
        Transaction,
        User,
    )

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={
                "email": f"sim-{_uuid.uuid4().hex[:8]}@example.com",
                "password": "sangat-rahasia-123",
            },
        ).raise_for_status()
        client.post(
            "/accounts", json={"name": "BCA", "type": "bank", "opening_balance": 10_000_000}
        ).raise_for_status()

        before_summary = client.get("/summary").json()
        before_transactions = client.get("/transactions").json()

        response = client.post(
            "/simulations/deposit",
            json={
                "principal": 10_000_000,
                "annual_rate_percent": "4",
                "basis": "months",
                "months": 6,
                "tax_percent": "20",
                "fees": 0,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["gross_interest"] == 200_000
        assert body["net_interest"] == 160_000
        assert body["final_value"] == 10_160_000

        # The decisive part of AC07.
        assert client.get("/summary").json() == before_summary
        assert client.get("/transactions").json() == before_transactions

    with factory() as cleanup:
        for model in (AuditEvent, Entry, Transaction, Account, Session, LoginAttempt, User):
            cleanup.query(model).delete()
        cleanup.commit()


@requires_db
@pytest.mark.integration
def test_simulations_require_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.post("/simulations/deposit", json={}).status_code == 401
        assert anon.get("/simulations/capacity").status_code == 401
