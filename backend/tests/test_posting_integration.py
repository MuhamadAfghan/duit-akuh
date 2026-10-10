"""Database-level guarantees: idempotency, atomicity, isolation.

These are the parts of the PRD that cannot be proven with pure functions,
because they are properties of the database — a unique constraint, a
rollback, a WHERE clause on ``user_id``.

Requires PostgreSQL; see ``conftest.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.domain.errors import (
    AccountArchived,
    AmbiguousAccount,
    CrossUserAccess,
    InsufficientBalance,
    UnbalancedTransaction,
)
from app.domain.ledger import Leg, build_expense, build_transfer
from app.models import (
    Account,
    AccountKind,
    AccountType,
    AuditEvent,
    Entry,
    Transaction,
    TransactionType,
)
from app.services.accounts import (
    expense_category,
    find_accounts_by_name,
    open_account_with_balance,
    resolve_account,
)
from app.services.posting import account_balance, account_snapshots, post_transaction

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def make_bank(session, user, name="BCA", alias="bca", balance=5_000_000):
    account, _ = open_account_with_balance(
        session,
        user_id=user.id,
        name=name,
        account_type=AccountType.BANK,
        alias=alias,
        opening_balance=balance,
        occurred_at=NOW,
    )
    return account


# ----------------------------------------------------------------------
# AC04 - a confirmation sent twice creates exactly one transaction
# ----------------------------------------------------------------------


def test_ac04_duplicate_confirmation_posts_once(session, user):
    bank = make_bank(session, user)
    category = expense_category(session, user.id)
    key = f"op-{uuid.uuid4()}"

    legs = build_expense(from_account_id=bank.id, expense_account_id=category.id, amount=35_000)

    first = post_transaction(
        session,
        user_id=user.id,
        tx_type=TransactionType.EXPENSE,
        occurred_at=NOW,
        legs=legs,
        idempotency_key=key,
    )
    second = post_transaction(
        session,
        user_id=user.id,
        tx_type=TransactionType.EXPENSE,
        occurred_at=NOW,
        legs=legs,
        idempotency_key=key,
    )

    assert first.replayed is False
    assert second.replayed is True, "the retry must be recognised, not posted again"
    assert first.transaction.id == second.transaction.id

    count = session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == user.id, Transaction.type == TransactionType.EXPENSE)
    )
    assert count == 1

    # And the balance moved only once.
    assert account_balance(session, user.id, bank.id) == 5_000_000 - 35_000


def test_different_keys_post_separately(session, user):
    bank = make_bank(session, user)
    category = expense_category(session, user.id)

    for _ in range(3):
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=build_expense(
                from_account_id=bank.id, expense_account_id=category.id, amount=10_000
            ),
            idempotency_key=f"op-{uuid.uuid4()}",
        )

    assert account_balance(session, user.id, bank.id) == 5_000_000 - 30_000


def test_same_key_is_scoped_per_user(session, user, other_user):
    """Two users may legitimately use the same key; they must not collide."""
    bank_a = make_bank(session, user)
    bank_b = make_bank(session, other_user, name="Mandiri", alias="mandiri")
    cat_a = expense_category(session, user.id)
    cat_b = expense_category(session, other_user.id)

    key = "same-key"

    post_transaction(
        session,
        user_id=user.id,
        tx_type=TransactionType.EXPENSE,
        occurred_at=NOW,
        legs=build_expense(from_account_id=bank_a.id, expense_account_id=cat_a.id, amount=1_000),
        idempotency_key=key,
    )
    result = post_transaction(
        session,
        user_id=other_user.id,
        tx_type=TransactionType.EXPENSE,
        occurred_at=NOW,
        legs=build_expense(from_account_id=bank_b.id, expense_account_id=cat_b.id, amount=2_000),
        idempotency_key=key,
    )

    assert result.replayed is False
    assert account_balance(session, other_user.id, bank_b.id) == 5_000_000 - 2_000


# ----------------------------------------------------------------------
# AC08 - no cross-user access
# ----------------------------------------------------------------------


def test_ac08_cannot_post_against_another_users_account(session, user, other_user):
    victim_bank = make_bank(session, other_user, name="Victim BCA", alias="victim")
    attacker_category = expense_category(session, user.id)

    with pytest.raises(CrossUserAccess):
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=build_expense(
                from_account_id=victim_bank.id,
                expense_account_id=attacker_category.id,
                amount=1_000_000,
            ),
            idempotency_key=f"op-{uuid.uuid4()}",
        )

    # The victim's balance is untouched.
    assert account_balance(session, other_user.id, victim_bank.id) == 5_000_000


def test_ac08_balance_queries_are_scoped_to_the_owner(session, user, other_user):
    victim_bank = make_bank(session, other_user, name="Victim BCA", alias="victim")

    # Asking as the wrong user returns zero, never the real figure.
    assert account_balance(session, user.id, victim_bank.id) == 0
    assert account_balance(session, other_user.id, victim_bank.id) == 5_000_000


def test_ac08_snapshots_never_include_another_users_accounts(session, user, other_user):
    make_bank(session, user, name="Mine", alias="mine")
    make_bank(session, other_user, name="Theirs", alias="theirs")

    names = {s.name for s in account_snapshots(session, user.id)}

    assert "Mine" in names
    assert "Theirs" not in names


def test_ac08_account_search_is_scoped_to_the_owner(session, user, other_user):
    make_bank(session, other_user, name="BCA Utama", alias="bca")

    assert find_accounts_by_name(session, user.id, "BCA") == []


# ----------------------------------------------------------------------
# AC04 - ambiguity is refused, never guessed
# ----------------------------------------------------------------------


def test_ac04_ambiguous_account_name_raises_instead_of_guessing(session, user):
    make_bank(session, user, name="BCA Tahapan", alias="tahapan")
    make_bank(session, user, name="BCA Bisnis", alias="bisnis", balance=1_000_000)

    with pytest.raises(AmbiguousAccount) as excinfo:
        resolve_account(session, user.id, "BCA")

    # The error names the candidates so the UI can offer a choice.
    assert "BCA Tahapan" in str(excinfo.value)
    assert "BCA Bisnis" in str(excinfo.value)


def test_unique_alias_resolves(session, user):
    make_bank(session, user, name="BCA Tahapan", alias="tahapan")
    make_bank(session, user, name="Jago", alias="jago", balance=1_000_000)

    assert resolve_account(session, user.id, "jago").name == "Jago"


# ----------------------------------------------------------------------
# Atomicity - a rejected posting leaves nothing behind
# ----------------------------------------------------------------------


def count_entries(session, user_id) -> int:
    return session.scalar(select(func.count()).select_from(Entry).where(Entry.user_id == user_id))


def test_unbalanced_posting_writes_nothing(session, user):
    bank = make_bank(session, user)
    balance_before = account_balance(session, user.id, bank.id)
    entries_before = count_entries(session, user.id)

    with pytest.raises(UnbalancedTransaction):
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=[Leg(bank.id, -100_000)],  # one-sided: money would vanish
            idempotency_key=f"op-{uuid.uuid4()}",
        )

    assert account_balance(session, user.id, bank.id) == balance_before
    # Nothing at all was written - not a half-posted leg, not an orphan.
    assert count_entries(session, user.id) == entries_before


def test_overdraft_is_refused_without_explicit_confirmation(session, user):
    bank = make_bank(session, user, balance=100_000)
    category = expense_category(session, user.id)

    with pytest.raises(InsufficientBalance):
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=build_expense(
                from_account_id=bank.id, expense_account_id=category.id, amount=150_000
            ),
            idempotency_key=f"op-{uuid.uuid4()}",
        )

    assert account_balance(session, user.id, bank.id) == 100_000


def test_overdraft_is_allowed_when_explicitly_confirmed(session, user):
    """The PRD permits a negative balance after a warning and confirmation."""
    bank = make_bank(session, user, balance=100_000)
    category = expense_category(session, user.id)

    post_transaction(
        session,
        user_id=user.id,
        tx_type=TransactionType.EXPENSE,
        occurred_at=NOW,
        legs=build_expense(from_account_id=bank.id, expense_account_id=category.id, amount=150_000),
        idempotency_key=f"op-{uuid.uuid4()}",
        allow_negative=True,
    )

    assert account_balance(session, user.id, bank.id) == -50_000


def test_posting_to_an_archived_account_is_refused(session, user):
    bank = make_bank(session, user)
    category = expense_category(session, user.id)
    bank.is_archived = True
    session.flush()

    with pytest.raises(AccountArchived):
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=build_expense(
                from_account_id=bank.id, expense_account_id=category.id, amount=1_000
            ),
            idempotency_key=f"op-{uuid.uuid4()}",
        )


# ----------------------------------------------------------------------
# End-to-end arithmetic through the database (AC01, AC02)
# ----------------------------------------------------------------------


def test_ac01_through_the_database(session, user):
    bank, _ = open_account_with_balance(
        session,
        user_id=user.id,
        name="BCA",
        account_type=AccountType.BANK,
        alias="bca",
        opening_balance=1_000_000,
        occurred_at=NOW,
    )
    wallet, _ = open_account_with_balance(
        session,
        user_id=user.id,
        name="GoPay",
        account_type=AccountType.EWALLET,
        alias="gopay",
        opening_balance=100_000,
        occurred_at=NOW,
    )

    from app.domain.balances import category_total, liquid_balance

    snapshots = account_snapshots(session, user.id)

    assert liquid_balance(snapshots) == 1_100_000
    assert category_total(snapshots, kind=AccountKind.INCOME) == 0


def test_ac02_through_the_database(session, user):
    bank = make_bank(session, user, balance=1_000_000)
    wallet, _ = open_account_with_balance(
        session,
        user_id=user.id,
        name="GoPay",
        account_type=AccountType.EWALLET,
        alias="gopay",
        opening_balance=0,
        occurred_at=NOW,
    )
    fee_category = expense_category(session, user.id, "Biaya admin")

    post_transaction(
        session,
        user_id=user.id,
        tx_type=TransactionType.TRANSFER,
        occurred_at=NOW,
        legs=build_transfer(
            from_account_id=bank.id,
            to_account_id=wallet.id,
            amount=100_000,
            fee=1_000,
            fee_expense_account_id=fee_category.id,
        ),
        idempotency_key=f"op-{uuid.uuid4()}",
    )

    assert account_balance(session, user.id, bank.id) == 1_000_000 - 101_000
    assert account_balance(session, user.id, wallet.id) == 100_000
    assert account_balance(session, user.id, fee_category.id) == 1_000


# ----------------------------------------------------------------------
# Constraints that the database itself enforces
# ----------------------------------------------------------------------


def test_duplicate_alias_is_rejected_by_the_database(session, user):
    """Two wallets sharing an alias would make AC04's ambiguity unresolvable."""
    from sqlalchemy.exc import IntegrityError

    make_bank(session, user, name="BCA Satu", alias="bca")

    session.add(
        Account(
            user_id=user.id,
            name="BCA Dua",
            alias="bca",
            type=AccountType.BANK,
            kind=AccountKind.ASSET,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_zero_amount_entry_is_rejected_by_the_database(session, user):
    from sqlalchemy.exc import IntegrityError

    bank = make_bank(session, user)

    tx = Transaction(
        user_id=user.id,
        type=TransactionType.EXPENSE,
        occurred_at=NOW,
        idempotency_key=f"op-{uuid.uuid4()}",
    )
    tx.entries = [Entry(user_id=user.id, account_id=bank.id, amount=0)]
    session.add(tx)

    with pytest.raises(IntegrityError):
        session.flush()


# ----------------------------------------------------------------------
# Audit trail (PRD section 9, AC08)
# ----------------------------------------------------------------------


def test_posting_writes_an_audit_event_pointing_at_the_transaction(session, user):
    bank = make_bank(session, user)
    category = expense_category(session, user.id)

    result = post_transaction(
        session,
        user_id=user.id,
        tx_type=TransactionType.EXPENSE,
        occurred_at=NOW,
        legs=build_expense(from_account_id=bank.id, expense_account_id=category.id, amount=35_000),
        idempotency_key=f"op-{uuid.uuid4()}",
        operation_id="op-abc",
    )

    event = session.scalar(
        select(AuditEvent).where(
            AuditEvent.user_id == user.id,
            AuditEvent.object_id == result.transaction.id,
            AuditEvent.action == "transaction.posted",
        )
    )

    assert event is not None, "a posting must leave an audit trail"
    # Regression guard: object_id was previously None because the column
    # default only runs at INSERT, so the event pointed at nothing.
    assert event.object_id == result.transaction.id
    assert event.operation_id == "op-abc"
    assert event.after["type"] == "expense"
    assert sum(e["amount"] for e in event.after["entries"]) == 0


def test_a_replayed_confirmation_does_not_add_a_second_audit_event(session, user):
    bank = make_bank(session, user)
    category = expense_category(session, user.id)
    key = f"op-{uuid.uuid4()}"
    legs = build_expense(from_account_id=bank.id, expense_account_id=category.id, amount=35_000)

    results = [
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=legs,
            idempotency_key=key,
        )
        for _ in range(2)
    ]

    assert results[1].replayed is True

    # Scoped to this transaction: the account's opening balance also wrote
    # a 'transaction.posted' event, so counting by action alone would be
    # measuring the wrong thing.
    count = session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.user_id == user.id,
            AuditEvent.object_id == results[0].transaction.id,
        )
    )

    assert count == 1


