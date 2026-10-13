"""Executing the model's tool calls.

Everything arriving here is **untrusted**. The model produced it from a
user's sentence, and the PRD treats model output — like receipt text —
as data, never as instruction. So each handler re-validates types,
re-resolves account names through the same ambiguity rules the REST API
uses, and recomputes every figure from the database.

Read tools return data. Propose tools return a stored :class:`Draft`
with its impact; they never write to the ledger.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from functools import partial
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import aliased

from ...domain.balances import (
    category_total,
    free_to_spend,
    impact_of,
    liquid_balance,
    net_worth,
    total_debt,
)
from ...domain.batch import reconcile
from ...domain.categories import resolve_expense, resolve_income
from ...domain.errors import AmbiguousAccount, DomainError
from ...domain.periods import Period, PeriodError, get_zone, resolve_period
from ...domain.simulation import SimulationError, simulate_deposit, simulate_regular_saving
from ...models import (
    LIQUID_TYPES,
    Account,
    AccountKind,
    Allocation,
    Budget,
    Draft,
    DraftStatus,
    Entry,
    Goal,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)
from ...money import MoneyError, positive_rupiah, rupiah
from ..accounts import expense_category, income_category, resolve_account
from ..budgets import report as budget_report
from ..capacity import estimate as estimate_capacity
from ..drafts import build_legs
from ..goals import headroom, saved_for
from ..posting import account_snapshots
from ..reporting import category_total_for_period, known_expense_categories, period_report

#: Account types the model may create. Deliberately excludes debit cards
#: and anything system-owned.
CREATABLE_TYPES = {"bank", "ewallet", "cash", "credit_card"}


class ToolError(Exception):
    """A tool call that cannot be honoured.

    Returned to the model as the tool's result rather than raised to the
    user: the model should ask a clarifying question, which is exactly
    what AC04 wants when an account name is ambiguous.
    """


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"Field '{key}' wajib diisi berupa teks")

    return value.strip()


def _parse_occurred_at(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if not isinstance(value, str):
        raise ToolError("occurred_on harus berupa teks YYYY-MM-DD")

    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ToolError(f"Tanggal '{value}' tidak dikenali, gunakan YYYY-MM-DD") from exc

    return datetime.combine(parsed, time(12, 0), tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Read tools
# ----------------------------------------------------------------------


def tool_get_accounts(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    snapshots = account_snapshots(db, user_id)
    accounts = {
        a.id: a
        for a in db.scalars(
            select(Account).where(Account.user_id == user_id, Account.is_system.is_(False))
        ).all()
    }

    return {
        "accounts": [
            {
                "name": accounts[s.id].name,
                "type": accounts[s.id].type.value,
                "balance": s.balance,
                "debt": s.debt,
                "archived": s.is_archived,
            }
            for s in snapshots
            if s.id in accounts
        ]
    }


def tool_get_summary(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    snapshots = account_snapshots(db, user_id)
    liquid_ids = {s.id for s in snapshots if s.type in LIQUID_TYPES and not s.is_archived}

    allocations = db.scalars(select(Allocation).where(Allocation.user_id == user_id)).all()
    allocated = sum(a.amount for a in allocations if a.account_id in liquid_ids)

    fts = free_to_spend(snapshots, allocated_on_liquid=allocated)

    return {
        "liquid": liquid_balance(snapshots),
        "net_worth": net_worth(snapshots),
        "total_debt": total_debt(snapshots),
        "free_to_spend": fts.amount,
        "is_shortfall": fts.is_shortfall,
        "expense_total": category_total(snapshots, kind=AccountKind.EXPENSE),
        "income_total": category_total(snapshots, kind=AccountKind.INCOME),
    }


def tool_get_spending(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    """Spending for a period, optionally narrowed to one category (FR06)."""
    user = db.get(User, user_id)
    keyword = args.get("period") or "bulan_ini"

    if not isinstance(keyword, str):
        raise ToolError("Field 'period' harus berupa teks")

    try:
        period = resolve_period(
            keyword,
            now=datetime.now(timezone.utc),
            timezone_name=getattr(user, "timezone", None),
        )
    except PeriodError as exc:
        raise ToolError(str(exc)) from exc

    requested = args.get("category")

    if isinstance(requested, str) and requested.strip():
        total = category_total_for_period(db, user_id, period, requested)

        if total is None:
            # Unknown category: say which ones exist rather than answer
            # zero, which would read as "you spent nothing" (AC04's
            # principle - do not answer an ambiguous reference).
            known = known_expense_categories(db, user_id)
            raise ToolError(
                f"Kategori '{requested}' belum pernah dipakai. "
                + (f"Yang ada: {', '.join(known)}." if known else "Belum ada kategori sama sekali.")
            )

        return {
            "period": period.label,
            "category": requested.strip(),
            "total": total,
        }

    report = period_report(db, user_id, period)

    # The same window again, immediately before this one. A breakdown
    # with no comparison answers "what did I spend" but not the question
    # people actually ask, which is "is that a lot".
    span = period.end - period.start
    previous = period_report(
        db, user_id, Period(start=period.start - span, end=period.start, label="sebelumnya")
    )

    limits = {
        status.category.casefold(): status.limit
        for status in budget_report(db, user_id, period).statuses
    }

    categories = []

    for row in report.categories:
        limit = limits.get(row.name.casefold())

        categories.append(
            {
                "name": row.name,
                "amount": row.amount,
                # Only when a budget exists. A category with none is not
                # "within budget" - there is nothing to be within.
                "limit": limit,
                "over": (row.amount - limit) if limit is not None and row.amount > limit else None,
            }
        )

    return {
        "period": report.label,
        "expense_total": report.expense_total,
        "income_total": report.income_total,
        "previous_expense_total": previous.expense_total,
        "categories": categories,
        "transaction_count": report.transaction_count,
    }


def tool_get_goals(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    rows = db.scalars(
        select(Goal).where(Goal.user_id == user_id).order_by(Goal.priority, Goal.name)
    ).all()

    return {
        "goals": [
            {
                "name": g.name,
                "target": g.target_amount,
                "saved": saved_for(db, user_id, g.id),
                "shortfall": max(0, g.target_amount - saved_for(db, user_id, g.id)),
                "status": g.status,
            }
            for g in rows
        ]
    }


def tool_get_budgets(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    user = db.get(User, user_id)
    keyword = args.get("period") or "bulan_ini"

    try:
        period = resolve_period(
            keyword,
            now=datetime.now(timezone.utc),
            timezone_name=getattr(user, "timezone", None),
        )
    except PeriodError as exc:
        raise ToolError(str(exc)) from exc

    report = budget_report(db, user_id, period)

    return {
        "period": report.label,
        "budgets": [
            {
                "category": s.category,
                "limit": s.limit,
                "spent": s.spent,
                "remaining": s.remaining,
                "percent": s.percent,
                "state": s.state.value,
            }
            for s in report.statuses
        ],
        "note": "Budget adalah rencana belanja, bukan saldo.",
    }


def tool_propose_budget(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    category = _require_str(args, "category")

    try:
        amount = positive_rupiah(args.get("amount"))
    except MoneyError as exc:
        raise ToolError(str(exc)) from exc

    # Show the change when a limit already exists: replacing a budget is
    # a real edit, and FR05 requires the impact to be visible before the
    # user confirms.
    current = db.scalar(
        select(Budget)
        .join(Account, Account.id == Budget.category_account_id)
        .where(
            Budget.user_id == user_id,
            Account.kind == AccountKind.EXPENSE,
            func.lower(Account.name) == category.lower(),
        )
    )

    impact = [
        {
            "account": f"Budget {category}",
            "before": current.amount if current else 0,
            "after": amount,
            "delta": amount - (current.amount if current else 0),
        }
    ]

    draft = _store_draft(
        db,
        user_id=user_id,
        kind="budget",
        payload={"category": category, "amount": amount},
        impact=impact,
    )

    return {
        "draft_id": str(draft.id),
        "operation_id": draft.operation_id,
        "saved": False,
        "note": "Menunggu konfirmasi pengguna",
    }


def tool_run_simulation(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    """Run a calculator. Changes nothing, so it needs no confirmation (AC07)."""
    kind = args.get("kind")

    try:
        if kind == "deposit":
            result = simulate_deposit(
                principal=args.get("principal"),
                annual_rate_percent=args.get("annual_rate_percent", 0),
                months=args.get("months"),
                tax_percent=args.get("tax_percent"),
                fees=args.get("fees") or 0,
            )
            out = asdict(result)
            if not result.complete:
                out["warning"] = (
                    "Tarif pajak belum diketahui, jadi hasil bersih ini belum "
                    "lengkap. Jangan sebut angkanya sebagai pasti."
                )
            return out

        if kind == "saving":
            # The model reaches for "months" as often as "periods" -
            # both mean the same thing here, and refusing one just
            # pushes it into doing the arithmetic itself, which is the
            # one thing it must not do.
            periods = args.get("periods") or args.get("months") or 0

            return asdict(
                simulate_regular_saving(
                    target=args.get("target"),
                    initial=args.get("initial") or 0,
                    periods=periods,
                )
            )

        if kind == "capacity":
            user = db.get(User, user_id)
            capacity = estimate_capacity(db, user_id, timezone_name=getattr(user, "timezone", None))
            return {
                "reliable_income": capacity.inputs.reliable_income,
                "cash_expenses": capacity.inputs.cash_expenses,
                "obligations": capacity.inputs.obligations,
                "per_month": capacity.available,
                "months_observed": capacity.months_observed,
                "reliable": capacity.reliable,
                "notes": capacity.notes,
            }
    except (SimulationError, MoneyError) as exc:
        # Spelled out because the observed failure mode is the model
        # quietly doing the sum itself when a tool refuses - and a
        # plausible-looking figure it invented is worse than no answer.
        raise ToolError(f"{exc} Jangan hitung sendiri; minta pengguna melengkapi datanya.") from exc

    raise ToolError(f"Jenis simulasi '{kind}' tidak dikenal. Jangan hitung sendiri.")


def _category_accounts(
    db: DbSession, user_id: uuid.UUID, name: str, *, group: bool = False
) -> list[Account]:
    """Every category account spelling ``name``, for either direction.

    A list rather than one row because folding the case only stops *new*
    duplicates; a ledger written before it can still hold "transport"
    and "Transport" side by side, and a merge that moved one of them
    would leave the user staring at the other.

    ``group`` widens it to the whole synonym group, which is what a
    *reading* of "ongkos" means. A merge asks for the exact spelling
    first and only then the group — see :func:`_named_categories` — or
    naming one member of a group as the destination would resolve to
    another member of it.
    """
    needles = (
        resolve_expense(name).aliases | resolve_income(name).aliases
        if group
        else {" ".join(name.split()).lower()}
    )
    needles = {needle for needle in needles if needle}

    if not needles:
        return []

    return list(
        db.scalars(
            select(Account)
            .where(
                Account.user_id == user_id,
                Account.kind.in_([AccountKind.EXPENSE, AccountKind.INCOME]),
                func.lower(Account.name).in_(needles),
            )
            .order_by(Account.created_at, Account.id)
        ).all()
    )


def tool_find_transactions(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    limit = args.get("limit", 20)
    limit = min(max(int(limit) if isinstance(limit, int) else 20, 1), 50)

    # The day a transaction belongs to is the day it was in the user's
    # own timezone, which is the rule `domain/periods.py` already states
    # for months: entries are stored in UTC, and for Asia/Jakarta that
    # is a seven-hour shift. Taking `.date()` off the stored value named
    # the previous day for anything bought between midnight and 07:00 —
    # so the model was told "12 Oktober" about a purchase the summary
    # and the data screen both called today, and no amount of prompting
    # could have made it answer right from that.
    zone = get_zone(getattr(db.get(User, user_id), "timezone", None))

    accounts = {
        a.id: a for a in db.scalars(select(Account).where(Account.user_id == user_id)).all()
    }

    query = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.occurred_at.desc())
    )

    requested = args.get("category")

    if isinstance(requested, str) and requested.strip():
        # Narrowed by joining through the entries, not by filtering the
        # page afterwards: "the last 20 transactions, of which three are
        # Transport" is not the question. The question is "the Transport
        # ones", and answering it from a window would hide the rest.
        matches = _category_accounts(db, user_id, requested, group=True)

        if not matches:
            known = known_expense_categories(db, user_id)
            raise ToolError(
                f"Kategori '{requested}' belum pernah dipakai. "
                + (f"Yang ada: {', '.join(known)}." if known else "Belum ada kategori sama sekali.")
            )

        query = query.where(
            Transaction.entries.any(Entry.account_id.in_([a.id for a in matches]))
        )

    rows = db.scalars(query.limit(limit)).all()

    return {
        "transactions": [
            {
                "id": str(t.id),
                "type": t.type.value,
                "date": t.occurred_at.astimezone(zone).date().isoformat(),
                "status": t.status.value,
                # The three keepsakes, named separately so the model can
                # tell "which one was the bus fare" without re-asking the
                # user something the ledger already knows.
                "category": _category_name_of(t, accounts),
                "merchant": t.merchant,
                "note": t.note,
                "description": t.description,
                "entries": [
                    {
                        "account": accounts[e.account_id].name if e.account_id in accounts else "?",
                        "amount": e.amount,
                    }
                    for e in t.entries
                ],
            }
            for t in rows
        ]
    }


def _category_name_of(transaction: Transaction, accounts: dict[uuid.UUID, Account]) -> str | None:
    """The category a transaction is filed under, if it has exactly one.

    A transfer has none, and a transfer with an admin fee has one that
    belongs to the fee rather than to the move itself — so "exactly one"
    is the honest test, and anything else answers None.
    """
    names = [
        accounts[entry.account_id].name
        for entry in transaction.entries
        if entry.account_id in accounts
        and accounts[entry.account_id].kind in (AccountKind.EXPENSE, AccountKind.INCOME)
    ]

    return names[0] if len(names) == 1 else None


# ----------------------------------------------------------------------
# Propose tools
# ----------------------------------------------------------------------


def _store_draft(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    payload: dict,
    impact: list[dict] | None,
) -> Draft:
    draft = Draft(
        id=uuid.uuid4(),
        user_id=user_id,
        kind=kind,
        payload=payload,
        impact={"rows": impact} if impact is not None else None,
        # Doubles as the idempotency key on confirmation, which is what
        # makes tapping a stale card twice harmless (AC13).
        operation_id=f"draft-{uuid.uuid4()}",
    )
    db.add(draft)
    db.flush()
    return draft


def _resolve(db: DbSession, user_id: uuid.UUID, text: str) -> Account:
    """Resolve an account name, turning ambiguity into a tool error.

    The model gets told to ask; it must not pick one itself (AC04).
    """
    try:
        return resolve_account(db, user_id, text)
    except AmbiguousAccount as exc:
        raise ToolError(str(exc)) from exc
    except DomainError as exc:
        raise ToolError(str(exc)) from exc


def _resolve_optional(
    db: DbSession, user_id: uuid.UUID, text: str | None
) -> tuple[str | None, bool]:
    """An account id, or a blank the user will fill in.

    The single-entry path turns an ambiguous or missing wallet into a
    tool error so the model asks. A batch cannot do that: one unclear
    wallet out of three would throw away two entries the model got
    right, and the person would be answering a question about a list
    they cannot see.

    So the slot is left empty and carried to the card, where the wallets
    are on screen and one tap resolves it. The guess is still never
    made - it is just made by the person instead of the model (AC04),
    and `_confirm_batch` refuses to post while any slot is empty.
    """
    if not isinstance(text, str) or not text.strip():
        return None, True

    try:
        return str(resolve_account(db, user_id, text).id), False
    except (AmbiguousAccount, DomainError):
        return None, True


#: Said when a transfer names a destination that is not a wallet.
#:
#: "gua abis tf ke ibu gua 300rb dari bank jago" is an expense: the
#: money left, and "Ibu" is who it went to, not somewhere it still is.
#: The model reads "tf" and reaches for `transfer`, which in this ledger
#: means moving money between the user's *own* wallets — so the lookup
#: fails on a name that was never going to be an account.
#:
#: Plain "Tidak ada kantong yang cocok dengan 'Ibu'" is a dead end: the
#: model has no way to know what to do differently, and in practice it
#: repeated the same call after the person said "ini pengeluaran". The
#: fix is to make the error say what the right call is. The *backend*
#: does not reclassify it - that would be guessing with someone's money,
#: and the draft still goes to the person to confirm (AC04).
_NOT_A_WALLET_HINT = (
    "'{name}' bukan kantong punya pengguna. Kalau uangnya dikirim ke ORANG LAIN "
    "(teman, keluarga, penjual), itu 'expense' dari kantong sumber dengan "
    "merchant='{name}', BUKAN 'transfer'. 'transfer' hanya untuk memindahkan "
    "uang antar kantong pengguna sendiri."
)


def _fill_slot(
    db: DbSession,
    user_id: uuid.UUID,
    *,
    item: dict,
    payload: dict,
    unresolved: list[str],
    batched: bool,
    field: str,
    source_key: str,
) -> None:
    """Fill one account slot, strictly or leniently depending on mode."""
    if not batched:
        name = _require_str(item, source_key)

        try:
            payload[field] = str(_resolve(db, user_id, name).id)
        except ToolError as exc:
            # Only the destination of a transfer: a *source* that does
            # not resolve is a different mistake, and the money has to
            # have come from somewhere the user owns either way.
            if field == "to_account_id" and item.get("type") == "transfer":
                raise ToolError(_NOT_A_WALLET_HINT.format(name=name)) from exc

            raise

        return

    account_id, missing = _resolve_optional(db, user_id, item.get(source_key))
    payload[field] = account_id

    if missing:
        unresolved.append(field)


def tool_propose_transactions(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    items = args.get("transactions")

    if not isinstance(items, list) or not items:
        raise ToolError("Field 'transactions' harus berupa daftar yang tidak kosong")

    if len(items) > 10:
        raise ToolError("Maksimal 10 transaksi dalam satu pesan")

    #: What the person said the whole lot came to, when they said it.
    #: Never posted - `reconcile` only checks the parts against it.
    stated_total = args.get("stated_total")

    if stated_total is not None:
        try:
            stated_total = positive_rupiah(stated_total)
        except MoneyError as exc:
            raise ToolError(str(exc)) from exc

    batched = len(items) > 1 or stated_total is not None

    drafts = []
    payloads = []

    for item in items:
        if not isinstance(item, dict):
            raise ToolError("Setiap transaksi harus berupa objek")

        kind = item.get("type")

        if kind not in {"expense", "income", "transfer", "card_payment", "refund"}:
            raise ToolError(f"Jenis transaksi '{kind}' tidak dikenal")

        try:
            amount = positive_rupiah(item.get("amount"))
            fee = rupiah(item.get("fee") or 0)
        except MoneyError as exc:
            raise ToolError(str(exc)) from exc

        payload: dict[str, Any] = {"type": kind, "amount": amount}
        occurred_at = _parse_occurred_at(item.get("occurred_on"))

        if occurred_at:
            payload["occurred_at"] = occurred_at.isoformat()

        for optional in ("merchant", "note", "category"):
            if isinstance(item.get(optional), str) and item[optional].strip():
                payload[optional] = item[optional].strip()

        unresolved: list[str] = []
        fill = partial(
            _fill_slot,
            db,
            user_id,
            item=item,
            payload=payload,
            unresolved=unresolved,
            batched=batched,
        )

        if kind in {"expense", "transfer", "card_payment"}:
            fill(field="from_account_id", source_key="from_account")

        if kind in {"income", "refund", "transfer"}:
            fill(field="to_account_id", source_key="to_account")

        if kind == "transfer":
            payload["fee"] = fee

        if kind == "card_payment":
            fill(field="card_account_id", source_key="to_account")

        if kind == "refund" and "category" not in payload:
            raise ToolError("Refund memerlukan kategori transaksi aslinya")

        if batched:
            payloads.append({"payload": payload, "unresolved": unresolved})
            continue

        impact = _impact_for(db, user_id, payload)
        draft = _store_draft(db, user_id=user_id, kind=kind, payload=payload, impact=impact)

        drafts.append(
            {"draft_id": str(draft.id), "operation_id": draft.operation_id, "impact": impact}
        )

    if batched:
        draft = _store_batch(db, user_id, payloads, stated_total)

        drafts.append(
            {
                "draft_id": str(draft.id),
                "operation_id": draft.operation_id,
                "impact": (draft.impact or {}).get("rows"),
            }
        )

    return {"drafts": drafts, "saved": False, "note": "Menunggu konfirmasi pengguna"}


def _store_batch(
    db: DbSession, user_id: uuid.UUID, items: list[dict], stated_total: int | None
) -> Draft:
    """One draft holding several entries.

    One draft and not several, because this is one thing the person
    said and must be one thing they confirm. Several drafts would mean
    several swipes for one sentence, and - worse - a half-posted batch
    the moment one of them failed.

    The impact is folded over every resolved entry at once rather than
    computed per item and added up: two expenses from the same wallet
    have to show one before and one after, not two overlapping previews
    of the same balance.
    """
    reconciliation = reconcile([item["payload"]["amount"] for item in items], stated_total)

    legs: list[Any] = []

    for item in items:
        if item["unresolved"]:
            continue

        legs.extend(_legs_for(db, user_id, item["payload"]))

    snapshots = account_snapshots(db, user_id)

    impact = [
        {"account": row.name, "before": row.before, "after": row.after, "delta": row.delta}
        for row in impact_of(legs, snapshots)
    ]

    payload = {
        "items": [{**item["payload"], "unresolved": item["unresolved"]} for item in items],
        "items_total": reconciliation.items_total,
        "stated_total": reconciliation.stated_total,
        "difference": reconciliation.difference,
        "matches": reconciliation.matches,
    }

    return _store_draft(db, user_id=user_id, kind="batch", payload=payload, impact=impact)


def _legs_for(db: DbSession, user_id: uuid.UUID, payload: dict):
    """Validate a stored payload and turn it into ledger legs."""
    from pydantic import TypeAdapter

    from ...api.schemas import Draft as DraftSchema

    parsed = TypeAdapter(DraftSchema).validate_python(payload)

    return build_legs(db, user_id, parsed)


def _impact_for(db: DbSession, user_id: uuid.UUID, payload: dict) -> list[dict]:
    """Compute a payload's impact the same way the REST preview does."""
    legs = _legs_for(db, user_id, payload)
    snapshots = account_snapshots(db, user_id)

    return [
        {"account": row.name, "before": row.before, "after": row.after, "delta": row.delta}
        for row in impact_of(legs, snapshots)
    ]


