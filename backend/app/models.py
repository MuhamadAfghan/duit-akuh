"""Database model.

The ledger is **double-entry**: every transaction is a set of entries whose
signed amounts sum to exactly zero. That is not bookkeeping ceremony — it
is what makes the PRD's hardest rules structural instead of a pile of
special cases:

* A transfer credits one account and debits another. It touches no income
  or expense account, so it *cannot* show up as either (FR02/AC02).
* A credit-card purchase debits an expense and credits the card liability.
  Paying the bill later debits the liability and credits the bank. The
  expense entry is never touched again, so the spend cannot be counted
  twice (AC03).
* An opening balance debits the asset and credits a system equity account,
  not income, so starting balances never inflate earnings (AC01).

Sign convention: **debit is positive, credit is negative.**

    asset/expense  increase with a positive amount
    liability/income/equity  increase with a negative amount

So an account's ``balance`` is ``SUM(entries.amount)``. For assets that is
the balance as a person would state it. For a liability the amount owed is
the negation of that sum, which ``Account.debt`` exposes.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


# ----------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------


class AccountKind(str, enum.Enum):
    """The accounting nature of an account, which fixes its sign behaviour."""

    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"
    #: Opening balances and other adjustments that must not be income.
    EQUITY = "equity"


class AccountType(str, enum.Enum):
    """The product-level type the user actually picks (PRD FR01)."""

    BANK = "bank"
    EWALLET = "ewallet"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    #: A debit card is a payment instrument over a bank account. It holds no
    #: balance of its own, so it never appears in an entry.
    DEBIT_CARD = "debit_card"
    #: System accounts, created per user, not shown as wallets.
    INCOME_CATEGORY = "income_category"
    EXPENSE_CATEGORY = "expense_category"
    OPENING_BALANCE = "opening_balance"


#: Which accounting nature each product type carries.
KIND_BY_TYPE: dict[AccountType, AccountKind] = {
    AccountType.BANK: AccountKind.ASSET,
    AccountType.EWALLET: AccountKind.ASSET,
    AccountType.CASH: AccountKind.ASSET,
    AccountType.CREDIT_CARD: AccountKind.LIABILITY,
    AccountType.DEBIT_CARD: AccountKind.ASSET,
    AccountType.INCOME_CATEGORY: AccountKind.INCOME,
    AccountType.EXPENSE_CATEGORY: AccountKind.EXPENSE,
    AccountType.OPENING_BALANCE: AccountKind.EQUITY,
}

#: Types the user holds money in. Only these count toward liquid balance;
#: a debit card is excluded because its money already sits in its bank
#: account and counting both would double it (FR09).
LIQUID_TYPES = frozenset({AccountType.BANK, AccountType.EWALLET, AccountType.CASH})


class TransactionType(str, enum.Enum):
    """What the user did, for reporting. The entries define the effect."""

    OPENING = "opening"
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    CARD_PAYMENT = "card_payment"
    REFUND = "refund"
    REVERSAL = "reversal"


class TransactionStatus(str, enum.Enum):
    POSTED = "posted"
    #: Superseded by a reversal. History is kept; nothing is deleted (FR02).
    REVERSED = "reversed"


# ----------------------------------------------------------------------
# Mixins
# ----------------------------------------------------------------------


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )


class OwnedMixin:
    """Every row belongs to exactly one user.

    AC08 makes zero cross-account access a release gate, so ownership is a
    non-nullable column on every table rather than something inferred by a
    join at query time.
    """

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    #: argon2/bcrypt hash. Never the password itself.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Jakarta")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Account(Base, OwnedMixin, TimestampMixin):
    """A place money sits, or a system account for income/expense/equity."""

    __tablename__ = "accounts"
    __table_args__ = (
        # Two wallets may not share a conversational alias for one user:
        # "BCA" matching two accounts must be impossible to create silently,
        # since AC04 requires ambiguity to be resolved rather than guessed.
        UniqueConstraint("user_id", "alias", name="uq_accounts_user_alias"),
        Index("ix_accounts_user_type", "user_id", "type"),
        CheckConstraint("credit_limit IS NULL OR credit_limit >= 0", name="ck_accounts_limit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Lowercased short name the user says in chat; NULL for system accounts.
    alias: Mapped[str | None] = mapped_column(String(60), nullable=True)

    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type"), nullable=False
    )
    kind: Mapped[AccountKind] = mapped_column(
        Enum(AccountKind, name="account_kind"), nullable=False
    )

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")

    #: Credit cards only. An available limit is NOT money and never counts
    #: as an asset or as spendable (FR01/FR09) - it lives here, apart from
    #: any balance.
    credit_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    #: A debit card points at the bank account it draws from.
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )

    #: Archived, never deleted: an account with history must keep it (FR01).
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Optimistic concurrency, so two devices editing the same version are
    #: detected rather than silently last-write-wins (FR03).
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    entries: Mapped[list[Entry]] = relationship(back_populates="account")

    @property
    def is_liquid(self) -> bool:
        return self.type in LIQUID_TYPES and not self.is_archived


class Transaction(Base, OwnedMixin, TimestampMixin):
    """One atomic financial event, made of balanced entries."""

    __tablename__ = "transactions"
    __table_args__ = (
        # The idempotency guarantee behind AC04: the same confirmation sent
        # twice collides here and the caller is handed the original.
        UniqueConstraint("user_id", "idempotency_key", name="uq_transactions_idempotency"),
        Index("ix_transactions_user_occurred", "user_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)

    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"), nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.POSTED,
    )

    #: When it happened in the user's timezone, as opposed to created_at,
    #: which is when we recorded it. The PRD requires both.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Where this came from: chat, manual form, receipt OCR, import.
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    #: Links a refund or reversal back to what it corrects, so history stays
    #: traceable instead of rows disappearing (FR02/AC08).
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=True
    )

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    entries: Mapped[list[Entry]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", lazy="selectin"
    )


class Entry(Base, OwnedMixin):
    """One leg of a transaction: an account and a signed delta.

    Debit positive, credit negative. The legs of a transaction always sum
    to zero; see :mod:`app.domain.ledger`.
    """

    __tablename__ = "entries"
    __table_args__ = (
        # A zero-amount leg carries no information and usually signals a
        # construction bug, so it is rejected at the database.
        CheckConstraint("amount <> 0", name="ck_entries_nonzero"),
        Index("ix_entries_account", "account_id"),
        Index("ix_entries_user_account", "user_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )

    #: Integer rupiah. Positive debit, negative credit.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="entries")
    account: Mapped[Account] = relationship(back_populates="entries")


class Goal(Base, OwnedMixin, TimestampMixin):
    """A savings target (PRD FR07). Funded by allocations, not by a balance."""

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    allocations: Mapped[list[Allocation]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )


class Allocation(Base, OwnedMixin, TimestampMixin):
    """Earmarks part of an account's balance for a goal.

    Purely virtual: an allocation moves no money and creates no entry, so
    it can never change net assets (FR07/AC05). The rule that allocations
    on an account may not exceed its balance is enforced in
    :mod:`app.domain.allocations`, which has the balance to check against.
    """

    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_allocations_positive"),
        UniqueConstraint("goal_id", "account_id", name="uq_allocation_goal_account"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    goal: Mapped[Goal] = relationship(back_populates="allocations")


class AuditEvent(Base, OwnedMixin):
    """Append-only trail of who changed what (PRD section 9, AC08)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    #: Correlates every row written by one confirmed action, so a multi-step
    #: plan can be traced or audited as a unit (FR15).
    operation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Session(Base, TimestampMixin):
    """A logged-in session, keyed by a random token held in a cookie.

    Only the token's **hash** is stored. A database leak then exposes no
    usable session, the same reasoning that applies to passwords — except
    the token is 256 bits of randomness, so a fast hash is sufficient and
    a slow KDF would only cost latency on every request.
    """

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_active", "user_id", "revoked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: SHA-256 of the raw token. Unique so a lookup is a single index hit.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set on logout or when sessions are revoked after a password change.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    #: Coarse client info to help a user recognise their own sessions.
    #: Deliberately not an IP address: that is personal data the app has no
    #: product need to retain.
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    def is_valid(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


class LoginAttempt(Base):
    """Failed sign-in attempts, for the throttling PRD section 9 requires.

    Only failures are recorded, and only an email and a timestamp — enough
    to rate-limit without building a log of when someone signs in.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_email_time", "email", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    #: Stored lowercased. Not a foreign key: attempts against an address
    #: that was never registered must be throttled too.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class DraftStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    #: The world moved on - a balance changed, an account was archived -
    #: so the draft's preview no longer describes what would happen.
    STALE = "stale"


class Conversation(Base, OwnedMixin, TimestampMixin):
    """The single persistent thread (PRD FR14, FR15).

    One per user, enforced by a unique constraint rather than convention:
    the PRD is explicit that there is one main chat continuing across
    sessions and devices, with no per-topic threads to switch between.
    """

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("user_id", name="uq_conversation_per_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)


class Message(Base, OwnedMixin):
    """One turn in the thread."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_seq", "conversation_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    #: Ordering key. NOT created_at: PostgreSQL's now() returns the
    #: transaction start time, so every message written in one turn - the
    #: user's message, the reply, and each card - shares a timestamp and
    #: the thread renders in arbitrary order. A sequence cannot tie.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"), nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Set when this turn is a card rather than prose. The card's content
    #: lives on the Draft row so it cannot drift from what gets posted.
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True
    )


