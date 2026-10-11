"""Changing a draft before it is confirmed (PRD FR05, AC04).

The model proposes from a sentence, and a sentence can be wrong in small
ways — the right amount from the wrong wallet, the right wallet with the
wrong category. The cheap fix is to send another message and let the
model try again, but that is a round trip through a language model to
change one field, and it can misread the correction as readily as it
misread the original.

So a revision is a backend operation, not a conversation. The patch
arrives as structured fields, is validated here, and the impact is
recomputed by the same functions that produced the original preview —
never by the model, and never by the client.

**A revision makes a new draft.** The old one is cancelled, keeping its
row and its operation id, and the new one gets its own. That is what
stops a confirmation already in flight from landing on edited numbers:
the id the client is holding is no longer pending, so it cannot post.
Nothing is written to the ledger either way — a draft is a proposal, so
revising one is not a correction in the FR02 sense and raises no audit
event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session as DbSession

from ...domain.errors import DomainError
from ...models import Account, Draft, DraftStatus, Message
from ...money import MoneyError, positive_rupiah
from .dispatch import _impact_for, _store_batch, _store_draft

#: Only money movements can be revised this way. A goal, a budget or a
#: reversal each has its own payload shape and its own rules about what
#: may change; pretending one patch format fits all of them is how a
#: field ends up silently ignored.
REVISABLE_KINDS = {"expense", "income", "transfer", "card_payment", "refund"}

#: An allowlist, not a denylist. An unknown key is refused rather than
#: dropped, because a client that sends `ammount` should be told, not
#: quietly handed back the old figure as though the edit had worked.
PATCHABLE = frozenset(
    {
        "amount",
        "from_account_id",
        "to_account_id",
        "card_account_id",
        "category",
        "note",
        "occurred_at",
    }
)

#: Which accounts each kind actually uses. A patch naming a field its
#: kind has no use for - a `to_account_id` on an expense - is a bug in
#: the caller, and accepting it would store a payload the confirm path
#: then ignores.
ACCOUNT_FIELDS = {
    "expense": {"from_account_id"},
    "income": {"to_account_id"},
    "transfer": {"from_account_id", "to_account_id"},
    "card_payment": {"from_account_id", "card_account_id"},
    "refund": {"to_account_id"},
}


class ReviseError(Exception):
    """A patch that cannot be applied, with a code the API can map."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ----------------------------------------------------------------------


def _account(db: DbSession, user_id: uuid.UUID, raw: Any) -> Account:
    """Resolve an account **by id**, not by name.

    The chat resolves names because a person types them. A revision
    comes from a picker that already knows the ids, so there is nothing
    to disambiguate here and no reason to re-open that door.
    """
    try:
        account_id = uuid.UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise ReviseError("account_not_found", "Kantong tidak dikenal") from exc

    account = db.get(Account, account_id)

    # One message for missing, archived and someone else's: telling them
    # apart would confirm which ids exist.
    if account is None or account.user_id != user_id or account.is_archived:
        raise ReviseError("account_not_found", "Kantong tidak dikenal")

    return account


