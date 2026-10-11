"""The PRD's acceptance criteria, as executable tests.

Each test names the AC it covers and uses the PRD's own figures. These
run with no database: the ledger builders are pure, which is the point —
the rules that decide whether someone's money is counted correctly should
not need infrastructure to verify.

Database-level guarantees (idempotency, atomicity, cross-user isolation)
are covered separately in ``test_posting_integration.py``.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.allocations import AllocationSnapshot, check_allocation_fits
from app.domain.balances import (
    AccountSnapshot,
    category_total,
    free_to_spend,
    liquid_balance,
    net_worth,
    total_debt,
)
from app.domain.errors import (
    AllocationExceedsBalance,
    InvalidTransaction,
    UnbalancedTransaction,
)
from app.domain.ledger import (
    Leg,
    assert_balanced,
    build_card_payment,
    build_expense,
    build_income,
    build_opening_balance,
    build_refund,
    build_reversal,
    build_transfer,
)
from app.models import AccountKind, AccountType
from app.money import MoneyError, format_rupiah, positive_rupiah, rupiah

# Stable ids so assertions read clearly.
BANK = uuid.uuid4()
EWALLET = uuid.uuid4()
CASH = uuid.uuid4()
CARD = uuid.uuid4()
EXPENSE = uuid.uuid4()
FEE_EXPENSE = uuid.uuid4()
INCOME = uuid.uuid4()
EQUITY = uuid.uuid4()


def balances(*leg_lists: list[Leg]) -> dict[uuid.UUID, int]:
    """Fold several transactions into per-account balances."""
    totals: dict[uuid.UUID, int] = {}

    for legs in leg_lists:
        assert_balanced(legs)
        for leg in legs:
            totals[leg.account_id] = totals.get(leg.account_id, 0) + leg.amount

    return totals


def snapshot(account_id, type_, kind, balance, **kw) -> AccountSnapshot:
    return AccountSnapshot(
        id=account_id, name=str(account_id)[:8], type=type_, kind=kind, balance=balance, **kw
    )


# ----------------------------------------------------------------------
# AC01 - opening balances are assets, not income
# ----------------------------------------------------------------------


def test_ac01_opening_balances_do_not_count_as_income():
    """Bank 1,000,000 + e-wallet 100,000 = assets 1,100,000, income stays 0."""
    bank_open = build_opening_balance(account_id=BANK, equity_account_id=EQUITY, amount=1_000_000)
    wallet_open = build_opening_balance(
        account_id=EWALLET, equity_account_id=EQUITY, amount=100_000
    )

    totals = balances(bank_open, wallet_open)

    accounts = [
        snapshot(BANK, AccountType.BANK, AccountKind.ASSET, totals[BANK]),
        snapshot(EWALLET, AccountType.EWALLET, AccountKind.ASSET, totals[EWALLET]),
        snapshot(EQUITY, AccountType.OPENING_BALANCE, AccountKind.EQUITY, totals[EQUITY]),
    ]

    assert liquid_balance(accounts) == 1_100_000
    assert net_worth(accounts) == 1_100_000
    # The decisive part: no income account was touched at all.
    assert category_total(accounts, kind=AccountKind.INCOME) == 0


# ----------------------------------------------------------------------
# AC02 - top-up with an admin fee
# ----------------------------------------------------------------------


def test_ac02_topup_with_admin_fee_splits_fee_as_expense():
    """Top up 100,000 with a 1,000 fee: bank -101,000, e-wallet +100,000, expense 1,000."""
    legs = build_transfer(
        from_account_id=BANK,
        to_account_id=EWALLET,
        amount=100_000,
        fee=1_000,
        fee_expense_account_id=FEE_EXPENSE,
    )

    totals = balances(legs)

    assert totals[BANK] == -101_000
    assert totals[EWALLET] == 100_000
    assert totals[FEE_EXPENSE] == 1_000

    accounts = [
        snapshot(BANK, AccountType.BANK, AccountKind.ASSET, totals[BANK]),
        snapshot(EWALLET, AccountType.EWALLET, AccountKind.ASSET, totals[EWALLET]),
        snapshot(
            FEE_EXPENSE, AccountType.EXPENSE_CATEGORY, AccountKind.EXPENSE, totals[FEE_EXPENSE]
        ),
    ]

    # Only the fee is an expense - the 100,000 that moved is not spending.
    assert category_total(accounts, kind=AccountKind.EXPENSE) == 1_000
    assert category_total(accounts, kind=AccountKind.INCOME) == 0
    # The transfer itself destroyed no money: net change is just the fee.
    assert liquid_balance(accounts) == -1_000


def test_transfer_without_fee_is_neither_income_nor_expense():
    legs = build_transfer(from_account_id=BANK, to_account_id=CASH, amount=250_000)
    totals = balances(legs)

    assert totals[BANK] == -250_000
    assert totals[CASH] == 250_000
    assert set(totals) == {BANK, CASH}, "a plain transfer must touch no category account"


def test_transfer_to_same_account_is_rejected():
    with pytest.raises(InvalidTransaction):
        build_transfer(from_account_id=BANK, to_account_id=BANK, amount=1_000)


def test_fee_without_a_category_is_rejected():
    with pytest.raises(InvalidTransaction):
        build_transfer(from_account_id=BANK, to_account_id=EWALLET, amount=100_000, fee=1_000)


# ----------------------------------------------------------------------
# AC03 - credit card spend then full payment must not double count
# ----------------------------------------------------------------------


def test_ac03_card_spend_then_payment_does_not_double_count():
    """Spend 800,000 on the card, then pay it in full.

    Expense stays 800,000 and the debt returns to zero.
    """
    spend = build_expense(from_account_id=CARD, expense_account_id=EXPENSE, amount=800_000)
    payment = build_card_payment(from_account_id=BANK, card_account_id=CARD, amount=800_000)

    totals = balances(spend, payment)

    accounts = [
        snapshot(BANK, AccountType.BANK, AccountKind.ASSET, totals[BANK]),
        snapshot(
            CARD,
            AccountType.CREDIT_CARD,
            AccountKind.LIABILITY,
            totals[CARD],
            credit_limit=10_000_000,
        ),
        snapshot(EXPENSE, AccountType.EXPENSE_CATEGORY, AccountKind.EXPENSE, totals[EXPENSE]),
    ]

    assert category_total(accounts, kind=AccountKind.EXPENSE) == 800_000, "spend counted once"
    assert total_debt(accounts) == 0, "card paid off"
    assert totals[BANK] == -800_000, "the bank is what actually paid"


def test_card_spend_alone_creates_debt_and_expense_together():
    spend = build_expense(from_account_id=CARD, expense_account_id=EXPENSE, amount=800_000)
    totals = balances(spend)

    accounts = [
        snapshot(
            CARD,
            AccountType.CREDIT_CARD,
            AccountKind.LIABILITY,
            totals[CARD],
            credit_limit=10_000_000,
        ),
        snapshot(EXPENSE, AccountType.EXPENSE_CATEGORY, AccountKind.EXPENSE, totals[EXPENSE]),
    ]

    assert total_debt(accounts) == 800_000
    assert category_total(accounts, kind=AccountKind.EXPENSE) == 800_000


def test_credit_limit_is_never_counted_as_money():
    """A card with a large limit and no debt adds nothing to what you have."""
    card = snapshot(
        CARD, AccountType.CREDIT_CARD, AccountKind.LIABILITY, 0, credit_limit=50_000_000
    )
    bank = snapshot(BANK, AccountType.BANK, AccountKind.ASSET, 1_000_000)

    accounts = [bank, card]

    assert liquid_balance(accounts) == 1_000_000
    assert net_worth(accounts) == 1_000_000
    assert free_to_spend(accounts).amount == 1_000_000


def test_card_payment_to_itself_is_rejected():
    with pytest.raises(InvalidTransaction):
        build_card_payment(from_account_id=CARD, card_account_id=CARD, amount=1_000)


# ----------------------------------------------------------------------
# AC05 - allocations are virtual
# ----------------------------------------------------------------------


def test_ac05_allocation_does_not_increase_assets():
    """Allocating 2,000,000 out of a 5,000,000 balance leaves assets unchanged."""
    opening = build_opening_balance(account_id=BANK, equity_account_id=EQUITY, amount=5_000_000)
    totals = balances(opening)

    accounts = [snapshot(BANK, AccountType.BANK, AccountKind.ASSET, totals[BANK])]
    before = net_worth(accounts)

    goal = uuid.uuid4()
    check_allocation_fits(
        account_id=BANK, account_balance=totals[BANK], existing=[], new_amount=2_000_000
    )

    # An allocation writes no entry, so nothing about the ledger changed.
    assert net_worth(accounts) == before == 5_000_000

    # It does reduce what is free to spend, without being a second pot.
    allocations = [AllocationSnapshot(account_id=BANK, goal_id=goal, amount=2_000_000)]
    result = free_to_spend(accounts, allocated_on_liquid=sum(a.amount for a in allocations))

    assert result.liquid == 5_000_000
    assert result.allocated == 2_000_000
    assert result.amount == 3_000_000


def test_ac05_allocation_above_balance_is_rejected():
    with pytest.raises(AllocationExceedsBalance):
        check_allocation_fits(
            account_id=BANK, account_balance=5_000_000, existing=[], new_amount=5_000_001
        )


def test_allocations_accumulate_against_the_same_balance():
    goal_a = uuid.uuid4()
    existing = [AllocationSnapshot(account_id=BANK, goal_id=goal_a, amount=3_000_000)]

    check_allocation_fits(
        account_id=BANK, account_balance=5_000_000, existing=existing, new_amount=2_000_000
    )

    with pytest.raises(AllocationExceedsBalance):
        check_allocation_fits(
            account_id=BANK, account_balance=5_000_000, existing=existing, new_amount=2_000_001
        )


def test_editing_an_allocation_is_not_counted_against_itself():
    goal = uuid.uuid4()
    existing = [AllocationSnapshot(account_id=BANK, goal_id=goal, amount=5_000_000)]

    total = check_allocation_fits(
        account_id=BANK,
        account_balance=5_000_000,
        existing=existing,
        new_amount=4_000_000,
        replacing_goal_id=goal,
    )

    assert total == 4_000_000


def test_negative_balance_supports_no_allocation():
    with pytest.raises(AllocationExceedsBalance):
        check_allocation_fits(account_id=BANK, account_balance=-50_000, existing=[], new_amount=1)


def test_the_refusal_says_the_amounts_the_way_the_app_writes_money():
    """The message is shown to the user, so it reads like the rest.

    "Alokasi 5000000 melebihi saldo 3628050" is a developer's string.
    Nothing else in the product prints a bare integer of rupiah.
    """
    with pytest.raises(AllocationExceedsBalance) as refusal:
        check_allocation_fits(
            account_id=BANK,
            account_balance=3_628_050,
            existing=[],
            new_amount=5_000_000,
        )

    message = str(refusal.value)

    assert "Rp5.000.000" in message
    assert "Rp3.628.050" in message
    assert "5000000" not in message


# ----------------------------------------------------------------------
# Corrections and refunds (FR02, AC08 arithmetic half)
# ----------------------------------------------------------------------


def test_ac08_correcting_an_amount_restores_the_difference():
    """35,000 corrected to 30,000 restores 5,000, via reversal + repost."""
    original = build_expense(from_account_id=BANK, expense_account_id=EXPENSE, amount=35_000)
    reversal = build_reversal(original)
    corrected = build_expense(from_account_id=BANK, expense_account_id=EXPENSE, amount=30_000)

    totals = balances(original, reversal, corrected)

    assert totals[BANK] == -30_000
    assert totals[EXPENSE] == 30_000

    # The reversal did not erase anything: three transactions exist, and
    # the net effect is the corrected one.
    only_original = balances(original)
    assert only_original[BANK] == -35_000


def test_refund_reduces_the_original_category():
    spend = build_expense(from_account_id=BANK, expense_account_id=EXPENSE, amount=200_000)
    refund = build_refund(to_account_id=BANK, expense_account_id=EXPENSE, amount=50_000)

    totals = balances(spend, refund)

    assert totals[BANK] == -150_000
    assert totals[EXPENSE] == 150_000


def test_refund_onto_a_card_reduces_debt():
    spend = build_expense(from_account_id=CARD, expense_account_id=EXPENSE, amount=800_000)
    refund = build_refund(to_account_id=CARD, expense_account_id=EXPENSE, amount=300_000)

    totals = balances(spend, refund)
    accounts = [
        snapshot(CARD, AccountType.CREDIT_CARD, AccountKind.LIABILITY, totals[CARD]),
        snapshot(EXPENSE, AccountType.EXPENSE_CATEGORY, AccountKind.EXPENSE, totals[EXPENSE]),
    ]

    assert total_debt(accounts) == 500_000
    assert category_total(accounts, kind=AccountKind.EXPENSE) == 500_000


# ----------------------------------------------------------------------
# The balance invariant itself
# ----------------------------------------------------------------------


def test_unbalanced_legs_are_refused():
    with pytest.raises(UnbalancedTransaction):
        assert_balanced([Leg(BANK, -100), Leg(EWALLET, 99)])


def test_every_builder_produces_balanced_legs():
    cases = [
        build_opening_balance(account_id=BANK, equity_account_id=EQUITY, amount=1_000_000),
        build_income(to_account_id=BANK, income_account_id=INCOME, amount=5_000_000),
        build_expense(from_account_id=BANK, expense_account_id=EXPENSE, amount=35_000),
        build_transfer(from_account_id=BANK, to_account_id=CASH, amount=100_000),
        build_transfer(
            from_account_id=BANK,
            to_account_id=EWALLET,
            amount=100_000,
            fee=1_000,
            fee_expense_account_id=FEE_EXPENSE,
        ),
        build_card_payment(from_account_id=BANK, card_account_id=CARD, amount=800_000),
        build_refund(to_account_id=BANK, expense_account_id=EXPENSE, amount=10_000),
    ]

    for legs in cases:
        assert sum(leg.amount for leg in legs) == 0


# ----------------------------------------------------------------------
# FR09 - free to spend, and shortfalls shown honestly
# ----------------------------------------------------------------------


def test_free_to_spend_subtracts_allocations_and_reserves_once():
    accounts = [
        snapshot(BANK, AccountType.BANK, AccountKind.ASSET, 5_000_000),
        snapshot(CASH, AccountType.CASH, AccountKind.ASSET, 300_000),
    ]

    result = free_to_spend(accounts, allocated_on_liquid=2_000_000, reserved=1_000_000)

    assert result.liquid == 5_300_000
    assert result.amount == 2_300_000
    assert not result.is_shortfall


def test_free_to_spend_reports_a_shortfall_rather_than_zero():
    accounts = [snapshot(BANK, AccountType.BANK, AccountKind.ASSET, 1_000_000)]

    result = free_to_spend(accounts, allocated_on_liquid=1_500_000)

    assert result.amount == -500_000, "a shortfall must keep its sign, not clamp to zero"
    assert result.is_shortfall


def test_debit_card_balance_is_not_added_to_liquid():
    """A debit card draws on its bank account; counting both doubles it."""
    accounts = [
        snapshot(BANK, AccountType.BANK, AccountKind.ASSET, 1_000_000),
        snapshot(uuid.uuid4(), AccountType.DEBIT_CARD, AccountKind.ASSET, 0),
    ]

    assert liquid_balance(accounts) == 1_000_000


# ----------------------------------------------------------------------
# FR03 - money is integer rupiah
# ----------------------------------------------------------------------


@pytest.mark.parametrize("value", [35_000, "35000", 35_000.0, -1_000, 0])
def test_rupiah_accepts_exact_integers(value):
    assert isinstance(rupiah(value), int)


@pytest.mark.parametrize("value", [35_000.5, 0.1 + 0.2, "35.000", "abc", None, True, False])
def test_rupiah_rejects_anything_lossy(value):
    with pytest.raises(MoneyError):
        rupiah(value)


@pytest.mark.parametrize("value", [0, -1])
def test_positive_rupiah_requires_a_positive_amount(value):
    with pytest.raises(MoneyError):
        positive_rupiah(value)


def test_format_rupiah_uses_indonesian_grouping():
    assert format_rupiah(35_000) == "Rp35.000"
    assert format_rupiah(5_000_000) == "Rp5.000.000"
    assert format_rupiah(-1_000) == "-Rp1.000"
    assert format_rupiah(0) == "Rp0"


def test_large_amounts_stay_exact():
    """Well past the point where float64 loses integer precision."""
    big = 9_007_199_254_740_993  # 2**53 + 1
    assert rupiah(big) == big
    assert rupiah(big) + 1 == big + 1
