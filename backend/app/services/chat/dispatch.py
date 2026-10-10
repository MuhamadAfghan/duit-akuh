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
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ...domain.balances import (
    category_total,
    free_to_spend,
    impact_of,
    liquid_balance,
    net_worth,
    total_debt,
)
from ...domain.errors import AmbiguousAccount, DomainError
from ...domain.periods import PeriodError, resolve_period
from ...models import (
    LIQUID_TYPES,
    Account,
    AccountKind,
    Allocation,
    Draft,
    DraftStatus,
    Goal,
    Transaction,
    User,
)
from ...money import MoneyError, positive_rupiah, rupiah
from ..accounts import resolve_account
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

    return {
        "period": report.label,
        "expense_total": report.expense_total,
        "income_total": report.income_total,
        "categories": [{"name": c.name, "amount": c.amount} for c in report.categories],
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


def tool_find_transactions(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    limit = args.get("limit", 20)
    limit = min(max(int(limit) if isinstance(limit, int) else 20, 1), 50)

    rows = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.occurred_at.desc())
        .limit(limit)
    ).all()

    accounts = {
        a.id: a.name for a in db.scalars(select(Account).where(Account.user_id == user_id)).all()
    }

    return {
        "transactions": [
            {
                "id": str(t.id),
                "type": t.type.value,
                "date": t.occurred_at.date().isoformat(),
                "status": t.status.value,
                "description": t.description,
                "entries": [
                    {"account": accounts.get(e.account_id, "?"), "amount": e.amount}
                    for e in t.entries
                ],
            }
            for t in rows
        ]
    }


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


def tool_propose_transactions(db: DbSession, user_id: uuid.UUID, args: dict) -> dict:
    items = args.get("transactions")

    if not isinstance(items, list) or not items:
        raise ToolError("Field 'transactions' harus berupa daftar yang tidak kosong")

    if len(items) > 10:
        raise ToolError("Maksimal 10 transaksi dalam satu pesan")

    drafts = []

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

        if kind in {"expense", "transfer", "card_payment"}:
            source = _resolve(db, user_id, _require_str(item, "from_account"))
            payload["from_account_id"] = str(source.id)

        if kind in {"income", "refund"}:
            target = _resolve(db, user_id, _require_str(item, "to_account"))
            payload["to_account_id"] = str(target.id)

        if kind == "transfer":
            target = _resolve(db, user_id, _require_str(item, "to_account"))
            payload["to_account_id"] = str(target.id)
            payload["fee"] = fee

        if kind == "card_payment":
            card = _resolve(db, user_id, _require_str(item, "to_account"))
            payload["card_account_id"] = str(card.id)

        if kind == "refund" and "category" not in payload:
            raise ToolError("Refund memerlukan kategori transaksi aslinya")

        impact = _impact_for(db, user_id, payload)
        draft = _store_draft(db, user_id=user_id, kind=kind, payload=payload, impact=impact)

        drafts.append(
            {"draft_id": str(draft.id), "operation_id": draft.operation_id, "impact": impact}
        )

    return {"drafts": drafts, "saved": False, "note": "Menunggu konfirmasi pengguna"}


def _impact_for(db: DbSession, user_id: uuid.UUID, payload: dict) -> list[dict]:
    """Compute a payload's impact the same way the REST preview does."""
    from pydantic import TypeAdapter

    from ...api.schemas import Draft as DraftSchema

    parsed = TypeAdapter(DraftSchema).validate_python(payload)
    legs = build_legs(db, user_id, parsed)
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


HANDLERS = {
    "get_accounts": tool_get_accounts,
    "get_summary": tool_get_summary,
    "get_spending": tool_get_spending,
    "find_transactions": tool_find_transactions,
    "propose_transactions": tool_propose_transactions,
    "get_goals": tool_get_goals,
    "propose_account_change": tool_propose_account_change,
    "propose_goal": tool_propose_goal,
    "propose_allocation": tool_propose_allocation,
    "propose_correction": tool_propose_correction,
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
