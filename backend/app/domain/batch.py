"""Several entries from one sentence (PRD FR02, FR03).

People do not narrate one transaction at a time. "Tadi pagi ngeluarin
150rb — obat 50rb, makan 70rb, minum 30rb" is four numbers and three
transactions, and the fourth number is the trap: recorded alongside the
others it doubles the spending to 300.000.

So the stated total is never a posting. It is a **claim about the
parts**, and the only thing this module does with it is check whether
the parts agree. The check lives here, in the pure layer, because it is
arithmetic about money and the model must not be the one doing it — the
same reason every other figure is recomputed from the database.

Nothing here decides what to do about a mismatch. Dropping the
difference, adding it as an extra entry, or editing the parts are the
user's call, made at the confirmation; a backend that picked one would
be guessing with somebody's money.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..money import rupiah
from .errors import DomainError


class EmptyBatch(DomainError):
    """A batch with no entries is not a batch."""

    def __init__(self) -> None:
        super().__init__("Nggak ada catatan yang bisa disimpan")


@dataclass(frozen=True)
class Reconciliation:
    """What the parts add up to, against what was said."""

    #: The sum of the entries. This is the only figure that gets posted.
    items_total: int
    #: What the person said the whole thing came to, when they said it.
    stated_total: int | None
    #: stated - items. Positive means something is unaccounted for;
    #: negative means the parts come to more than the stated total.
    difference: int
    #: True when there is nothing to resolve: either no total was
    #: stated, or it matches the parts exactly.
    matches: bool


def reconcile(amounts: Sequence[int], stated_total: int | None = None) -> Reconciliation:
    """Add the parts up and compare them with the stated total.

    Every amount goes through `rupiah`, so a float that drifted in from
    the model's output is refused here rather than rounded into the
    ledger (FR03).
    """
    if not amounts:
        raise EmptyBatch

    items_total = sum(rupiah(amount) for amount in amounts)

    if stated_total is None:
        return Reconciliation(
            items_total=items_total, stated_total=None, difference=0, matches=True
        )

    stated = rupiah(stated_total)
    difference = stated - items_total

    return Reconciliation(
        items_total=items_total,
        stated_total=stated,
        difference=difference,
        matches=difference == 0,
    )