def _text(value: Any, field: str) -> str | None:
    """A trimmed string, or None to clear the field."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ReviseError("invalid_patch", f"Field '{field}' harus berupa teks")

    return value.strip() or None


def _moment(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ReviseError("invalid_patch", "Tanggal tidak valid") from exc

    return parsed.isoformat()


def _apply(db: DbSession, user_id: uuid.UUID, kind: str, payload: dict, patch: dict) -> dict:
    """The patched payload, every field re-validated from scratch."""
    revised = dict(payload)
    allowed_accounts = ACCOUNT_FIELDS[kind]

    for field, value in patch.items():
        if field not in PATCHABLE:
            raise ReviseError("invalid_patch", f"Field '{field}' tidak bisa diubah")

        if field == "amount":
            try:
                revised["amount"] = positive_rupiah(value)
            except MoneyError as exc:
                raise ReviseError("invalid_patch", str(exc)) from exc

        elif field in {"from_account_id", "to_account_id", "card_account_id"}:
            if field not in allowed_accounts:
                raise ReviseError("invalid_patch", f"Jenis '{kind}' tidak punya field '{field}'")
            revised[field] = str(_account(db, user_id, value).id)

        elif field == "occurred_at":
            revised["occurred_at"] = _moment(value)

        else:
            text = _text(value, field)

            if text is None:
                revised.pop(field, None)
            else:
                revised[field] = text

    # A refund without a category cannot be attributed to what it
    # reverses, so clearing it is refused rather than stored.
    if kind == "refund" and not revised.get("category"):
        raise ReviseError("invalid_patch", "Refund memerlukan kategori transaksi aslinya")

    return revised


def _revise_batch(db: DbSession, user_id: uuid.UUID, draft: Draft, patch: dict) -> Draft:
    """Change one entry of a batch.

    `item` is the entry's position in the list, which is also how the
    card numbers them. Everything else is the ordinary field patch, run
    through the same validation a single entry gets - so filling in the
    wallet the model could not work out goes down exactly the path that
    checks it belongs to this user.

    The whole batch is rebuilt afterwards rather than the one entry
    patched in place: the totals, the reconciliation against what the
    person said, and the combined impact are all facts about the list,
    not about the row that changed.
    """
    index = patch.pop("item", None)
    items = draft.payload.get("items") or []

    if not isinstance(index, int) or not 0 <= index < len(items):
        raise ReviseError("invalid_patch", "Catatan yang mau diubah nggak ketemu")

    if not patch:
        raise ReviseError("invalid_patch", "Tidak ada yang diubah")

    target = items[index]
    kind = target.get("type")

    if kind not in REVISABLE_KINDS:
        raise ReviseError("kind_not_revisable", "Catatan jenis ini belum bisa diubah")

    current = {key: value for key, value in target.items() if key != "unresolved"}
    revised = _apply(db, user_id, kind, current, patch)

    if revised == current:
        raise ReviseError("invalid_patch", "Tidak ada yang berubah")

    rebuilt = []

    for position, item in enumerate(items):
        payload = {key: value for key, value in item.items() if key != "unresolved"}

        if position == index:
            payload = revised

        # Recomputed, not carried over: the point of most of these
        # patches is to empty this list.
        rebuilt.append(
            {
                "payload": payload,
                "unresolved": [
                    field
                    for field in ACCOUNT_FIELDS.get(payload.get("type"), ())
                    if field in payload and payload[field] is None
                ],
            }
        )

    draft.status = DraftStatus.CANCELLED

    try:
        replacement = _store_batch(db, user_id, rebuilt, draft.payload.get("stated_total"))
    except DomainError as exc:
        raise ReviseError("invalid_patch", str(exc)) from exc

    db.query(Message).filter(Message.user_id == user_id, Message.draft_id == draft.id).update(
        {"draft_id": replacement.id}, synchronize_session=False
    )
    db.flush()

    return replacement


def revise_draft(db: DbSession, *, user_id: uuid.UUID, draft: Draft, patch: dict) -> Draft:
    """Cancel `draft` and return its revised replacement.

    The caller has already established that `draft` is this user's and
    still pending.
    """
    if not isinstance(patch, dict) or not patch:
        raise ReviseError("invalid_patch", "Tidak ada yang diubah")

    if draft.kind == "batch":
        return _revise_batch(db, user_id, draft, dict(patch))

    if draft.kind not in REVISABLE_KINDS:
        raise ReviseError("kind_not_revisable", "Draft jenis ini belum bisa diubah")

    revised = _apply(db, user_id, draft.kind, draft.payload, patch)

    if revised == draft.payload:
        raise ReviseError("invalid_patch", "Tidak ada yang berubah")

    # The same call the original preview went through, so a revised card
    # and a fresh one cannot disagree about what will happen. It also
    # re-runs the ledger's own validation - a transfer to the same
    # wallet, a card payment to a bank - before anything is stored.
    try:
        impact = _impact_for(db, user_id, revised)
    except DomainError as exc:
        raise ReviseError("invalid_patch", str(exc)) from exc
    except ValueError as exc:
        # Pydantic's own refusal, e.g. an amount that is not an integer.
        raise ReviseError("invalid_patch", "Draft hasil perubahan tidak valid") from exc

    draft.status = DraftStatus.CANCELLED

    replacement = _store_draft(db, user_id=user_id, kind=draft.kind, payload=revised, impact=impact)

    # The thread keeps one card per proposal rather than growing a
    # cancelled one per edit. The superseded row stays in `drafts` and
    # is still queryable; what moves is only which draft the message
    # points at, and nothing was ever posted from the old one.
    db.query(Message).filter(Message.user_id == user_id, Message.draft_id == draft.id).update(
        {"draft_id": replacement.id}, synchronize_session=False
    )

    db.flush()

    return replacement
