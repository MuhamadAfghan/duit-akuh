"""Period boundaries (PRD FR06).

Pure, no database. The cases that matter are the ones that look fine
until they are not: a month boundary in a non-UTC timezone, the turn of
the year, and a 31st in a month that has 30 days.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.periods import PeriodError, get_zone, month_period, resolve_period

JAKARTA = "Asia/Jakarta"
WIB = ZoneInfo(JAKARTA)


def at(local: str, zone: str = JAKARTA) -> datetime:
    """A local wall-clock time, as an aware datetime."""
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(zone))


# ----------------------------------------------------------------------
# The timezone trap
# ----------------------------------------------------------------------


def test_month_starts_at_local_midnight_not_utc_midnight():
    """Jakarta is UTC+7, so the month begins at 17:00 UTC the day before.

    Using a UTC boundary would file a purchase made at 06:00 on 1 October
    local time into September.
    """
    period = resolve_period("bulan_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    assert period.start == datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)
    assert period.end == datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)


def test_an_early_morning_local_purchase_falls_in_the_right_month():
    period = resolve_period("bulan_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    # 1 October, 06:00 in Jakarta == 30 September, 23:00 UTC.
    early = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)

    assert period.contains(early), "belongs to October for a Jakarta user"


def test_a_late_night_local_purchase_does_not_leak_into_next_month():
    period = resolve_period("bulan_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    # 31 October, 23:30 Jakarta == 31 October, 16:30 UTC - still October.
    late = datetime(2026, 10, 31, 16, 30, tzinfo=timezone.utc)
    # 1 November, 00:30 Jakarta == 31 October, 17:30 UTC - November.
    after = datetime(2026, 10, 31, 17, 30, tzinfo=timezone.utc)

    assert period.contains(late)
    assert not period.contains(after)


def test_the_range_is_half_open_so_midnight_belongs_to_one_period_only():
    october = resolve_period("bulan_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)
    november = month_period(2026, 11, WIB)

    assert october.end == november.start
    assert not october.contains(october.end)
    assert november.contains(november.start)


def test_an_unknown_timezone_falls_back_to_utc_rather_than_failing():
    assert str(get_zone("Mars/Olympus")) == "UTC"
    assert str(get_zone(None)) == JAKARTA


# ----------------------------------------------------------------------
# Keywords
# ----------------------------------------------------------------------


def test_last_month_across_the_year_boundary():
    period = resolve_period("bulan_lalu", now=at("2027-01-05T10:00"), timezone_name=JAKARTA)

    assert period.label == "Desember 2026"
    assert period.start == datetime(2026, 11, 30, 17, 0, tzinfo=timezone.utc)


def test_last_month_from_the_31st_does_not_crash():
    """31 March minus a month is February, which has no 31st."""
    period = resolve_period("bulan_lalu", now=at("2026-03-31T10:00"), timezone_name=JAKARTA)

    assert period.label == "Februari 2026"


def test_today_is_one_local_day():
    period = resolve_period("hari_ini", now=at("2026-10-10T23:59"), timezone_name=JAKARTA)

    assert period.start == datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc)
    assert period.end == datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)


def test_this_week_starts_on_monday():
    # 2026-10-10 is a Saturday.
    period = resolve_period("minggu_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    # Monday 5 October local == 4 October 17:00 UTC.
    assert period.start == datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)


def test_seven_days_includes_today():
    period = resolve_period("7_hari", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    assert period.contains(datetime(2026, 10, 10, 5, 0, tzinfo=timezone.utc))
    # Seven days inclusive of today means it starts on the 4th.
    assert period.start == datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)


def test_this_year():
    period = resolve_period("tahun_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    assert period.label == "2026"
    assert period.start == datetime(2025, 12, 31, 17, 0, tzinfo=timezone.utc)


def test_defaults_to_this_month():
    default = resolve_period(None, now=at("2026-10-10T09:00"), timezone_name=JAKARTA)
    explicit = resolve_period("bulan_ini", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    assert default == explicit


def test_an_unknown_keyword_lists_the_valid_ones():
    with pytest.raises(PeriodError) as excinfo:
        resolve_period("kapan_kapan", now=at("2026-10-10T09:00"))

    assert "bulan_ini" in str(excinfo.value)


# ----------------------------------------------------------------------
# Explicit dates
# ----------------------------------------------------------------------


def test_explicit_dates_are_inclusive_of_the_end_day():
    period = resolve_period(
        now=at("2026-10-10T09:00"),
        timezone_name=JAKARTA,
        start=date(2026, 10, 1),
        end=date(2026, 10, 7),
    )

    # The 7th, late evening local, must still be inside.
    assert period.contains(datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc))
    assert not period.contains(datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc))


def test_a_reversed_range_is_rejected():
    with pytest.raises(PeriodError):
        resolve_period(now=at("2026-10-10T09:00"), start=date(2026, 10, 7), end=date(2026, 10, 1))


def test_half_a_range_is_rejected():
    with pytest.raises(PeriodError):
        resolve_period(now=at("2026-10-10T09:00"), start=date(2026, 10, 1))


def test_all_time_is_unbounded_so_a_future_date_is_not_hidden():
    """A transaction dated in the future is a mistake worth seeing.

    Capping "sejak awal" at today would quietly drop it from the one
    view meant to show everything.
    """
    period = resolve_period("semua", now=at("2026-10-10T09:00"), timezone_name=JAKARTA)

    assert period.contains(datetime(1999, 1, 1, tzinfo=timezone.utc))
    assert period.contains(datetime(2030, 6, 1, tzinfo=timezone.utc))