def tool_propose_account_change(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    name = _require_str(args, "name")
    account_type = _require_str(args, "account_type")

    if account_type not in CREATABLE_TYPES:
        raise ToolError(f"Jenis kantong '{account_type}' tidak bisa dibuat lewat chat")

    try:
        opening = rupiah(args.get("opening_balance") or 0)
        limit = rupiah(args["credit_limit"]) if args.get("credit_limit") else None
    except MoneyError as exc:
        raise ToolError(str(exc)) from exc

    if opening < 0:
        raise ToolError("Saldo awal tidak boleh negatif")

    # Checked before a card is drawn, not only at confirmation time. The
    # model re-reads the whole thread, so after a few turns it will
    # cheerfully re-propose wallets the user already created and
    # confirmed — which reads to them as their confirmation having been
    # lost, and would double their opening balances if they confirmed
    # again. Telling the model here turns that into a question.
    existing = db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            func.lower(Account.name) == name.strip().lower(),
            Account.is_archived.is_(False),
        )
    )

    if existing is not None:
        raise ToolError(
            f"Kantong '{existing.name}' sudah ada, jadi tidak dibuat ulang. "
            "Kalau maksudnya kantong lain, pakai nama yang berbeda."
        )

    payload = {
        "name": name,
        "type": account_type,
        "opening_balance": opening,
        "credit_limit": limit,
    }

    draft = _store_draft(db, user_id=user_id, kind="account", payload=payload, impact=None)

    return {
        "draft_id": str(draft.id),
        "operation_id": draft.operation_id,
        "saved": False,
        "note": "Menunggu konfirmasi pengguna",
    }