def test_a_rejected_posting_leaves_no_audit_event(session, user):
    """An audit trail must not claim a posting that never happened."""
    bank = make_bank(session, user, balance=100_000)
    category = expense_category(session, user.id)

    before = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id == user.id)
    )

    with pytest.raises(InsufficientBalance):
        post_transaction(
            session,
            user_id=user.id,
            tx_type=TransactionType.EXPENSE,
            occurred_at=NOW,
            legs=build_expense(
                from_account_id=bank.id, expense_account_id=category.id, amount=999_000
            ),
            idempotency_key=f"op-{uuid.uuid4()}",
        )

    after = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id == user.id)
    )

    assert after == before


def test_an_exact_name_beats_a_substring_match(session, user):
    """A bank and its own credit card is an ordinary pairing.

    "CC BCA" contains "BCA", so a substring-only search made "pakai BCA"
    ambiguous forever for anyone holding both.
    """
    make_bank(session, user, name="BCA", alias="bca")
    open_account_with_balance(
        session,
        user_id=user.id,
        name="CC BCA",
        account_type=AccountType.CREDIT_CARD,
        alias="cc",
        occurred_at=NOW,
    )

    assert resolve_account(session, user.id, "BCA").name == "BCA"
    assert resolve_account(session, user.id, "bca").name == "BCA"
    # The card is still reachable by its own name and alias.
    assert resolve_account(session, user.id, "CC BCA").name == "CC BCA"
    assert resolve_account(session, user.id, "cc").name == "CC BCA"


def test_a_substring_still_resolves_when_nothing_matches_exactly(session, user):
    make_bank(session, user, name="BCA Tahapan", alias="tahapan")

    assert resolve_account(session, user.id, "Tahapan").name == "BCA Tahapan"


def test_a_substring_matching_several_accounts_is_still_ambiguous(session, user):
    """Precedence must not turn a genuine ambiguity into a guess."""
    make_bank(session, user, name="BCA Tahapan", alias="tahapan")
    make_bank(session, user, name="BCA Bisnis", alias="bisnis", balance=1_000_000)

    with pytest.raises(AmbiguousAccount):
        resolve_account(session, user.id, "BCA")


def test_two_accounts_named_the_same_are_impossible_so_exact_is_unique(session, user):
    """The unique alias constraint plus distinct names keep tier one singular."""
    make_bank(session, user, name="BCA", alias="bca")

    assert len(find_accounts_by_name(session, user.id, "BCA")) == 1
