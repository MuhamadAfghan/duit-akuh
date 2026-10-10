"""The chat loop.

One turn: take the user's message, give the model the conversation so
far plus the tool list, run whatever tools it calls, feed the results
back, and return the assistant's reply together with any drafts raised.

Three constraints from the PRD shape this:

* **History is summarised by truncation.** The model has 24,576 tokens
  for prompt *and* output, shared with tool schemas and results, so only
  a recent window of the thread is sent.
* **A bounded number of tool rounds.** Each round is another call to a
  shared GPU; an unbounded loop would hold a slot and could not finish
  inside Cloudflare's window anyway.
* **Failure must leave manual entry working** (AC09/AC22). An AI error
  becomes a plain assistant message saying so, never a 500 that loses
  the user's text.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...models import AiRequestLog, Conversation, Draft, Message, MessageRole
from ..ai.base import AiAdapter, AiError, ChatResult
from .dispatch import dispatch
from .tools import ALL_TOOLS, PROPOSE_TOOL_NAMES, SYSTEM_PROMPT

#: How many past turns to send. Enough for "the account I just
#: mentioned" to resolve, small enough to leave room for tool results.
HISTORY_LIMIT = 20

#: Tool rounds per user message. Two covers the common
#: find_transactions -> propose_correction chain; more suggests the
#: model is looping.
MAX_TOOL_ROUNDS = 3

FAILURE_REPLY = (
    "Maaf, layanan AI sedang tidak bisa dihubungi. "
    "Transaksi tetap bisa dicatat manual lewat halaman Data."
)


@dataclass
class TurnResult:
    """What one user message produced."""

    reply: str
    drafts: list[Draft] = field(default_factory=list)
    #: True when the AI failed and the reply is the manual-entry fallback.
    degraded: bool = False


def get_or_create_conversation(db: DbSession, user_id: uuid.UUID) -> Conversation:
    """The single thread for this user (FR14, FR15)."""
    conversation = db.scalar(select(Conversation).where(Conversation.user_id == user_id))

    if conversation is None:
        conversation = Conversation(id=uuid.uuid4(), user_id=user_id)
        db.add(conversation)
        db.flush()

    return conversation


def recent_messages(
    db: DbSession, conversation_id: uuid.UUID, limit: int = HISTORY_LIMIT
) -> list[Message]:
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(limit)
    ).all()

    return list(reversed(rows))


def _as_prompt(messages: list[Message]) -> list[dict[str, Any]]:
    """Render stored turns for the model.

    Card turns carry no prose, so they are described rather than sent
    empty — otherwise the model loses track of what it already proposed.
    """
    rendered = []

    for message in messages:
        if message.body:
            rendered.append({"role": message.role.value, "content": message.body})
        elif message.draft_id:
            rendered.append(
                {"role": "assistant", "content": "[kartu draft menunggu konfirmasi pengguna]"}
            )

    return rendered


def _log_ai(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    result: ChatResult | None,
    started: float,
    status: str,
    error: str | None = None,
    operation_id: str | None = None,
) -> None:
    """Record the request per PRD section 13.

    Tool **names** only. Their arguments carry amounts and account names,
    which belong in the user's data, not in an operational log.
    """
    db.add(
        AiRequestLog(
            user_id=user_id,
            kind="chat",
            model=result.model if result else "",
            operation_id=operation_id,
            prompt_tokens=result.usage.prompt_tokens if result else None,
            completion_tokens=result.usage.completion_tokens if result else None,
            latency_ms=int((time.monotonic() - started) * 1000),
            status=status,
            error=error[:500] if error else None,
            tool_calls=[c.name for c in result.tool_calls] if result else None,
        )
    )


async def run_turn(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    adapter: AiAdapter,
    body: str,
) -> TurnResult:
    """Process one user message end to end."""
    conversation = get_or_create_conversation(db, user_id)

    db.add(
        Message(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            body=body,
        )
    )
    db.flush()

    prompt: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    prompt += _as_prompt(recent_messages(db, conversation.id))

    drafts: list[Draft] = []
    reply = ""
    degraded = False

    for _ in range(MAX_TOOL_ROUNDS):
        started = time.monotonic()

        try:
            result = await adapter.chat(messages=prompt, tools=ALL_TOOLS)
        except AiError as exc:
            _log_ai(
                db, user_id=user_id, result=None, started=started, status="error", error=str(exc)
            )
            reply = FAILURE_REPLY
            degraded = True
            break

        _log_ai(db, user_id=user_id, result=result, started=started, status="ok")

        if not result.tool_calls:
            reply = result.content.strip()
            break

        # Echo the assistant's tool call turn, then each result, exactly
        # as the OpenAI protocol expects.
        prompt.append(
            {
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in result.tool_calls
                ],
            }
        )

        for call in result.tool_calls:
            output = dispatch(db, user_id, call.name, call.arguments)

            if call.name in PROPOSE_TOOL_NAMES and "error" not in output:
                drafts.extend(_collect_drafts(db, user_id, output))

            prompt.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(output, ensure_ascii=False, default=str),
                }
            )

        reply = result.content.strip()
    else:
        # Ran out of rounds with the model still calling tools.
        reply = reply or "Aku belum berhasil menyelesaikan itu. Bisa diperjelas?"

    if not reply and drafts:
        reply = "Ini draftnya. Periksa dulu, lalu konfirmasi kalau sudah benar."

    if not reply:
        reply = "Maaf, aku belum paham maksudnya. Bisa diulang dengan nominal dan kantongnya?"

    assistant = Message(
        id=uuid.uuid4(),
        user_id=user_id,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        body=reply,
    )
    db.add(assistant)

    for draft in drafts:
        db.add(
            Message(
                id=uuid.uuid4(),
                user_id=user_id,
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                draft_id=draft.id,
            )
        )

    db.flush()

    return TurnResult(reply=reply, drafts=drafts, degraded=degraded)


def _collect_drafts(db: DbSession, user_id: uuid.UUID, output: dict) -> list[Draft]:
    """Pull the Draft rows a propose tool just created out of its result."""
    ids = []

    if output.get("draft_id"):
        ids.append(output["draft_id"])

    for item in output.get("drafts") or []:
        if isinstance(item, dict) and item.get("draft_id"):
            ids.append(item["draft_id"])

    if not ids:
        return []

    return list(
        db.scalars(
            select(Draft).where(Draft.user_id == user_id, Draft.id.in_([uuid.UUID(i) for i in ids]))
        ).all()
    )
