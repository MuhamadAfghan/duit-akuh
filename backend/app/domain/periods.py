"""Resolving the periods people actually say (PRD FR06).

"Bulan ini makan berapa" needs a real date range, and the range has to
be computed in the **user's** timezone even though entries are stored in
UTC. For Asia/Jakarta that is a seven-hour shift: a purchase at 06:00 on
1 October local time is 23:00 on 30 September UTC, so a naive UTC month
boundary files it in the wrong month.

Everything here is pure, so the boundaries can be tested directly —
including the awkward cases (year rollover, a 31st in a 30-day month,
DST in timezones that have it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Jakarta"


class PeriodError(ValueError):
    """The requested period could not be understood."""


@dataclass(frozen=True, slots=True)
class Period:
    """A half-open range ``[start, end)`` in UTC, plus how to name it.

    Half-open so a transaction at exactly midnight belongs to one period
    only — with an inclusive end, the boundary instant would be counted
    in both.
    """

    start: datetime
    end: datetime
    label: str

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


def get_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        # An unknown timezone must not break reporting; UTC is a safe,
        # visible fallback.
        return ZoneInfo("UTC")


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc)


def _day_start(day: date, zone: ZoneInfo) -> datetime:
    """Midnight local, as UTC."""
    return _utc(datetime.combine(day, time.min, tzinfo=zone))


def _add_months(day: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month's length.

    31 January minus one month is 31 December, but plus one month is 28
    or 29 February — clamping is what people mean, and it avoids a
    ValueError on the 31st.
    """
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1

    # Last day of the target month, found by stepping back from the first
    # of the following one.
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    return date(year, month, min(day.day, last.day))


MONTH_NAMES = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)


def month_period(year: int, month: int, zone: ZoneInfo) -> Period:
    first = date(year, month, 1)
    next_first = _add_months(first, 1).replace(day=1)

    return Period(
        start=_day_start(first, zone),
        end=_day_start(next_first, zone),
        label=f"{MONTH_NAMES[month - 1]} {year}",
    )


def resolve_period(
    keyword: str | None = None,
    *,
    now: datetime,
    timezone_name: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Period:
    """Turn a keyword, or an explicit pair of dates, into a UTC range.

    ``start`` and ``end`` are **inclusive** local dates, because that is
    what a person means by "1 to 31 October"; the returned range is
    half-open, with ``end`` pushed to the following midnight.
    """
    zone = get_zone(timezone_name)
    today = now.astimezone(zone).date()

    if start or end:
        if not (start and end):
            raise PeriodError("Tanggal awal dan akhir harus diisi keduanya")

        if end < start:
            raise PeriodError("Tanggal akhir tidak boleh sebelum tanggal awal")

        return Period(
            start=_day_start(start, zone),
            end=_day_start(end + timedelta(days=1), zone),
            label=f"{start.isoformat()} sampai {end.isoformat()}",
        )

    keyword = (keyword or "bulan_ini").strip().lower()

    if keyword in {"bulan_ini", "bulan-ini", "this_month"}:
        return month_period(today.year, today.month, zone)

    if keyword in {"bulan_lalu", "bulan-lalu", "last_month"}:
        previous = _add_months(today.replace(day=1), -1)
        return month_period(previous.year, previous.month, zone)

    if keyword in {"hari_ini", "today"}:
        return Period(
            start=_day_start(today, zone),
            end=_day_start(today + timedelta(days=1), zone),
            label="hari ini",
        )

    if keyword in {"minggu_ini", "this_week"}:
        monday = today - timedelta(days=today.weekday())
        return Period(
            start=_day_start(monday, zone),
            end=_day_start(monday + timedelta(days=7), zone),
            label="minggu ini",
        )

    if keyword in {"7_hari", "7d", "last_7_days"}:
        return Period(
            start=_day_start(today - timedelta(days=6), zone),
            end=_day_start(today + timedelta(days=1), zone),
            label="7 hari terakhir",
        )

    if keyword in {"30_hari", "30d", "last_30_days"}:
        return Period(
            start=_day_start(today - timedelta(days=29), zone),
            end=_day_start(today + timedelta(days=1), zone),
            label="30 hari terakhir",
        )

    if keyword in {"tahun_ini", "this_year"}:
        return Period(
            start=_day_start(date(today.year, 1, 1), zone),
            end=_day_start(date(today.year + 1, 1, 1), zone),
            label=str(today.year),
        )

    if keyword in {"semua", "all", "sejak_awal"}:
        # Genuinely unbounded at both ends. Capping the end at "tomorrow"
        # would silently hide a transaction dated in the future - a data
        # entry mistake the user most needs to see, not one to conceal.
        # Still a real range so callers need no special case.
        return Period(
            start=datetime(1970, 1, 1, tzinfo=timezone.utc),
            end=datetime(2200, 1, 1, tzinfo=timezone.utc),
            label="sejak awal",
        )

    raise PeriodError(
        f"Periode '{keyword}' tidak dikenal. Gunakan: hari_ini, minggu_ini, "
        "bulan_ini, bulan_lalu, 7_hari, 30_hari, tahun_ini, semua."
    )


#: Keywords the API and the model may use.
PERIOD_KEYWORDS = (
    "hari_ini",
    "minggu_ini",
    "bulan_ini",
    "bulan_lalu",
    "7_hari",
    "30_hari",
    "tahun_ini",
    "semua",
)
