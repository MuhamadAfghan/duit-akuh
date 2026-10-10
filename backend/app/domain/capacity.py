"""How much the user can actually set aside (PRD FR10).

Cash-flow projection, not a spending report, and the difference matters:

* **A credit-card bill is counted when it is paid**, not when the
  purchases were made. The purchases already formed the bill; counting
  both in the same horizon would subtract the same money twice. The
  reporting module does the opposite — it counts spending at purchase
  time — and both are right for their own question.
* **Internal transfers and opening balances are excluded** from income.
  Moving your own money is not earning it (FR02/AC01).
* **One-off income the user flags is excluded** from the reliable
  figure, since next month will not repeat it.

Everything here is pure; :mod:`app.services.capacity` supplies the
numbers from the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..money import rupiah


@dataclass(frozen=True, slots=True)
class CapacityInputs:
    """Monthly averages, in integer rupiah."""

    reliable_income: int
    cash_expenses: int
    #: Card bills and other obligations falling due in the horizon,
    #: counted at their payment date.
    obligations: int
    #: Reserves the user explicitly chose to hold back. Only these reduce
    #: capacity — a budget does not (FR08).
    reserves: int = 0
    #: Deposits already promised to existing goals.
    committed_deposits: int = 0


@dataclass(frozen=True, slots=True)
class Capacity:
    """What is left over per period, and how that was arrived at."""

    inputs: CapacityInputs
    #: Income minus outgoings and reserves, before existing goals.
    gross: int
    #: After deposits already committed — what a *new* goal can use.
    available: int
    #: Whole calendar months the figures were derived from.
    months_observed: int
    #: False when fewer than `MINIMUM_MONTHS` were available, so the
    #: caller must ask the user to confirm an estimate rather than
    #: present this as measured.
    reliable: bool
    notes: list[str] = field(default_factory=list)


#: The PRD's default observation window.
MINIMUM_MONTHS = 3


def compute_capacity(inputs: CapacityInputs, *, months_observed: int) -> Capacity:
    """Project what can be saved per period.

    A negative result is returned as-is. Someone spending more than they
    earn needs to see that, not a zero that implies breaking even.
    """
    reliable_income = rupiah(inputs.reliable_income)
    cash_expenses = rupiah(inputs.cash_expenses)
    obligations = rupiah(inputs.obligations)
    reserves = rupiah(inputs.reserves)
    committed = rupiah(inputs.committed_deposits)

    gross = reliable_income - cash_expenses - obligations - reserves
    available = gross - committed

    notes: list[str] = []

    if months_observed < MINIMUM_MONTHS:
        notes.append(
            f"Baru {months_observed} bulan penuh tercatat; angka ini perkiraan "
            f"dan sebaiknya dikonfirmasi manual."
        )

    if gross < 0:
        notes.append("Pengeluaran melebihi pemasukan pada periode yang tercatat.")

    if committed and available < 0:
        notes.append("Setoran target yang sudah disepakati melebihi kapasitas.")

    return Capacity(
        inputs=inputs,
        gross=gross,
        available=available,
        months_observed=months_observed,
        reliable=months_observed >= MINIMUM_MONTHS,
        notes=notes,
    )
