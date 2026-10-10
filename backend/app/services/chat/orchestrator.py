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

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...models import Account, AiRequestLog, Conversation, Draft, Message, MessageRole, User
from ..ai.base import AiAdapter, AiError, ChatResult
from .dispatch import dispatch
from .tools import ALL_TOOLS, PROPOSE_TOOL_NAMES, build_system_prompt

#: How many past turns to send. Enough for "the account I just
#: mentioned" to resolve, small enough to leave room for tool results.
HISTORY_LIMIT = 20

#: Tool rounds per user message. Observed live, a single "top up X from
#: Y" needs three: get_accounts, propose_transactions, then the reply —
#: so three was exactly the ceiling and anything needing one more lookup
#: was being cut off. Five leaves headroom while still bounding how long
#: a turn can hold a slot on the shared GPU.
MAX_TOOL_ROUNDS = 5

FAILURE_REPLY = (
    "Maaf, layanan AI sedang tidak bisa dihubungi. "
    "Transaksi tetap bisa dicatat manual lewat halaman Data."
)

#: Words the model uses when it believes it recorded something. Matched
#: only to catch it claiming a draft it never created - see
#: `_claims_a_draft`.
_CLAIM_WORDS = re.compile(
    r"\b(draft|tersimpan|disimpan|dicatat|saya catat|aku catat)\b",
    re.IGNORECASE,
)

#: One corrective round when the model answered in prose instead of
#: calling a tool. Bounded to a single retry: if it will not comply twice,
#: the honest thing is to say so rather than keep burning GPU slots.
_NUDGE = (
    "Kamu menjawab seolah draft sudah dibuat, padahal kamu tidak memanggil "
    "tool apa pun, jadi tidak ada draft dan pengguna tidak melihat kartu. "
    "Panggil tool propose_* sekarang dengan data yang sama. Jangan menjawab "
    "dengan teks saja."
)

HONEST_FALLBACK = (
    "Maaf, aku belum berhasil membuat draftnya. Coba ulangi dengan menyebut "
    'nominal dan kantongnya, misalnya: "makan 35rb pakai BCA".'
)


