"""Request and response shapes for the money endpoints.

Amounts cross the wire as JSON integers of rupiah. ``StrictInt`` is used
deliberately: without it Pydantic would happily coerce ``35000.4`` to an
int and silently round money away, which FR03 forbids.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt

from ..models import AccountType, TransactionType

#: A positive amount of rupiah. Direction is expressed by the transaction
#: type, never by a negative number.
PositiveRupiah = Annotated[StrictInt, Field(gt=0)]
NonNegativeRupiah = Annotated[StrictInt, Field(ge=0)]


# ----------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------


class AccountCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: AccountType
    alias: str | None = Field(default=None, max_length=60)
    opening_balance: NonNegativeRupiah = 0
    credit_limit: PositiveRupiah | None = None
    occurred_at: datetime | None = None


class AccountUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    alias: str | None = Field(default=None, max_length=60)
    credit_limit: PositiveRupiah | None = None
    is_archived: bool | None = None


class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    alias: str | None
    type: AccountType
    balance: StrictInt
    #: Positive amount owed; 0 for anything that is not a liability.
    debt: StrictInt
    credit_limit: StrictInt | None
    is_archived: bool


class SummaryOut(BaseModel):
    """The FR09 dashboard indicators.

    ``free_to_spend`` keeps its sign when negative: the PRD requires a
    shortfall to be shown as a real figure rather than hidden behind a
    zero.
    """

    liquid: StrictInt
    net_worth: StrictInt
    total_debt: StrictInt
    allocated: StrictInt
    free_to_spend: StrictInt
    is_shortfall: bool
    expense_total: StrictInt
    income_total: StrictInt


# ----------------------------------------------------------------------
# Transactions
# ----------------------------------------------------------------------


class _DraftBase(BaseModel):
    occurred_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)
    merchant: str | None = Field(default=None, max_length=200)
    #: Must be set explicitly to let an asset balance go below zero. The
    #: PRD allows it only after a warning and an explicit confirmation.
    allow_negative: bool = False


class ExpenseDraft(_DraftBase):
    type: Literal["expense"]
    amount: PositiveRupiah
    from_account_id: uuid.UUID
    #: Category name; created on first use.
    category: str = Field(default="Lain-lain", max_length=120)


class IncomeDraft(_DraftBase):
    type: Literal["income"]
    amount: PositiveRupiah
    to_account_id: uuid.UUID
    category: str = Field(default="Pemasukan lain", max_length=120)


class TransferDraft(_DraftBase):
    """Covers transfer, top-up and cash withdrawal — identical in the ledger."""

    type: Literal["transfer"]
    amount: PositiveRupiah
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    #: Recorded as its own expense leg, never folded into the amount.
    fee: NonNegativeRupiah = 0
    fee_category: str = Field(default="Biaya admin", max_length=120)


class CardPaymentDraft(_DraftBase):
    type: Literal["card_payment"]
    amount: PositiveRupiah
    from_account_id: uuid.UUID
    card_account_id: uuid.UUID


class RefundDraft(_DraftBase):
    type: Literal["refund"]
    amount: PositiveRupiah
    to_account_id: uuid.UUID
    category: str = Field(max_length=120)


Draft = Annotated[
    ExpenseDraft | IncomeDraft | TransferDraft | CardPaymentDraft | RefundDraft,
    Field(discriminator="type"),
]


class ImpactOut(BaseModel):
    account_id: uuid.UUID
    name: str
    before: StrictInt
    after: StrictInt
    delta: StrictInt


class PreviewOut(BaseModel):
    """A draft's effect, computed without writing anything."""

    impact: list[ImpactOut]
    #: True when posting would drive an asset negative, so the UI can warn
    #: before asking for confirmation rather than after a rejection.
    would_overdraw: bool


class EntryOut(BaseModel):
    account_id: uuid.UUID
    amount: StrictInt


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: TransactionType
    occurred_at: datetime
    description: str | None
    merchant: str | None
    note: str | None
    entries: list[EntryOut]
    #: True when this request matched an earlier idempotency key and no
    #: new transaction was created.
    replayed: bool = False
