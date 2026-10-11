"""Goal allocation rules (PRD FR07, AC05).

An allocation is an earmark on money that is already in an account. It
creates no ledger entry, so it cannot change net assets — the thing AC05
checks. What it *can* do is over-promise, which is what these rules
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..money import format_rupiah, positive_rupiah
from .errors import AllocationExceedsBalance


@dataclass(frozen=True, slots=True)
class AllocationSnapshot:
    account_id: object
    goal_id: object
    amount: int


def allocated_on_account(allocations: list[AllocationSnapshot], account_id: object) -> int:
    """Total currently earmarked on one account."""
    return sum(a.amount for a in allocations if a.account_id == account_id)


def check_allocation_fits(
    *,
    account_id: object,
    account_balance: int,
    existing: list[AllocationSnapshot],
    new_amount: int,
    replacing_goal_id: object | None = None,
) -> int:
    """Verify a new or changed allocation still fits the account's balance.

    The invariant: the sum of active allocations on an account may not
    exceed its **positive** balance. A negative balance can support no
    allocation at all.

    ``replacing_goal_id`` is the goal whose allocation is being changed;
    its current amount is excluded from the existing total so that editing
    an allocation is not counted against itself.

    :returns: the resulting total allocated on the account.
    :raises AllocationExceedsBalance: if it would not fit.
    """
    new_amount = positive_rupiah(new_amount)

    others = sum(
        a.amount for a in existing if a.account_id == account_id and a.goal_id != replacing_goal_id
    )

    total = others + new_amount
    headroom = max(0, account_balance)

    if total > headroom:
        raise AllocationExceedsBalance(
            f"Alokasi {format_rupiah(total)} melebihi saldo "
            f"{format_rupiah(headroom)} pada akun tersebut. "
            f"Sisa yang bisa dialokasikan: {format_rupiah(max(0, headroom - others))}."
        )

    return total
