"""Money as integer rupiah.

PRD FR03 forbids floating point for money. Every amount in this codebase is
a Python ``int`` of whole rupiah, stored as PostgreSQL ``BIGINT``.

Python's ``int`` is arbitrary precision, so there is no overflow to worry
about in application code; BIGINT caps at ~9.2e18 rupiah, far beyond any
personal balance. The real risk is a ``float`` sneaking in from JSON, a
division, or a percentage calculation — which is what the guards here
exist to catch, loudly and early.
"""

from __future__ import annotations

from typing import Any

# BIGINT bounds. Amounts outside this cannot be stored, so reject them at
# the edge rather than letting PostgreSQL raise mid-transaction.
MIN_RUPIAH = -(2**63)
MAX_RUPIAH = 2**63 - 1


class MoneyError(ValueError):
    """Raised when a value cannot be trusted as an amount of money."""


def rupiah(value: Any) -> int:
    """Coerce a value to integer rupiah, refusing anything lossy.

    Accepts ``int`` and ``str`` of digits. Accepts ``float`` **only** when it
    is exactly integral (e.g. ``35000.0`` from JSON), because a fractional
    float means the caller already lost precision somewhere upstream and
    silently rounding would hide the bug.

    ``bool`` is rejected outright: it is an ``int`` subclass in Python, and
    ``rupiah(True) == 1`` is never what anyone meant.
    """
    if isinstance(value, bool):
        raise MoneyError(f"Nominal tidak boleh boolean: {value!r}")

    if isinstance(value, int):
        amount = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise MoneyError(
                f"Nominal harus bilangan bulat rupiah, bukan {value!r}. "
                "Uang tidak boleh berupa pecahan float (FR03)."
            )
        amount = int(value)
    elif isinstance(value, str):
        text = value.strip()
        try:
            amount = int(text)
        except ValueError as exc:
            raise MoneyError(f"Nominal bukan bilangan bulat: {value!r}") from exc
    else:
        raise MoneyError(f"Tipe nominal tidak didukung: {type(value).__name__}")

    if not MIN_RUPIAH <= amount <= MAX_RUPIAH:
        raise MoneyError(f"Nominal di luar jangkauan BIGINT: {amount}")

    return amount


def positive_rupiah(value: Any) -> int:
    """Coerce to integer rupiah and require it to be strictly positive.

    Transaction amounts are always stated as a positive magnitude; direction
    is expressed by the ledger entries, never by a negative input.
    """
    amount = rupiah(value)

    if amount <= 0:
        raise MoneyError(f"Nominal harus lebih besar dari nol, bukan {amount}")

    return amount


def format_rupiah(amount: int) -> str:
    """Format for humans: ``35000`` -> ``"Rp35.000"``.

    Indonesian grouping uses ``.`` as the thousands separator.
    """
    amount = rupiah(amount)
    sign = "-" if amount < 0 else ""
    grouped = f"{abs(amount):,}".replace(",", ".")
    return f"{sign}Rp{grouped}"
