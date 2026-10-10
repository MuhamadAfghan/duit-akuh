"""Budget evaluation (PRD FR08).

A budget is a **plan for spending**, not a claim on cash. The PRD is
explicit that the app must not quietly subtract the whole budget from
free-to-spend — only reserves the user deliberately set aside do that.
So nothing here touches a balance; it compares what was spent in a
period against a limit.

What counts as "spent" is already settled by the ledger: a query over
expense accounts cannot see transfers or card-bill payments, and refunds
credit their category so they net off. See
:mod:`app.services.reporting`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..money import positive_rupiah, rupiah

#: Where "approaching the limit" begins. Early enough to change
#: behaviour, late enough not to cry wolf every week of the month.
WARNING_THRESHOLD_PERCENT = 80


class BudgetState(str, Enum):
    OK = "ok"
    APPROACHING = "approaching"
    EXCEEDED = "exceeded"


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    category: str
    limit: int
    spent: int
    #: ``limit - spent``. Goes negative when overspent, deliberately:
    #: clamping it to zero would hide the overspend, which is the one
    #: thing a budget exists to surface.
    remaining: int
    #: Uncapped, so 130 means 30% over. Unlike a savings goal, exceeding
    #: a budget is the signal, not an excess to tuck away.
    percent: int
    state: BudgetState

    @property
    def overspend(self) -> int:
        return max(0, -self.remaining)


def evaluate(*, category: str, limit: int, spent: int) -> BudgetStatus:
    """Compare spending against a limit.

    ``spent`` may be negative if refunds in the period exceeded purchases
    — unusual but real — and is reported as-is rather than floored, since
    pretending it was zero would misstate the month.
    """
    limit = positive_rupiah(limit)
    spent = rupiah(spent)

    remaining = limit - spent
    percent = spent * 100 // limit

    if spent > limit:
        state = BudgetState.EXCEEDED
    elif percent >= WARNING_THRESHOLD_PERCENT:
        state = BudgetState.APPROACHING
    else:
        state = BudgetState.OK

    return BudgetStatus(
        category=category,
        limit=limit,
        spent=spent,
        remaining=remaining,
        percent=percent,
        state=state,
    )


@dataclass(frozen=True, slots=True)
class BudgetSummary:
    total_limit: int
    total_spent: int
    total_remaining: int
    exceeded: list[str]
    approaching: list[str]


def summarise(statuses: list[BudgetStatus]) -> BudgetSummary:
    """Roll several budgets into one line for the dashboard.

    ``total_remaining`` is the plain sum, so an underspent category can
    offset an overspent one — which is what a person means by "am I
    within budget overall". The per-category names are kept alongside so
    a breach is never hidden by that netting.
    """
    return BudgetSummary(
        total_limit=sum(s.limit for s in statuses),
        total_spent=sum(s.spent for s in statuses),
        total_remaining=sum(s.remaining for s in statuses),
        exceeded=[s.category for s in statuses if s.state is BudgetState.EXCEEDED],
        approaching=[s.category for s in statuses if s.state is BudgetState.APPROACHING],
    )