def _resolve_goal(db: DbSession, user_id: uuid.UUID, name: str) -> Goal:
    """Find one goal by name, refusing to guess between several.

    Same rule as accounts: an ambiguous reference must produce a
    question, not a choice made on the user's behalf (AC04).
    """
    needle = name.strip().lower()

    matches = list(
        db.scalars(
            select(Goal).where(Goal.user_id == user_id, func.lower(Goal.name).contains(needle))
        ).all()
    )

    if not matches:
        raise ToolError(f"Tidak ada target bernama '{name}'")

    if len(matches) > 1:
        raise ToolError(
            f"'{name}' cocok dengan {len(matches)} target: "
            + ", ".join(g.name for g in matches)
            + ". Pilih salah satu."
        )

    return matches[0]


def tool_propose_goal(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    name = _require_str(args, "name")

    try:
        target = positive_rupiah(args.get("target_amount"))
    except MoneyError as exc:
        raise ToolError(str(exc)) from exc

    target_date = _parse_occurred_at(args.get("target_date"))
    priority = args.get("priority", 0)

    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 100:
        priority = 0

    payload = {
        "name": name,
        "target_amount": target,
        "priority": priority,
    }

    if target_date:
        payload["target_date"] = target_date.isoformat()

    draft = _store_draft(db, user_id=user_id, kind="goal", payload=payload, impact=None)

    return {
        "draft_id": str(draft.id),
        "operation_id": draft.operation_id,
        "saved": False,
        "note": "Menunggu konfirmasi pengguna",
    }


def tool_propose_allocation(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    goal = _resolve_goal(db, user_id, _require_str(args, "goal_name"))
    account = _resolve(db, user_id, _require_str(args, "account"))

    try:
        amount = positive_rupiah(args.get("amount"))
    except MoneyError as exc:
        raise ToolError(str(exc)) from exc

    # Validate now, while a draft is being built, so the card never
    # offers something that will fail on confirmation (AC05).
    free = headroom(db, user_id, account.id)

    if amount > free:
        raise ToolError(f"Sisa yang bisa dialokasikan dari '{account.name}' hanya {free}.")

    payload = {
        "goal_id": str(goal.id),
        "account_id": str(account.id),
        "amount": amount,
        # Display-only. Confirmation reads the ids; without the names the
        # card could only show a UUID.
        "goal_name": goal.name,
        "account_name": account.name,
    }

    already = saved_for(db, user_id, goal.id)

    return {
        "draft_id": str(
            _store_draft(
                db,
                user_id=user_id,
                kind="allocation",
                payload=payload,
                impact=[
                    {
                        "account": f"Target {goal.name}",
                        "before": already,
                        "after": already + amount,
                        "delta": amount,
                    }
                ],
            ).id
        ),
        "saved": False,
        "note": ("Menunggu konfirmasi. Alokasi tidak memindahkan uang dan tidak menambah aset."),
    }


def tool_propose_correction(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    raw_id = _require_str(args, "transaction_id")

    try:
        transaction_id = uuid.UUID(raw_id)
    except ValueError as exc:
        raise ToolError(f"'{raw_id}' bukan UUID transaksi yang valid") from exc

    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )

    if transaction is None:
        raise ToolError("Transaksi tidak ditemukan")

    snapshots = {s.id: s for s in account_snapshots(db, user_id)}
    rows = []

    for entry in transaction.entries:
        snapshot = snapshots.get(entry.account_id)
        before = snapshot.balance if snapshot else 0
        rows.append(
            {
                "account": snapshot.name if snapshot else "?",
                "before": before,
                "after": before - entry.amount,
                "delta": -entry.amount,
            }
        )

    draft = _store_draft(
        db,
        user_id=user_id,
        kind="reversal",
        payload={"transaction_id": str(transaction_id)},
        impact=rows,
    )

    return {
        "draft_id": str(draft.id),
        "operation_id": draft.operation_id,
        "impact": rows,
        "saved": False,
        "note": "Menunggu konfirmasi pengguna",
    }


#: How many originals one merge may move. A category with more than this
#: behind it is a bigger act than a chat card can honestly preview, so it
#: is refused with the count rather than half-done.
MAX_RECATEGORISE = 100


def _category_entry(
    transaction: Transaction, accounts: dict[uuid.UUID, Account]
) -> Entry:
    """The one entry that carries this transaction's category."""
    candidates = [
        entry
        for entry in transaction.entries
        if entry.account_id in accounts
        and accounts[entry.account_id].kind in (AccountKind.EXPENSE, AccountKind.INCOME)
    ]

    if not candidates:
        raise ToolError(
            "Transaksi ini tidak punya kategori - pindah kantong dan bayar "
            "tagihan kartu memang tidak dikategorikan."
        )

    if len(candidates) > 1:
        raise ToolError("Transaksi ini punya lebih dari satu kategori; sebutkan yang mana.")

    return candidates[0]


def moved_away(
    db: DbSession, user_id: uuid.UUID, account_ids: set[uuid.UUID]
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """Legs a posted move has already taken out of these categories.

    A reclassification does not edit the leg it refiles. It posts a
    counter-pair beside it — crediting the category the money left,
    debiting the one it arrived in — because the original is not wrong
    and deleting nothing is the rule (FR02/AC08). So a category that has
    already been merged still holds both halves of that move, netting to
    zero, and both halves are still there to be found.

    Returned as ``(transaction, account)`` pairs naming both halves, so
    the caller can skip a leg by the pair it sits on.

    The join is what tells the two sides of a move apart. A move's credit
    lands on an account its original also has a leg on; its debit lands
    on one the original never touched. Matching only the shared account
    keeps the arriving money movable — otherwise merging the
    *destination* of an earlier move would have left the money that came
    in through it behind.
    """
    if not account_ids:
        return set()

    original = aliased(Entry)

    rows = db.execute(
        select(Transaction.id, Transaction.reverses_id, Entry.account_id)
        .join(Entry, Entry.transaction_id == Transaction.id)
        .join(
            original,
            (original.transaction_id == Transaction.reverses_id)
            & (original.account_id == Entry.account_id),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.RECLASSIFY,
            Transaction.status == TransactionStatus.POSTED,
            Entry.account_id.in_(account_ids),
        )
    ).all()

    gone: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for move_id, original_id, account_id in rows:
        gone.add((original_id, account_id))
        gone.add((move_id, account_id))

    return gone


def _current_category_leg(
    db: DbSession, user_id: uuid.UUID, transaction: Transaction, accounts: dict[uuid.UUID, Account]
) -> tuple[Transaction, Entry]:
    """Where this transaction's category sits *now*, and the leg holding it.

    Because a move leaves the original alone, the original's own leg
    still names the category it was first filed under. Reading it to move
    the same transaction a second time produced a card headed
    "ongkos -> makan" for money the breakdown already showed under
    Transportasi, and confirming it would have left the amount sitting in
    two categories at once.

    So the chain is followed to its end: the last move is where the money
    is, and the next one has to reverse *that* rather than the original.
    """
    current = transaction
    entry = _category_entry(transaction, accounts)
    seen = {transaction.id}

    while True:
        move = db.scalar(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.reverses_id == current.id,
                Transaction.type == TransactionType.RECLASSIFY,
                Transaction.status == TransactionStatus.POSTED,
            )
            .order_by(Transaction.created_at)
            .limit(1)
        )

        if move is None or move.id in seen:
            return current, entry

        # The other side of the counter-pair is where it landed. Anything
        # but one leg is not a shape this understands, so the chain stops
        # rather than guessing.
        landed = [e for e in move.entries if e.account_id != entry.account_id]

        if len(landed) != 1:
            return current, entry

        seen.add(move.id)
        current, entry = move, landed[0]


def _named_categories(db: DbSession, user_id: uuid.UUID, name: str) -> list[Account]:
    """The categories this name refers to: the exact spelling, else the group.

    **Exact first is what makes a merge inside one synonym group
    possible at all.** "ongkos", "bensin" and "transport" are three
    aliases of Transportasi, and a ledger written before the groups
    existed can hold all three as separate accounts. Resolving either
    side through the group hands back the oldest of them, so
    "pindahkan ongkos ke transport" came back as "ongkos -> bensin",
    for Rp0 — the person was naming a destination and could not reach
    it.

    The group is still the fallback, and has to be: once the merge is
    done only "Transportasi" is left, and "pindahin ongkos" has to find
    it. The person's word is the one they will keep using, whatever the
    account ended up called.
    """
    exact = _category_accounts(db, user_id, name)

    return exact or _category_accounts(db, user_id, name, group=True)


def _target_category(db: DbSession, user_id: uuid.UUID, name: str, *, income: bool) -> Account:
    """The destination, created under its canonical name if it is new.

    Filing a *new* expense goes through `expense_category`, which always
    resolves the group: "ongkos 25rb" should land in whatever account
    this ledger already keeps transport in. Here the name is a
    destination somebody chose, so :func:`_named_categories` decides,
    and the group only has the last word when nothing is called that
    yet.
    """
    wanted = AccountKind.INCOME if income else AccountKind.EXPENSE

    for account in _named_categories(db, user_id, name):
        if account.kind is wanted:
            return account

    return income_category(db, user_id, name) if income else expense_category(db, user_id, name)


def _pending_twin(db: DbSession, user_id: uuid.UUID, payload: dict) -> Draft | None:
    """A move already waiting that would do exactly this.

    "Pindahkan ongkos dan bensin ke transport" is one sentence and the
    model answers it with one call per category — sometimes with the same
    call twice, which is how three cards came back for two merges. Two
    identical cards are not two acts: they are one act the person has to
    decide twice, and both would post.
    """
    waiting = db.scalars(
        select(Draft).where(
            Draft.user_id == user_id,
            Draft.kind == "recategorise",
            Draft.status == DraftStatus.PENDING,
        )
    ).all()

    for draft in waiting:
        stored = draft.payload or {}
        same_target = stored.get("to_account_id") == payload["to_account_id"]

        if same_target and stored.get("moves") == payload["moves"]:
            return draft

    return None


def tool_propose_recategorise(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    """Draft a move of one or many transactions into another category.

    The money does not move, so neither does any wallet: both legs of
    every posting land on category accounts. That is the whole point of
    the tool existing. Before it did, the model answered "pindahkan ke
    transport" with `propose_correction`, whose card says BATALKAN and
    whose impact hands the cash back — the right words over the wrong
    act.
    """
    to_name = _require_str(args, "to_category")
    raw_id = args.get("transaction_id")
    from_name = args.get("from_category")

    has_id = isinstance(raw_id, str) and raw_id.strip()
    has_category = isinstance(from_name, str) and from_name.strip()

    if has_id and has_category:
        raise ToolError(
            "Pilih salah satu: satu transaksi lewat 'transaction_id', atau "
            "seluruh kategori lewat 'from_category'."
        )

    if not has_id and not has_category:
        raise ToolError("Sebutkan 'transaction_id' atau 'from_category'.")

    accounts = {
        a.id: a for a in db.scalars(select(Account).where(Account.user_id == user_id)).all()
    }

    if has_id:
        try:
            transaction_id = uuid.UUID(raw_id)
        except ValueError as exc:
            raise ToolError(f"'{raw_id}' bukan UUID transaksi yang valid") from exc

        transaction = db.scalar(
            select(Transaction).where(
                Transaction.id == transaction_id, Transaction.user_id == user_id
            )
        )

        if transaction is None:
            raise ToolError("Transaksi tidak ditemukan")

        if transaction.status is TransactionStatus.REVERSED:
            raise ToolError("Transaksi ini sudah dibatalkan, kategorinya tidak perlu dipindah.")

        moves = [_current_category_leg(db, user_id, transaction, accounts)]
        source = accounts[moves[0][1].account_id]
    else:
        sources = _named_categories(db, user_id, from_name)

        if not sources:
            known = known_expense_categories(db, user_id)
            raise ToolError(
                f"Kategori '{from_name}' belum pernah dipakai. "
                + (f"Yang ada: {', '.join(known)}." if known else "Belum ada kategori sama sekali.")
            )

        source = sources[0]
        source_ids = {a.id for a in sources}

        rows = db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.status == TransactionStatus.POSTED,
                Transaction.entries.any(Entry.account_id.in_(source_ids)),
            )
            .order_by(Transaction.occurred_at)
        ).all()

        # Both halves of an earlier move are skipped. They cancel each
        # other out, so the net about to be moved is the same either
        # way — but counting them made "pindahkan ongkos ke transport"
        # answer a category merged last week with "3 transaksi, Rp0",
        # and confirming it a second time would have moved the same
        # money twice.
        gone = moved_away(db, user_id, source_ids)

        moves = [
            (row, entry)
            for row in rows
            for entry in row.entries
            if entry.account_id in source_ids and (row.id, entry.account_id) not in gone
        ]

        if len(moves) > MAX_RECATEGORISE:
            raise ToolError(
                f"Kategori '{source.name}' punya {len(moves)} transaksi, terlalu "
                f"banyak untuk satu kali pindah (maksimal {MAX_RECATEGORISE})."
            )

    if not moves:
        raise ToolError(f"Tidak ada transaksi di kategori '{source.name}'.")

    # The target follows the source's nature. Filing an expense under an
    # income category would make a month's spending read as earnings, and
    # the ledger would still balance while saying something false.
    target = _target_category(db, user_id, to_name, income=source.kind is AccountKind.INCOME)

    source_ids = {entry.account_id for _, entry in moves}

    if target.id in source_ids:
        raise ToolError(f"'{to_name}' adalah kategori yang sama dengan '{source.name}'.")

    # Net, not gross. A refund inside the category sits there as a
    # credit, and adding its size to the purchases would announce a move
    # bigger than the one about to happen.
    moved = sum(entry.amount for _, entry in moves)
    amount = abs(moved)

    # A category that has already been emptied still holds its entries:
    # the original debits and the credits of the move that took them
    # away, netting to nothing. Offering "pindahkan Rp0" is a
    # confirmation for an act with no effect, and repeating the request
    # only stacks more of them.
    if amount == 0:
        raise ToolError(
            f"Kategori '{source.name}' sudah kosong - isinya nol setelah dihitung "
            "bersih, jadi tidak ada yang bisa dipindahkan."
        )

    snapshots = {s.id: s for s in account_snapshots(db, user_id)}

    # Summed over every spelling being merged, not just the one whose
    # name is shown. A source that exists twice would otherwise preview a
    # "before" that is only part of what the card is about to move.
    source_before = sum(
        snapshots[account_id].balance for account_id in source_ids if account_id in snapshots
    )
    target_before = snapshots[target.id].balance if target.id in snapshots else 0

    rows_impact = [
        {
            "account": source.name,
            "before": source_before,
            "after": source_before - moved,
            "delta": -moved,
        },
        {
            "account": target.name,
            "before": target_before,
            "after": target_before + moved,
            "delta": moved,
        },
    ]

    payload = {
        "from_category": source.name,
        "to_category": target.name,
        "to_account_id": str(target.id),
        "amount": amount,
        "count": len(moves),
        # One row per leg, each naming the account it actually sits on. A
        # single `from_account_id` was wrong the moment a category
        # existed under two spellings: half the legs hang off the other
        # row, and confirming would have looked for them on an account
        # they were never on.
        "moves": [
            {
                "transaction_id": str(transaction.id),
                "from_account_id": str(entry.account_id),
                # Signed, because the direction is part of the fact.
                "amount": entry.amount,
            }
            for transaction, entry in moves
        ],
    }

    draft = _pending_twin(db, user_id, payload) or _store_draft(
        db,
        user_id=user_id,
        kind="recategorise",
        payload=payload,
        impact=rows_impact,
    )

    return {
        "draft_id": str(draft.id),
        "operation_id": draft.operation_id,
        "from_category": source.name,
        "to_category": target.name,
        "count": len(moves),
        "amount": amount,
        "impact": rows_impact,
        "saved": False,
        "note": "Menunggu konfirmasi pengguna. Saldo kantong tidak berubah.",
    }


HANDLERS = {
    "get_accounts": tool_get_accounts,
    "get_summary": tool_get_summary,
    "get_spending": tool_get_spending,
    "find_transactions": tool_find_transactions,
    "propose_transactions": tool_propose_transactions,
    "get_goals": tool_get_goals,
    "get_budgets": tool_get_budgets,
    "run_simulation": tool_run_simulation,
    "propose_budget": tool_propose_budget,
    "propose_account_change": tool_propose_account_change,
    "propose_goal": tool_propose_goal,
    "propose_allocation": tool_propose_allocation,
    "propose_correction": tool_propose_correction,
    "propose_recategorise": tool_propose_recategorise,
}


def dispatch(db: DbSession, user_id: uuid.UUID, name: str, arguments: dict) -> dict:
    """Run one tool call, returning the result to feed back to the model."""
    handler = HANDLERS.get(name)

    if handler is None:
        return {"error": f"Tool '{name}' tidak tersedia"}

    try:
        return handler(db, user_id, arguments or {})
    except ToolError as exc:
        # Handed back as a result, not raised: the model should turn it
        # into a question for the user.
        return {"error": str(exc)}
    except DomainError as exc:
        return {"error": str(exc)}


def pending_draft(db: DbSession, user_id: uuid.UUID, draft_id: uuid.UUID) -> Draft | None:
    return db.scalar(
        select(Draft).where(
            Draft.id == draft_id,
            Draft.user_id == user_id,
            Draft.status == DraftStatus.PENDING,
        )
    )
