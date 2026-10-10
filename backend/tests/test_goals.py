"""Goal progress and deposit planning (PRD FR07, FR11, AC06).

Pure, no database. The PRD's own worked example is the centrepiece:
a Rp15,000,000 laptop with Rp3,000,000 up front over six deposits needs
Rp2,000,000 each, and a capacity of Rp1,500,000 should offer eight
deposits, Rp3,000,000 more up front, or Rp500,000 more per period.
"""

from __future__ import annotations

import pytest

from app.domain.goals import (
    GoalStatus,
    ceil_div,
    goal_progress,
    plan_against_capacity,
    split_capacity_by_priority,
)
from app.money import MoneyError

# ----------------------------------------------------------------------
# AC06 - the PRD's worked example, figure for figure
# ----------------------------------------------------------------------


def test_ac06_six_deposits_on_a_fifteen_million_laptop():
    progress = goal_progress(target=15_000_000, saved=3_000_000, remaining_deposits=6)

    assert progress.shortfall == 12_000_000
    assert progress.per_deposit == 2_000_000
    assert progress.percent == 20


def test_ac06_a_capacity_of_one_and_a_half_million_offers_eight_deposits():
    progress = goal_progress(target=15_000_000, saved=3_000_000, remaining_deposits=6)
    plan = plan_against_capacity(progress, capacity=1_500_000)

    assert plan.feasible is False

    by_kind = {a.kind: a.value for a in plan.alternatives}

    assert by_kind["more_deposits"] == 8
    # 12,000,000 - (1,500,000 x 6) = 3,000,000 more up front.
    assert by_kind["extra_upfront"] == 3_000_000
    # 2,000,000 - 1,500,000 = 500,000 more per period.
    assert by_kind["extra_capacity"] == 500_000


def test_a_sufficient_capacity_needs_no_alternatives():
    progress = goal_progress(target=15_000_000, saved=3_000_000, remaining_deposits=6)
    plan = plan_against_capacity(progress, capacity=2_000_000)

    assert plan.feasible is True
    assert plan.alternatives == []


def test_zero_capacity_offers_no_impossible_schedule():
    """With nothing to spare, "extend the schedule" is not an option."""
    progress = goal_progress(target=1_000_000, saved=0, remaining_deposits=5)
    plan = plan_against_capacity(progress, capacity=0)

    assert plan.feasible is False
    assert "more_deposits" not in {a.kind for a in plan.alternatives}


# ----------------------------------------------------------------------
# Rounding
# ----------------------------------------------------------------------


def test_the_required_deposit_rounds_up_so_the_goal_is_actually_reached():
    """10,000 over 3 deposits is 3,333.33; three deposits of 3,333 fall short."""
    progress = goal_progress(target=10_000, saved=0, remaining_deposits=3)

    assert progress.per_deposit == 3_334
    assert progress.per_deposit * 3 >= progress.shortfall


def test_deposits_stay_whole_rupiah():
    progress = goal_progress(target=1_000_000, saved=1, remaining_deposits=7)

    assert isinstance(progress.per_deposit, int)
    assert progress.per_deposit * 7 >= progress.shortfall


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(10, 3, 4), (9, 3, 3), (1, 3, 1), (0, 3, 0), (12_000_000, 1_500_000, 8)],
)
def test_ceil_div(numerator, denominator, expected):
    assert ceil_div(numerator, denominator) == expected


def test_ceil_div_refuses_a_zero_divisor():
    with pytest.raises(ValueError):
        ceil_div(10, 0)


# ----------------------------------------------------------------------
# Edges the PRD calls out
# ----------------------------------------------------------------------


def test_an_overdue_goal_needs_adjustment_rather_than_dividing_by_zero():
    progress = goal_progress(target=10_000_000, saved=4_000_000, remaining_deposits=0)

    assert progress.status is GoalStatus.NEEDS_ADJUSTMENT
    assert progress.per_deposit is None
    assert progress.shortfall == 6_000_000
    assert progress.percent == 40


def test_progress_caps_at_one_hundred_and_reports_the_excess_separately():
    progress = goal_progress(target=10_000_000, saved=12_000_000, remaining_deposits=3)

    assert progress.percent == 100
    assert progress.surplus == 2_000_000
    assert progress.shortfall == 0
    assert progress.is_achieved


def test_a_reached_goal_needs_no_further_deposits():
    progress = goal_progress(target=5_000_000, saved=5_000_000, remaining_deposits=4)

    assert progress.status is GoalStatus.ACHIEVED
    assert progress.per_deposit is None


def test_an_explicitly_paused_goal_keeps_its_status():
    """Pausing is the user's decision; progress must not silently undo it."""
    progress = goal_progress(
        target=5_000_000, saved=5_000_000, remaining_deposits=0, status=GoalStatus.PAUSED
    )

    assert progress.status is GoalStatus.PAUSED


def test_a_goal_with_nothing_saved_is_zero_percent():
    progress = goal_progress(target=5_000_000, saved=0, remaining_deposits=5)

    assert progress.percent == 0
    assert progress.per_deposit == 1_000_000


@pytest.mark.parametrize("target", [0, -1])
def test_a_non_positive_target_is_rejected(target):
    with pytest.raises(MoneyError):
        goal_progress(target=target, saved=0, remaining_deposits=1)


def test_a_fractional_target_is_rejected():
    with pytest.raises(MoneyError):
        goal_progress(target=15_000_000.5, saved=0, remaining_deposits=6)


def test_negative_savings_are_rejected():
    with pytest.raises(ValueError):
        goal_progress(target=1_000_000, saved=-1, remaining_deposits=1)


# ----------------------------------------------------------------------
# Several goals against one capacity
# ----------------------------------------------------------------------


def test_capacity_is_shared_by_priority_and_never_oversubscribed():
    """The PRD forbids recommending more in total than the user can save."""
    goals = [("laptop", 1, 2_000_000), ("liburan", 2, 1_500_000), ("hp", 3, 1_000_000)]

    split = split_capacity_by_priority(goals, capacity=3_000_000)

    assert split["laptop"] == 2_000_000
    assert split["liburan"] == 1_000_000, "gets what is left, not what it asked"
    assert split["hp"] == 0
    assert sum(split.values()) == 3_000_000


def test_a_comfortable_capacity_funds_everything():
    goals = [("laptop", 1, 2_000_000), ("hp", 2, 500_000)]

    split = split_capacity_by_priority(goals, capacity=10_000_000)

    assert split == {"laptop": 2_000_000, "hp": 500_000}
    assert sum(split.values()) == 2_500_000, "no more than each goal needs"


def test_zero_capacity_funds_nothing():
    goals = [("laptop", 1, 2_000_000)]

    assert split_capacity_by_priority(goals, capacity=0) == {"laptop": 0}
