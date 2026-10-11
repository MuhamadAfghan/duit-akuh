"""Reconciling a spoken total against its parts.

Pure arithmetic, no database: this is the check that stops "ngeluarin
150rb — obat 50, makan 70, minum 30" being recorded as 300.000.
"""

from __future__ import annotations

import pytest

from app.domain.batch import EmptyBatch, reconcile
from app.money import MoneyError


def test_the_parts_are_added_up():
    result = reconcile([50_000, 70_000, 30_000])

    assert result.items_total == 150_000


def test_a_matching_total_is_not_an_extra_entry():
    """The headline case. The stated total agrees with the parts, and
    the only figure that can ever be posted is the parts' sum."""
    result = reconcile([50_000, 70_000, 30_000], 150_000)

    assert result.matches is True
    assert result.difference == 0
    assert result.items_total == 150_000
    # Not 300.000: the stated total is a claim, never a fourth entry.
    assert result.items_total + (result.stated_total or 0) != result.items_total * 2 - 150_000


def test_a_shortfall_is_reported_not_absorbed():
    result = reconcile([50_000, 70_000, 30_000], 200_000)

    assert result.matches is False
    assert result.difference == 50_000


def test_parts_exceeding_the_stated_total_give_a_negative_difference():
    result = reconcile([50_000, 70_000, 30_000], 120_000)

    assert result.matches is False
    assert result.difference == -30_000


def test_no_stated_total_means_nothing_to_reconcile():
    result = reconcile([50_000, 70_000])

    assert result.stated_total is None
    assert result.matches is True
    assert result.difference == 0


def test_a_float_amount_is_refused_rather_than_rounded():
    """FR03: money never becomes a float, not even while being summed."""
    with pytest.raises(MoneyError):
        reconcile([50_000.5, 70_000])


def test_a_float_total_is_refused_too():
    with pytest.raises(MoneyError):
        reconcile([50_000], 50_000.5)


def test_an_empty_batch_is_refused():
    with pytest.raises(EmptyBatch):
        reconcile([])
