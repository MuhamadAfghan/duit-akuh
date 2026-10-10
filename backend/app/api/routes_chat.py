"""Chat endpoints.

The single thread (FR14): send a message, read the history, confirm or
cancel a draft the assistant raised.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import get_settings
from ..models import Draft, DraftStatus
from ..services.ai.base import AiAdapter
from ..services.ai.openai_compat import OpenAiCompatAdapter
from ..services.chat.confirm import DraftNotPending, cancel_draft, confirm_draft
from ..services.chat.dispatch import pending_draft
from ..services.chat.orchestrator import get_or_create_conversation, recent_messages, run_turn
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


class DraftOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: DraftStatus
    payload: dict
    impact: list[dict] | None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    body: str | None
    draft: DraftOut | None = None


class TurnOut(BaseModel):
    reply: str
    drafts: list[DraftOut]
    #: True when the AI was unreachable and the reply is the
    #: manual-entry fallback rather than a real answer (AC22).
    degraded: bool


def _draft_out(draft: Draft) -> DraftOut:
    return DraftOut(
        id=draft.id,
        kind=draft.kind,
        status=draft.status,
        payload=draft.payload,
        impact=(draft.impact or {}).get("rows") if draft.impact else None,
    )


@router.get("/messages", response_model=list[MessageOut])
def list_messages(user: CurrentUser, db: DbSessionDep) -> list[MessageOut]:
    """The thread, oldest first.

    This is what makes the conversation survive navigation and a new
    device, which local component state cannot (FR15).
    """
    conversation = get_or_create_conversation(db, user.id)
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
            draft=_draft_out(drafts[m.draft_id]) if m.draft_id in drafts else None,
        )
        for m in messages
    ]


@router.post("/messages", response_model=TurnOut)
async def send_message(body: SendMessageIn, user: CurrentUser, db: DbSessionDep) -> TurnOut:
    result = await run_turn(db, user_id=user.id, adapter=get_adapter(), body=body.body)

    return TurnOut(
        reply=result.reply,
        drafts=[_draft_out(d) for d in result.drafts],
        degraded=result.degraded,
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


@router.post("/drafts/{draft_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel(draft_id: uuid.UUID, user: CurrentUser, db: DbSessionDep) -> None:
    draft = pending_draft(db, user.id, draft_id)

    if draft is None:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found"})

    cancel_draft(db, draft)