class Draft(Base, OwnedMixin, TimestampMixin):
    """A proposed change, awaiting confirmation (PRD FR05).

    The model proposes; this row records what the backend *validated* and
    what it showed the user. Confirming posts from this row, never from
    the model's output again — so what was previewed is what is written,
    and a replayed confirmation cannot smuggle in different numbers.
    """

    __tablename__ = "drafts"
    __table_args__ = (Index("ix_drafts_user_status", "user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)

    #: What kind of change: matches the API draft discriminator.
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status"), nullable=False, default=DraftStatus.PENDING
    )

    #: The validated draft body, in the same shape the REST API accepts.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    #: The impact rows shown to the user, stored so the card can be
    #: re-rendered later exactly as it was.
    impact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: Doubles as the idempotency key when confirmed, which is what makes
    #: tapping a stale card twice harmless (AC13).
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )


class AiRequestLog(Base, OwnedMixin):
    """Per-request AI telemetry required by PRD section 13.

    Records what was asked of the model and what it cost, but never the
    prompt or the answer: those are the user's financial life, and the
    retention policy for them is a separate decision.
    """

    __tablename__ = "ai_request_logs"
    __table_args__ = (Index("ix_ai_logs_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    #: chat | vision | stt
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    prompt_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Names only, never arguments: arguments carry amounts and accounts.
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