def _claims_a_draft(reply: str) -> bool:
    """True when a reply sounds like something was drafted or saved.

    Deliberately crude. It exists because the opposite failure is severe:
    the model sometimes describes a draft in prose without calling a
    tool, and the user is then told their transaction was recorded when
    nothing exists. A false positive costs one extra model round; a false
    negative misleads someone about their money.
    """
    return bool(_CLAIM_WORDS.search(reply))


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

    Card turns are rendered as an explicit statement that a tool was
    called. Without that the history contains only prose replies, and
    the model copies the pattern — answering "Draft transaksi: ..." in
    text without ever calling propose_*, so the user sees a reply
    claiming a draft that does not exist. Observed against the real
    model; `test_history_shows_that_tools_were_used` guards it.
    """
    rendered: list[dict[str, Any]] = []

    for message in messages:
        if message.body:
            rendered.append({"role": message.role.value, "content": message.body})
        elif message.draft_id:
            rendered.append(
                {
                    "role": "assistant",
                    "content": (
                        "[Aku memanggil tool propose_* dan kartu draft tampil. "
                        "Draft hanya muncul lewat tool, bukan lewat teks.]"
                    ),
                }
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
    db: DbSession, *, user_id: uuid.UUID, adapter: AiAdapter, body: str
) -> TurnResult:
    """Process one message and return the finished turn.

    Drains :func:`run_turn_events`, so the streaming and non-streaming
    paths cannot drift apart - there is one implementation and two
    presentations of it.
    """
    result: TurnResult | None = None

    async for event in run_turn_events(db, user_id=user_id, adapter=adapter, body=body):
        if event["type"] == "done":
            result = event["result"]

    assert result is not None, "run_turn_events must always end with a done event"

    return result


async def run_turn_events(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    adapter: AiAdapter,
    body: str,
) -> AsyncIterator[dict[str, Any]]:
    """Process one user message, yielding progress as it happens.

    Events: ``token`` for each content fragment, ``tool`` when one is
    called, ``draft`` when a card is raised, and finally ``done``
    carrying the TurnResult. The browser gets something to show within
    a second instead of a blank wait.
    """
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

    # The model has no clock. Without today's date it dates "kemarin"
    # from memory, which lands years off.
    user_timezone = getattr(db.get(User, user_id), "timezone", None) or "Asia/Jakarta"

    try:
        now_local = datetime.now(ZoneInfo(user_timezone))
    except ZoneInfoNotFoundError:
        now_local = datetime.now(timezone.utc)
        user_timezone = "UTC"

    # The model cannot name a wallet it has not been shown. Without the
    # list it invented names - "cc" went out as "credit_card" - and
    # every such turn failed.
    wallets = [
        (a.name, a.type.value, a.alias)
        for a in db.scalars(
            select(Account)
            .where(
                Account.user_id == user_id,
                Account.is_system.is_(False),
                Account.is_archived.is_(False),
            )
            .order_by(Account.name)
        ).all()
    ]

    prompt: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(now_local, user_timezone, wallets),
        }
    ]
    prompt += _as_prompt(recent_messages(db, conversation.id))

    drafts: list[Draft] = []
    reply = ""
    degraded = False

    for _ in range(MAX_TOOL_ROUNDS):
        started = time.monotonic()

        streamed_any = False

        try:
            # Tokens are forwarded as they arrive rather than collected
            # and flushed at the end. Buffering them put a silent gap of
            # a second or more between the tool finishing and any text
            # appearing, which is the wait this exists to remove.
            async for item in _stream_round(adapter, prompt):
                if isinstance(item, str):
                    streamed_any = True
                    yield {"type": "token", "text": item}
                else:
                    result = item
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

        # Text produced alongside a tool call is the model narrating a
        # plan, not answering. It has already been streamed, so tell the
        # client to drop it rather than leave a bubble claiming
        # something happened before it did.
        if streamed_any:
            yield {"type": "reset"}

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
            yield {"type": "tool", "name": call.name}

            output = dispatch(db, user_id, call.name, call.arguments)

            if call.name in PROPOSE_TOOL_NAMES and "error" not in output:
                new_drafts = _collect_drafts(db, user_id, output)
                drafts.extend(new_drafts)

                for draft in new_drafts:
                    yield {"type": "draft", "draft_id": str(draft.id)}

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

    # The model sometimes answers "Draft sudah dibuat" without having
    # called a tool. Rather than pass that on, give it one chance to
    # actually do it.
    if not degraded and not drafts and _claims_a_draft(reply):
        reply, drafts = await _retry_with_nudge(
            db, user_id=user_id, adapter=adapter, prompt=prompt, previous_reply=reply
        )

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

    yield {
        "type": "done",
        "result": TurnResult(reply=reply, drafts=drafts, degraded=degraded),
    }


async def _retry_with_nudge(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    adapter: AiAdapter,
    prompt: list[dict[str, Any]],
    previous_reply: str,
) -> tuple[str, list[Draft]]:
    """One corrective round after the model answered in prose.

    Returns the reply and drafts to use. If the retry still produces
    nothing, the reply says so plainly instead of repeating the model's
    false claim.
    """
    retry_prompt = [
        *prompt,
        {"role": "assistant", "content": previous_reply},
        {"role": "user", "content": _NUDGE},
    ]
    started = time.monotonic()

    try:
        result = await adapter.chat(messages=retry_prompt, tools=ALL_TOOLS)
    except AiError as exc:
        _log_ai(db, user_id=user_id, result=None, started=started, status="error", error=str(exc))
        return HONEST_FALLBACK, []

    _log_ai(db, user_id=user_id, result=result, started=started, status="ok")

    drafts: list[Draft] = []

    for call in result.tool_calls:
        output = dispatch(db, user_id, call.name, call.arguments)

        if call.name in PROPOSE_TOOL_NAMES and "error" not in output:
            drafts.extend(_collect_drafts(db, user_id, output))

    if drafts:
        return (result.content.strip() or "Ini draftnya. Periksa dulu, lalu konfirmasi."), drafts

    return HONEST_FALLBACK, []


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


async def _stream_round(adapter: AiAdapter, prompt: list[dict[str, Any]]):
    """Run one model call, yielding each token then the finished result.

    The adapter reports tokens through a synchronous callback while it
    is awaited, so they go onto a queue and are drained here. Without
    this the generator could only yield after the whole call returned,
    which is the buffering it exists to avoid.

    Yields ``str`` for each fragment and finally the :class:`ChatResult`.
    """
    queue: asyncio.Queue[str] = asyncio.Queue()
    call = asyncio.create_task(
        adapter.chat(messages=prompt, tools=ALL_TOOLS, on_delta=queue.put_nowait)
    )

    try:
        while True:
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({getter, call}, return_when=asyncio.FIRST_COMPLETED)

            if getter in done:
                yield getter.result()
                continue

            # The call finished. Cancel the pending read and drain
            # whatever landed in the queue just before it did.
            getter.cancel()
            break
    finally:
        if not call.done():
            call.cancel()

    while not queue.empty():
        yield queue.get_nowait()

    # Re-raises AiError here, where the caller already handles it.
    yield await call
