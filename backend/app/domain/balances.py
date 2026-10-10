"""Dashboard indicators (PRD FR09).

Pure functions over plain snapshots, so the definitions that decide
whether the app double-counts someone's money can be tested directly.

The one rule running through all of it: **a given rupiah is counted
once.** A debit card's money already sits in its bank account. A credit
limit is not money. An allocation earmarks a balance that is already in
``liquid``, so subtracting it is a reduction, never a separate pot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import LIQUID_TYPES, AccountKind, AccountType


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """An account plus its computed balance, in integer rupiah.

    ``balance`` is ``SUM(entries.amount)``: for an asset the amount held,
    for a liability a negative number whose magnitude is the debt.
    """

    id: object
    name: str
    type: AccountType
    kind: AccountKind
    balance: int
    is_archived: bool = False
    credit_limit: int | None = None

    @property
    def debt(self) -> int:
        """Amount owed, as a positive number. Zero for non-liabilities."""
        if self.kind is not AccountKind.LIABILITY:
            return 0
        return max(0, -self.balance)


@dataclass(frozen=True, slots=True)
class FreeToSpend:
    """Breakdown of spendable money, so the number can be explained."""

    liquid: int
    allocated: int
    reserved: int
    amount: int
    #: True when the result is negative. The PRD requires a shortfall to be
    #: shown as its real negative value, not hidden behind a zero.
    is_shortfall: bool = field(default=False)


def liquid_balance(accounts: list[AccountSnapshot]) -> int:
    """Bank + e-wallet + cash.

    Excludes locked deposits and credit limits, and excludes debit cards —
    a debit card holds no money of its own, so including it would count
    its bank account twice.
    """
    return sum(a.balance for a in accounts if a.type in LIQUID_TYPES and not a.is_archived)


def total_debt(accounts: list[AccountSnapshot]) -> int:
    """All recorded liabilities, as a positive number."""
    return sum(a.debt for a in accounts if not a.is_archived)


def net_worth(accounts: list[AccountSnapshot]) -> int:
    """Recorded assets minus recorded liabilities.

    Only real accounts count: income, expense and equity are bookkeeping
    counterparts, not things the user owns.
    """
    assets = sum(
        a.balance
        for a in accounts
        if a.kind is AccountKind.ASSET and a.type in LIQUID_TYPES and not a.is_archived
    )
    return assets - total_debt(accounts)


def free_to_spend(
    accounts: list[AccountSnapshot],
    *,
    allocated_on_liquid: int = 0,
    reserved: int = 0,
) -> FreeToSpend:
    """Liquid balance minus goal allocations and chosen reserves.

    ``allocated_on_liquid`` must only include allocations sitting on liquid
    accounts, otherwise money that was never in ``liquid`` would be
    subtracted from it.

    Budgets are deliberately **not** subtracted here. A budget is a
    spending plan, not a claim on cash; only reserves the user explicitly
    chose reduce this figure (FR08).
    """
    liquid = liquid_balance(accounts)
    amount = liquid - allocated_on_liquid - reserved

    return FreeToSpend(
        liquid=liquid,
        allocated=allocated_on_liquid,
        reserved=reserved,
        amount=amount,
        is_shortfall=amount < 0,
    )


def category_total(
    accounts: list[AccountSnapshot], *, kind: AccountKind = AccountKind.EXPENSE
) -> int:
    """Total booked to income or expense categories, as a positive number.

    Expense accounts carry positive (debit) balances and income accounts
    negative (credit) ones, so income is negated to read naturally. Refunds
    already reduce their category through a credit entry, so they need no
    special handling here.
    """
    if kind is AccountKind.EXPENSE:
        return sum(a.balance for a in accounts if a.kind is AccountKind.EXPENSE)

    if kind is AccountKind.INCOME:
        return -sum(a.balance for a in accounts if a.kind is AccountKind.INCOME)

    raise ValueError(f"category_total hanya untuk INCOME atau EXPENSE, bukan {kind}")


@dataclass(frozen=True, slots=True)
class ImpactRow:
    """What one account's balance would become if a draft were posted."""

    account_id: object
    name: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


def impact_of(legs, accounts: list[AccountSnapshot]) -> list[ImpactRow]:
    """Compute a draft's effect on balances without writing anything.

    This is what the chat's confirmation card shows before the user
    commits (FR05: every financial change must display its impact first).
    It is pure, so the preview and the eventual posting cannot disagree
    about arithmetic — they fold the same legs the same way.

    Accounts not touched by the draft are omitted. System accounts are
    included: a category's running total moving is part of the effect.
    """
    by_id = {a.id: a for a in accounts}

    deltas: dict[object, int] = {}
    order: list[object] = []

    for leg in legs:
        if leg.account_id not in deltas:
            order.append(leg.account_id)
        deltas[leg.account_id] = deltas.get(leg.account_id, 0) + leg.amount

    rows = []

    for account_id in order:
        snapshot = by_id.get(account_id)
        before = snapshot.balance if snapshot else 0
        rows.append(
            ImpactRow(
                account_id=account_id,
                name=snapshot.name if snapshot else "(tidak dikenal)",
                before=before,
                after=before + deltas[account_id],
            )
        )

    return rows
