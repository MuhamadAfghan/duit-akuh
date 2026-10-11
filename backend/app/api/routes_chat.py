"""Chat endpoints.

The single thread (FR14): send a message, read the history, confirm or
cancel a draft the assistant raised.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..models import Draft, DraftStatus, Message
from ..services.ai.base import AiAdapter
from ..services.ai.limits import (
    RATE_WINDOW,
    AiBusy,
    AiRateLimited,
    AlreadyProcessing,
    check_rate_limit,
    gate,
)
from ..services.ai.openai_compat import OpenAiCompatAdapter
from ..services.chat.confirm import DraftNotPending, cancel_draft, confirm_draft
from ..services.chat.dispatch import pending_draft
from ..services.chat.orchestrator import (
    recent_messages,
    run_turn,
    run_turn_events,
)
from ..services.chat.revise import ReviseError, revise_draft
from ..services.chat.sessions import (
    ConversationNotFound,
    ConversationRow,
    active_conversation,
    create_conversation,
    list_conversations,
    owned,
    rename,
    set_flags,
)
from .deps import CurrentUser, DbSessionDep

router = APIRouter(prefix="/chat", tags=["chat"])

#: Overridden in tests with a deterministic fake, so the orchestrator can
#: be exercised without a network or a GPU.
_adapter_override: AiAdapter | None = None


def set_adapter(adapter: AiAdapter | None) -> None:
    global _adapter_override
    _adapter_override = adapter


def get_adapter() -> AiAdapter:
    if _adapter_override is not None:
        return _adapter_override

    settings = get_settings()

    if not settings.llm_base_url:
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_not_configured", "message": "LLM_BASE_URL belum diatur"},
        )

    return OpenAiCompatAdapter(
        base_url=settings.llm_base_url,
        # Read at call time so the key is never held on a long-lived
        # object that might be logged or serialised.
        api_key=settings.require_llm_api_key(),
        model=settings.llm_model,
    )


class SendMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    #: Which thread this belongs to. Omitted means the most recently
    #: used one, so a client that knows nothing about sessions - an old
    #: build, a fresh install - still lands somewhere sensible.
    conversation_id: uuid.UUID | None = None
    #: The turn this one answers. Optional, and validated against the
    #: sender before it is stored - an id from someone else's thread
    #: must not become a quote in this one (AC08).
    reply_to_id: uuid.UUID | None = None


class DraftOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: DraftStatus
    payload: dict
    impact: list[dict] | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    is_pinned: bool
    is_archived: bool
    created_at: datetime
    #: The last thing said in it, and when. Both null for a thread with
    #: no prose yet - a turn that is only a card has nothing to quote.
    preview: str | None = None
    last_at: datetime | None = None


class ConversationPatchIn(BaseModel):
    """Rename, pin or archive. Every field optional, none required."""

    title: str | None = Field(default=None, max_length=120)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class ReplyRefOut(BaseModel):
    """Enough of the quoted turn to draw the block above a bubble.

    Sent inline rather than left for the client to look up: the quoted
    message may be older than the window the thread holds, and a quote
    that renders as an empty box is worse than no quote.
    """

    id: uuid.UUID
    role: str
    excerpt: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    body: str | None
    #: When the turn was written, so every bubble can say its own time.
    #: `seq` orders the thread; this is only ever shown, never sorted on
    #: - every message in one turn shares a transaction timestamp.
    created_at: datetime
    reply_to: ReplyRefOut | None = None
    #: A read tool's result the client can draw: {"kind", "data"}.
    #: Nothing here proposes a change, so it carries no confirmation.
    view: dict | None = None
    draft: DraftOut | None = None


class TurnOut(BaseModel):
    reply: str
    drafts: list[DraftOut]
    #: True when the AI was unreachable and the reply is the
    #: manual-entry fallback rather than a real answer (AC22).
    degraded: bool


#: The same cut the model's prompt uses, so a quote does not say one
#: thing on screen and another to the assistant.
REPLY_EXCERPT_CHARS = 160


def _reply_out(message: Message | None) -> ReplyRefOut | None:
    if message is None or not message.body:
        return None

    excerpt = " ".join(message.body.split())

    if len(excerpt) > REPLY_EXCERPT_CHARS:
        excerpt = f"{excerpt[:REPLY_EXCERPT_CHARS].rstrip()}…"

    return ReplyRefOut(id=message.id, role=message.role.value, excerpt=excerpt)


def _reply_target(
    db: DbSessionDep,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    reply_to_id: uuid.UUID | None,
):
    """Refuse a quote the sender does not own, or that is not in here.

    404 whether it is missing, someone else's, or from another thread:
    telling them apart would confirm which message ids exist. The
    thread check is not pedantry - a quote lifted out of one
    conversation into another arrives with no context behind it, and
    the model would be answering about a turn it cannot see.
    """
    if reply_to_id is None:
        return None

    quoted = db.get(Message, reply_to_id)

    if quoted is None or quoted.user_id != user_id or quoted.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail={"code": "message_not_found"})

    return reply_to_id


def _target_thread(db: DbSessionDep, user_id: uuid.UUID, conversation_id: uuid.UUID | None):
    """The thread a turn is being added to, resolved up front.

    Here rather than inside the orchestrator because this is the layer
    holding the request: a bad id has to become a status code, and by
    the time the generator runs the response has already begun.
    """
    try:
        return active_conversation(db, user_id, conversation_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"}) from exc


def _conversation_out(row: ConversationRow) -> ConversationOut:
    conversation = row.conversation

    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        is_pinned=conversation.is_pinned,
        is_archived=conversation.is_archived,
        created_at=conversation.created_at,
        preview=row.preview,
        last_at=row.last_at,
    )


def _draft_out(draft: Draft) -> DraftOut:
    return DraftOut(
        id=draft.id,
        kind=draft.kind,
        status=draft.status,
        payload=draft.payload,
        impact=(draft.impact or {}).get("rows") if draft.impact else None,
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_threads(
    user: CurrentUser, db: DbSessionDep, include_archived: bool = False
) -> list[ConversationOut]:
    """Every thread, pinned first, then by most recent activity."""
    return [
        _conversation_out(row)
        for row in list_conversations(db, user.id, include_archived=include_archived)
    ]


@router.get("/conversations/active", response_model=ConversationOut)
def active_thread(
    user: CurrentUser, db: DbSessionDep, conversation_id: uuid.UUID | None = None
) -> ConversationOut:
    """Which thread the chat opens on.

    Creates one when the account has none, which is the same thing
    reading the messages has always done: a user must never have to
    choose a conversation before they can type.
    """
    try:
        conversation = active_conversation(db, user.id, conversation_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"}) from exc

    return _conversation_out(ConversationRow(conversation=conversation, preview=None, last_at=None))


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def new_thread(user: CurrentUser, db: DbSessionDep) -> ConversationOut:
    """An empty thread. It stays untitled until its first message."""
    conversation = create_conversation(db, user.id)

    return _conversation_out(ConversationRow(conversation=conversation, preview=None, last_at=None))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def edit_thread(
    conversation_id: uuid.UUID,
    body: ConversationPatchIn,
    user: CurrentUser,
    db: DbSessionDep,
) -> ConversationOut:
    """Rename, pin or archive one thread.

    There is no delete. Archiving takes a thread out of the list, which
    is what the list is for; removing it would destroy the only record
    of why a transaction was entered, while the transaction itself -
    and the audit trail money changes carry - would survive without it.
    """
    try:
        conversation = owned(db, user.id, conversation_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"}) from exc

    if body.title is not None:
        try:
            rename(db, conversation, body.title)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "invalid_title", "message": str(exc)}
            ) from exc

    if body.is_pinned is not None or body.is_archived is not None:
        set_flags(db, conversation, is_pinned=body.is_pinned, is_archived=body.is_archived)

    return _conversation_out(ConversationRow(conversation=conversation, preview=None, last_at=None))


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    user: CurrentUser, db: DbSessionDep, conversation_id: uuid.UUID | None = None
) -> list[MessageOut]:
    """One thread, oldest first.

    This is what makes the conversation survive navigation and a new
    device, which local component state cannot (FR15).
    """
    try:
        conversation = active_conversation(db, user.id, conversation_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"}) from exc
    messages = recent_messages(db, conversation.id, limit=200)

    drafts = (
        {
            d.id: d
            for d in db.query(Draft)
            .filter(
                Draft.user_id == user.id, Draft.id.in_([m.draft_id for m in messages if m.draft_id])
            )
            .all()
        }
        if any(m.draft_id for m in messages)
        else {}
    )

    return [
        MessageOut(
            id=m.id,
            role=m.role.value,
            body=m.body,
            created_at=m.created_at,
            reply_to=_reply_out(m.reply_to),
            view=m.view,
            draft=_draft_out(drafts[m.draft_id]) if m.draft_id in drafts else None,
        )
        for m in messages
    ]


@router.post("/messages", response_model=TurnOut)
async def send_message(body: SendMessageIn, user: CurrentUser, db: DbSessionDep) -> TurnOut:
    """Process one message.

    Guarded by the limits in `services/ai/limits.py`: the AI server's 16
    parallel slots are shared with other applications, so one user must
    not be able to exhaust them.
    """
    try:
        check_rate_limit(db, user.id)
    except AiRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": exc.code, "message": str(exc)},
            # Standard, and it saves the client guessing: the window is
            # a minute, so there is no point retrying sooner.
            headers={"Retry-After": str(int(RATE_WINDOW.total_seconds()))},
        ) from exc

    conversation = _target_thread(db, user.id, body.conversation_id)
    reply_to_id = _reply_target(db, user.id, conversation.id, body.reply_to_id)

    try:
        async with gate.slot(user.id):
            result = await run_turn(
                db,
                user_id=user.id,
                adapter=get_adapter(),
                body=body.body,
                reply_to_id=reply_to_id,
                conversation_id=conversation.id,
            )
    except AlreadyProcessing as exc:
        # 409, not 429: nothing is wrong with the rate, the previous
        # turn simply has not finished.
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except AiBusy as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
            headers={"Retry-After": "10"},
        ) from exc

    return TurnOut(
        reply=result.reply,
        drafts=[_draft_out(d) for d in result.drafts],
        degraded=result.degraded,
    )


@router.post("/messages/stream")
async def send_message_streaming(
    body: SendMessageIn, user: CurrentUser, db: DbSessionDep
) -> StreamingResponse:
    """Process one message, streaming progress as newline-delimited JSON.

    NDJSON over a plain POST rather than SSE: `EventSource` cannot POST,
    and the client already reads the body as a stream. One JSON object
    per line, each with a `type`.

    Errors are emitted **inside the stream** rather than as a status
    code. By the time a tool fails the response has already begun, so
    the status is long since sent; a client that only checked it would
    see a success for a turn that failed.
    """
    try:
        check_rate_limit(db, user.id)
    except AiRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": exc.code, "message": str(exc)},
            headers={"Retry-After": str(int(RATE_WINDOW.total_seconds()))},
        ) from exc

    if gate.is_processing(user.id):
        raise HTTPException(
            status_code=409,
            detail={"code": "already_processing", "message": "Pesan sebelumnya masih diproses."},
        )

    # Resolved before the response opens. Once the first byte is out the
    # status is sent, and a 404 raised from inside the generator would
    # reach the client as a broken stream on a 200.
    conversation = _target_thread(db, user.id, body.conversation_id)
    reply_to_id = _reply_target(db, user.id, conversation.id, body.reply_to_id)

    async def events():
        def line(payload: dict) -> str:
            return json.dumps(payload, ensure_ascii=False) + "\n"

        try:
            async with gate.slot(user.id):
                async for event in run_turn_events(
                    db,
                    user_id=user.id,
                    adapter=get_adapter(),
                    body=body.body,
                    reply_to_id=reply_to_id,
                    conversation_id=conversation.id,
                ):
                    if event["type"] == "done":
                        result = event["result"]
                        yield line(
                            {
                                "type": "done",
                                "reply": result.reply,
                                "degraded": result.degraded,
                                "drafts": [
                                    _draft_out(d).model_dump(mode="json") for d in result.drafts
                                ],
                            }
                        )
                    else:
                        yield line(event)
        except AlreadyProcessing as exc:
            yield line({"type": "error", "code": exc.code, "message": str(exc)})
        except AiBusy as exc:
            yield line({"type": "error", "code": exc.code, "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - the stream must not just stop
            # A half-written stream that simply ends looks to the client
            # like a success with a short reply. Say what happened.
            yield line(
                {
                    "type": "error",
                    "code": "internal_error",
                    "message": "Terjadi kesalahan. Coba lagi, atau catat manual.",
                }
            )
            raise exc

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        # Buffering here would defeat the point; nginx needs telling.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/drafts/{draft_id}/confirm", status_code=status.HTTP_200_OK)
def confirm(draft_id: uuid.UUID, user: CurrentUser, db: DbSessionDep) -> dict:
    """Apply a draft.

    Posts from the stored draft, not from the model's output, so what
    the card showed is what gets written.
    """
    draft = pending_draft(db, user.id, draft_id)

    if draft is None:
        # 404 whether it is missing, already handled, or someone else's:
        # distinguishing them would confirm the id exists.
        raise HTTPException(status_code=404, detail={"code": "draft_not_found"})

    try:
        return confirm_draft(db, user_id=user.id, draft=draft)
    except DraftNotPending as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc


class ReviseDraftIn(BaseModel):
    #: Only the fields that changed. Validated field by field against an
    #: allowlist in the service - an unknown key is an error, not a
    #: no-op, so a typo cannot look like a successful edit.
    patch: dict


@router.post("/drafts/{draft_id}/revise", response_model=DraftOut)
def revise(
    draft_id: uuid.UUID, body: ReviseDraftIn, user: CurrentUser, db: DbSessionDep
) -> DraftOut:
    """Change a pending draft before it is confirmed.

    Returns a *different* draft: the one named here is cancelled and
    replaced, so a confirmation already on its way with the old id can
    no longer post. The figures come back recomputed by the same code
    that produced the first preview.
    """
    draft = pending_draft(db, user.id, draft_id)

    if draft is None:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found"})

    try:
        return _draft_out(revise_draft(db, user_id=user.id, draft=draft, patch=body.patch))
    except ReviseError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc


@router.post("/drafts/{draft_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel(draft_id: uuid.UUID, user: CurrentUser, db: DbSessionDep) -> None:
    draft = pending_draft(db, user.id, draft_id)

    if draft is None:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found"})

    cancel_draft(db, draft)
