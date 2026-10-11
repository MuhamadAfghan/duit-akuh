"""Creating and finding accounts.

Also home to alias resolution, which is where AC04 lives: when a spoken
name like "BCA" matches two accounts, the system must ask rather than
pick one.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.errors import AccountNotFound, AmbiguousAccount, DuplicateAccount
from ..domain.ledger import build_opening_balance
from ..models import KIND_BY_TYPE, Account, AccountType, TransactionType
from ..money import positive_rupiah
from .posting import PostResult, post_transaction

#: Fixed names for the per-user system accounts. They are created lazily
#: and never shown as wallets.
OPENING_BALANCE_NAME = "Saldo awal"
UNCATEGORISED_EXPENSE_NAME = "Lain-lain"
UNCATEGORISED_INCOME_NAME = "Pemasukan lain"
ADMIN_FEE_NAME = "Biaya admin"


def _normalise_alias(value: str | None) -> str | None:
    """Aliases are matched case-insensitively, so they are stored folded."""
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def create_account(
    session: Session,
    *,
    user_id: uuid.UUID,
    name: str,
    account_type: AccountType,
    alias: str | None = None,
    credit_limit: int | None = None,
    linked_account_id: uuid.UUID | None = None,
    is_system: bool = False,
) -> Account:
    """Create an account. Does not post an opening balance.

    Refuses a name the user already has in use. A duplicate wallet is a
    money bug, not a tidiness one: each copy carries its own opening
    balance, so "Bank Jago" existing twice overstates net assets by a
    wallet that was never real. System accounts are exempt — they are
    looked up by name in :func:`get_system_account`, which is what keeps
    exactly one of each.
    """
    if not is_system:
        clash = session.scalar(
            select(Account).where(
                Account.user_id == user_id,
                func.lower(Account.name) == name.strip().lower(),
                Account.is_archived.is_(False),
            )
        )

        if clash is not None:
            raise DuplicateAccount(
                f"Kantong '{clash.name}' sudah ada. "
                "Pakai yang itu, ganti namanya, atau arsipkan dulu yang lama."
            )

    account = Account(
        user_id=user_id,
        name=name.strip(),
        alias=_normalise_alias(alias),
        type=account_type,
        kind=KIND_BY_TYPE[account_type],
        credit_limit=credit_limit,
        linked_account_id=linked_account_id,
        is_system=is_system,
    )
    session.add(account)
    session.flush()
    return account


def get_system_account(
    session: Session, user_id: uuid.UUID, account_type: AccountType, name: str
) -> Account:
    """Fetch a system account, creating it on first use."""
    account = session.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.type == account_type,
            Account.name == name,
            Account.is_system.is_(True),
        )
    )

    if account is not None:
        return account

    return create_account(
        session,
        user_id=user_id,
        name=name,
        account_type=account_type,
        is_system=True,
    )


def opening_balance_account(session: Session, user_id: uuid.UUID) -> Account:
    """The equity counterpart for starting balances.

    Separate from income on purpose: AC01 requires income for the period
    to stay zero when opening balances are entered.
    """
    return get_system_account(session, user_id, AccountType.OPENING_BALANCE, OPENING_BALANCE_NAME)


def expense_category(
    session: Session, user_id: uuid.UUID, name: str = UNCATEGORISED_EXPENSE_NAME
) -> Account:
    return get_system_account(session, user_id, AccountType.EXPENSE_CATEGORY, name)


def income_category(
    session: Session, user_id: uuid.UUID, name: str = UNCATEGORISED_INCOME_NAME
) -> Account:
    return get_system_account(session, user_id, AccountType.INCOME_CATEGORY, name)


def open_account_with_balance(
    session: Session,
    *,
    user_id: uuid.UUID,
    name: str,
    account_type: AccountType,
    opening_balance: int = 0,
    alias: str | None = None,
    credit_limit: int | None = None,
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> tuple[Account, PostResult | None]:
    """Create an account and, if given, post its starting balance.

    The balance is posted against the equity account, so it adds to assets
    without ever registering as income.
    """
    account = create_account(
        session,
        user_id=user_id,
        name=name,
        account_type=account_type,
        alias=alias,
        credit_limit=credit_limit,
    )

    if not opening_balance:
        return account, None

    amount = positive_rupiah(opening_balance)
    equity = opening_balance_account(session, user_id)

    result = post_transaction(
        session,
        user_id=user_id,
        tx_type=TransactionType.OPENING,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        legs=build_opening_balance(
            account_id=account.id, equity_account_id=equity.id, amount=amount
        ),
        idempotency_key=idempotency_key or f"opening:{account.id}",
        description=f"Saldo awal {account.name}",
        source="setup",
    )

    return account, result


def find_accounts_by_name(session: Session, user_id: uuid.UUID, text: str) -> list[Account]:
    """A user's wallets matching ``text``, preferring exact matches.

    Two tiers, and the precedence matters:

    1. The alias, or the full name, matching exactly.
    2. The name merely containing the text.

    A substring match is only consulted when nothing matches exactly.
    Without that, anyone with a "BCA" account **and** a "CC BCA" credit
    card — an ordinary pairing — would find "pakai BCA" ambiguous
    forever, because the card's name contains the bank's. Saying "BCA"
    when an account is called exactly that is not ambiguous.

    System and archived accounts are excluded; they are not things a
    user spends from by name.
    """
    needle = text.strip().lower()

    if not needle:
        return []

    def query(condition):
        return list(
            session.scalars(
                select(Account)
                .where(
                    Account.user_id == user_id,
                    Account.is_system.is_(False),
                    Account.is_archived.is_(False),
                    condition,
                )
                .order_by(Account.name)
            ).all()
        )

    exact = query((Account.alias == needle) | (func.lower(Account.name) == needle))

    if exact:
        return exact

    return list(
        session.scalars(
            select(Account)
            .where(
                Account.user_id == user_id,
                Account.is_system.is_(False),
                Account.is_archived.is_(False),
                func.lower(Account.name).contains(needle),
            )
            .order_by(Account.name)
        ).all()
    )


def resolve_account(session: Session, user_id: uuid.UUID, text: str) -> Account:
    """Resolve a spoken account name to exactly one account.

    Raises rather than guessing when the name is ambiguous. AC04 requires
    an ambiguous message to post nothing and ask the user to choose, so
    returning a "best match" here would defeat the whole check.
    """
    matches = find_accounts_by_name(session, user_id, text)

    if not matches:
        raise AccountNotFound(f"Tidak ada kantong yang cocok dengan '{text}'")

    if len(matches) > 1:
        raise AmbiguousAccount(
            f"'{text}' cocok dengan {len(matches)} kantong: "
            + ", ".join(a.name for a in matches)
            + ". Pilih salah satu."
        )

    return matches[0]
