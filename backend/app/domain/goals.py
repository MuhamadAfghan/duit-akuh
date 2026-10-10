"""Goal progress and deposit planning (PRD FR07, FR11).

Pure arithmetic over integer rupiah, so the figures a user plans their
savings around can be checked without a database.

Two rules shape most of this:

* **Rounding is always up.** A deposit of exactly shortfall/n would leave
  the goal a few rupiah short when n does not divide evenly, so the
  required deposit is ceiling-divided. Being a little early beats being
  short on the deadline.
* **An overdue goal is a state, not a division.** Once no deposit dates
  remain, there is nothing to divide by; the PRD asks for a "needs
  adjustment" status rather than an error or a fabricated number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..money import positive_rupiah, rupiah


def ceil_div(numerator: int, denominator: int) -> int:
    """Integer ceiling division. Keeps money an exact integer of rupiah."""
    if denominator <= 0:
        raise ValueError("Pembagi harus lebih besar dari nol")

    return -(-numerator // denominator)


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    CANCELLED = "cancelled"
    #: Deadline passed while still short. Not an error state — the PRD
    #: wants the gap against schedule shown, with the user deciding.
    NEEDS_ADJUSTMENT = "needs_adjustment"


@dataclass(frozen=True, slots=True)
class GoalProgress:
    target: int
    saved: int
    #: max(0, target - saved). Never negative, so an over-funded goal
    #: does not report a negative shortfall.
    shortfall: int
    #: Capped at 100 for display. `surplus` carries the excess instead,
    #: because a progress bar past full tells the user nothing.
    percent: int
    surplus: int
    remaining_deposits: int
    #: None when no deposit dates remain — there is nothing to divide by.
    per_deposit: int | None
    status: GoalStatus

    @property
    def is_achieved(self) -> bool:
        return self.shortfall == 0


def goal_progress(
    *,
    target: int,
    saved: int,
    remaining_deposits: int,
    status: GoalStatus = GoalStatus.ACTIVE,
) -> GoalProgress:
    """Where a goal stands, and what each remaining deposit must be.

    ``saved`` is the total of valid allocations; it is a view of money
    already held, never a separate balance (FR07/AC05).
    """
    target = positive_rupiah(target)
    saved = rupiah(saved)
    remaining_deposits = int(remaining_deposits)

    if saved < 0:
        raise ValueError("Dana terkumpul tidak boleh negatif")

    if remaining_deposits < 0:
        raise ValueError("Jumlah setoran tersisa tidak boleh negatif")

    shortfall = max(0, target - saved)
    surplus = max(0, saved - target)

    if shortfall == 0:
        resolved = GoalStatus.ACHIEVED if status is GoalStatus.ACTIVE else status
        return GoalProgress(
            target=target,
            saved=saved,
            shortfall=0,
            percent=100,
            surplus=surplus,
            remaining_deposits=remaining_deposits,
            per_deposit=None,
            status=resolved,
        )

    if remaining_deposits == 0:
        # Past the deadline and still short: report the gap, do not
        # divide by zero and do not invent a schedule.
        return GoalProgress(
            target=target,
            saved=saved,
            shortfall=shortfall,
            percent=min(100, saved * 100 // target),
            surplus=0,
            remaining_deposits=0,
            per_deposit=None,
            status=GoalStatus.NEEDS_ADJUSTMENT if status is GoalStatus.ACTIVE else status,
        )

    return GoalProgress(
        target=target,
        saved=saved,
        shortfall=shortfall,
        percent=min(100, saved * 100 // target),
        surplus=0,
        remaining_deposits=remaining_deposits,
        per_deposit=ceil_div(shortfall, remaining_deposits),
        status=status,
    )


# ----------------------------------------------------------------------
# Planning against a capacity (FR11)
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Alternative:
    kind: str
    label: str
    #: The figure the user would change to, in integer rupiah or a count.
    value: int


@dataclass(frozen=True, slots=True)
class GoalPlan:
    progress: GoalProgress
    capacity: int
    #: True when the plan already fits what the user can save.
    feasible: bool
    #: Only populated when it does not fit.
    alternatives: list[Alternative] = field(default_factory=list)


def plan_against_capacity(progress: GoalProgress, capacity: int) -> GoalPlan:
    """Check a goal against what the user can actually set aside.

    When the required deposit exceeds capacity, the PRD's worked example
    offers three ways out: more deposits, more money up front, or more
    capacity per period. All three are offered rather than one being
    chosen, because which is possible is the user's call.
    """
    capacity = rupiah(capacity)

    if capacity < 0:
        raise ValueError("Kapasitas tidak boleh negatif")

    required = progress.per_deposit

    if required is None or required <= capacity:
        return GoalPlan(progress=progress, capacity=capacity, feasible=True)

    alternatives: list[Alternative] = []

    if capacity > 0:
        deposits_needed = ceil_div(progress.shortfall, capacity)
        alternatives.append(
            Alternative(
                kind="more_deposits",
                label=f"Perpanjang jadi {deposits_needed} setoran",
                value=deposits_needed,
            )
        )

    # Extra up front so the remaining deposits fit the capacity exactly.
    extra_upfront = progress.shortfall - capacity * progress.remaining_deposits

    if extra_upfront > 0:
        alternatives.append(
            Alternative(
                kind="extra_upfront",
                label=f"Tambah dana awal {extra_upfront}",
                value=extra_upfront,
            )
        )

    alternatives.append(
        Alternative(
            kind="extra_capacity",
            label=f"Naikkan setoran {required - capacity} per periode",
            value=required - capacity,
        )
    )

    return GoalPlan(progress=progress, capacity=capacity, feasible=False, alternatives=alternatives)


def split_capacity_by_priority(
    goals: list[tuple[object, int, int]], capacity: int
) -> dict[object, int]:
    """Share a limited capacity across goals, highest priority first.

    ``goals`` is ``(id, priority, needed_per_period)``, lower priority
    number meaning more important.

    The PRD is explicit that the total recommended across all goals must
    not exceed the same capacity — which is only possible if later goals
    get what is left rather than what they asked for.
    """
    capacity = rupiah(capacity)

    if capacity < 0:
        raise ValueError("Kapasitas tidak boleh negatif")

    remaining = capacity
    allocation: dict[object, int] = {}

    for goal_id, _priority, needed in sorted(goals, key=lambda g: (g[1], str(g[0]))):
        share = min(max(0, needed), remaining)
        allocation[goal_id] = share
        remaining -= share

    return allocation
