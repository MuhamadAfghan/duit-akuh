"""The posting engine: building balanced entries for each kind of event.

Everything here is **pure**. These functions take account ids and integer
rupiah and return entry legs; they never touch the database. That is
deliberate — the PRD's money rules are exactly the part that has to be
provably right, so they are testable without a database, a user, or a
network.

Persistence lives in :mod:`app.services.posting`.

Sign convention (see :mod:`app.models`): debit positive, credit negative.
Every builder returns legs summing to zero, and :func:`assert_balanced`
is the backstop.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ..money import positive_rupiah, rupiah
from .errors import InvalidTransaction, UnbalancedTransaction


@dataclass(frozen=True, slots=True)
class Leg:
    """One side of a transaction: an account and a signed integer delta."""

    account_id: uuid.UUID
    amount: int

    def __post_init__(self) -> None:
        if self.amount == 0:
            raise InvalidTransaction("Leg tidak boleh bernilai nol")


def debit(account_id: uuid.UUID, amount: int) -> Leg:
    """Increase an asset or expense (or decrease a liability)."""
    return Leg(account_id, positive_rupiah(amount))


def credit(account_id: uuid.UUID, amount: int) -> Leg:
    """Increase a liability, income or equity (or decrease an asset)."""
    return Leg(account_id, -positive_rupiah(amount))


def assert_balanced(legs: list[Leg]) -> None:
    """Refuse any transaction whose legs do not sum to exactly zero.

    This is the single check that makes "money is never created or
    destroyed" structural. Integer arithmetic means it is exact — there is
    no epsilon to tune.
    """
    if not legs:
        raise InvalidTransaction("Transaksi harus punya minimal satu entry")

    total = sum(leg.amount for leg in legs)

    if total != 0:
        raise UnbalancedTransaction(
            f"Entry tidak seimbang: selisih {total}. "
            "Setiap transaksi harus berjumlah nol (debit = kredit)."
        )


# ----------------------------------------------------------------------
# Builders, one per event the PRD names in FR02
# ----------------------------------------------------------------------


def build_opening_balance(
    *, account_id: uuid.UUID, equity_account_id: uuid.UUID, amount: int
) -> list[Leg]:
    """Starting balance for an account.

    Credits a system *equity* account, never income — AC01 requires income
    for the period to stay zero when opening balances are set.
    """
    amount = positive_rupiah(amount)
    legs = [debit(account_id, amount), credit(equity_account_id, amount)]
    assert_balanced(legs)
    return legs


def build_income(
    *, to_account_id: uuid.UUID, income_account_id: uuid.UUID, amount: int
) -> list[Leg]:
    """Money arriving from outside: debit the wallet, credit income."""
    amount = positive_rupiah(amount)
    legs = [debit(to_account_id, amount), credit(income_account_id, amount)]
    assert_balanced(legs)
    return legs


def build_expense(
    *, from_account_id: uuid.UUID, expense_account_id: uuid.UUID, amount: int
) -> list[Leg]:
    """Money spent: credit the source, debit the expense category.

    The source may be an asset (cash/bank/e-wallet) or a credit-card
    liability. For a card this is the whole of AC03's first half: the
    expense is recognised now and the card's debt grows by the same amount.
    """
    amount = positive_rupiah(amount)
    legs = [credit(from_account_id, amount), debit(expense_account_id, amount)]
    assert_balanced(legs)
    return legs


def build_transfer(
    *,
    from_account_id: uuid.UUID,
    to_account_id: uuid.UUID,
    amount: int,
    fee: int = 0,
    fee_expense_account_id: uuid.UUID | None = None,
) -> list[Leg]:
    """Moving the user's own money between their own accounts.

    Covers transfer, top-up and cash withdrawal — the PRD treats all three
    identically. No income or expense account is touched, which is why a
    transfer can never be reported as either (FR02).

    A fee is a genuine cost and is recorded **separately** as an expense,
    so the source is reduced by ``amount + fee`` while the destination
    receives exactly ``amount``. That is AC02 precisely.
    """
    amount = positive_rupiah(amount)
    fee = rupiah(fee)

    if fee < 0:
        raise InvalidTransaction("Biaya admin tidak boleh negatif")

    if from_account_id == to_account_id:
        raise InvalidTransaction("Akun sumber dan tujuan tidak boleh sama")

    if fee and fee_expense_account_id is None:
        raise InvalidTransaction("Biaya admin harus punya kategori pengeluaran")

    legs = [credit(from_account_id, amount + fee), debit(to_account_id, amount)]

    if fee:
        legs.append(debit(fee_expense_account_id, fee))

    assert_balanced(legs)
    return legs


def build_card_payment(
    *, from_account_id: uuid.UUID, card_account_id: uuid.UUID, amount: int
) -> list[Leg]:
    """Paying down a credit card bill.

    Debits the card liability (reducing debt) and credits the bank. It
    deliberately touches **no expense account**: the spending was already
    recognised when the purchase happened, and counting it again here is
    exactly the double-count AC03 forbids.
    """
    amount = positive_rupiah(amount)

    if from_account_id == card_account_id:
        raise InvalidTransaction("Kartu tidak bisa membayar dirinya sendiri")

    legs = [debit(card_account_id, amount), credit(from_account_id, amount)]
    assert_balanced(legs)
    return legs


def build_refund(
    *, to_account_id: uuid.UUID, expense_account_id: uuid.UUID, amount: int
) -> list[Leg]:
    """A refund of an earlier purchase.

    The exact mirror of an expense: it credits the original expense
    category (reducing that category's total) and debits the account the
    money returns to — restoring an asset balance, or reducing card debt
    when the refund lands on the card (FR02).
    """
    amount = positive_rupiah(amount)
    legs = [debit(to_account_id, amount), credit(expense_account_id, amount)]
    assert_balanced(legs)
    return legs


def build_reversal(original_legs: list[Leg]) -> list[Leg]:
    """Invert a transaction to undo it.

    Corrections never delete rows. A correction is the original plus this
    reversal plus a fresh transaction, leaving the whole history traceable
    (FR02/AC08). Negating a balanced set stays balanced by construction.
    """
    if not original_legs:
        raise InvalidTransaction("Tidak ada entry untuk dibalik")

    legs = [Leg(leg.account_id, -leg.amount) for leg in original_legs]
    assert_balanced(legs)
    return legs
