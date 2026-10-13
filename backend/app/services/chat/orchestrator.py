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

from ...models import (
    Account,
    AiRequestLog,
    Conversation,
    Draft,
    DraftStatus,
    Message,
    MessageRole,
    User,
)
from ...money import format_rupiah
from ..ai.base import AiAdapter, AiError, ChatResult
from ..reporting import known_expense_categories, known_income_categories
from .dispatch import dispatch
from .sessions import active_conversation, name_if_unnamed
from .tools import ALL_TOOLS, PROPOSE_TOOL_NAMES, build_system_prompt

#: Read tools whose output the client knows how to draw, mapped to the
#: card it should render. A tool not listed here is simply narrated, and
#: adding one here is the only thing needed to make a new card appear.
DRAWABLE_TOOLS = {"get_spending": "spending"}

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
    r"\b(draft"
    r"|tersimpan|disimpan|dicatat"
    # "saya akan catat", "aku akan mencatat", "akan saya catat". The
    # first version of this required the two words to be adjacent, so
    # every phrasing with "akan" between them walked straight through —
    # which is the one the model actually uses.
    r"|(saya|aku)?\s*akan\s*(saya|aku)?\s*(men)?catat"
    r"|(saya|aku)\s+(men)?catat"
    r")\b",
    re.IGNORECASE,
)

#: A reply that asks the person to confirm, when no card was raised.
#:
#: The same failure wearing different words, and the more common one in
#: practice: the model lists the entries, asks "apakah ini sudah
#: benar?", and waits. There is nothing to answer — no card, no draft —
#: so "ok" only makes it ask again, which is the loop this catches.
_ASKS_TO_CONFIRM = re.compile(
    r"(apakah\s+(ini|itu|semua|data|rincian)?\s*(sudah\s+)?(benar|sesuai|betul)"
    r"|sudah\s+(benar|sesuai)\s*\?"
    r"|mohon\s+(di)?koreksi"
    r"|beri\s*tahu\s+(saya|aku)\s+(jika|kalau)\s+(ada|ini|itu|salah|perlu))",
    re.IGNORECASE,
)

#: One corrective round when the model answered in prose instead of
#: calling a tool. Bounded to a single retry: if it will not comply twice,
#: the honest thing is to say so rather than keep burning GPU slots.
_NUDGE = (
    "Kamu menjawab seolah draft sudah dibuat atau meminta pengguna "
    "mengonfirmasi lewat teks, padahal kamu tidak memanggil tool apa pun. "
    "Tidak ada draft, tidak ada kartu, dan pengguna tidak punya apa pun "
    "untuk dikonfirmasi - kalau dia menjawab 'ok' tidak akan terjadi apa-apa. "
    "Panggil tool propose_* sekarang dengan data yang sama. Kalau pesan "
    "TERAKHIR pengguna menyebut beberapa transaksi, masukkan semuanya dalam "
    "SATU panggilan - tapi hanya yang disebut di pesan terakhir itu. Jangan "
    "menyertakan transaksi dari pesan-pesan sebelumnya: itu sudah diurus, dan "
    "mengusulkannya lagi membuat uang orang terhitung dua kali. "
    "Kartu yang akan bertanya, bukan kamu. "
    "Kalau ternyata pengguna memang tidak minta mencatat apa pun, jawab "
    "biasa saja tanpa membuat draft."
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
    nothing exists. A false positive costs one extra model round - and
    the nudge tells the model to answer normally if nothing was meant to
    be recorded, so it costs nothing else. A false negative misleads
    someone about their money, or leaves them answering "ok" to a
    question no card was ever asked.
    """
    return bool(_CLAIM_WORDS.search(reply) or _ASKS_TO_CONFIRM.search(reply))


@dataclass
class TurnResult:
    """What one user message produced."""

    reply: str
    drafts: list[Draft] = field(default_factory=list)
    #: True when the AI failed and the reply is the manual-entry fallback.
    degraded: bool = False


def get_or_create_conversation(
    db: DbSession, user_id: uuid.UUID, conversation_id: uuid.UUID | None = None
) -> Conversation:
    """The thread this turn belongs to (FR14, FR15).

    Kept as a name here because every caller already used it; the
    choosing lives in `services/chat/sessions.py` now that a user can
    have more than one.
    """
    return active_conversation(db, user_id, conversation_id)


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


#: What became of a card, in the words the model is shown. CONFIRMED
#: carries an instruction and not only a fact, because the fact alone
#: was not enough: told merely that a draft existed, the model folded
#: it into the next batch.
_DRAFT_OUTCOME = {
    DraftStatus.CONFIRMED: "SUDAH DISIMPAN. Jangan diusulkan lagi.",
    DraftStatus.CANCELLED: "Dibatalkan oleh pengguna, tidak tersimpan.",
    DraftStatus.STALE: "Kedaluwarsa, tidak tersimpan.",
    DraftStatus.PENDING: "Masih menunggu konfirmasi pengguna.",
}

#: A digest is a reminder, not a record. The window is 24,576 tokens for
#: prompt and output together, and twenty turns of full payloads would
#: crowd out the conversation they are there to explain.
DIGEST_CHARS = 160


def _entry_digest(payload: dict[str, Any]) -> str:
    """One transaction, in a few words."""
    parts = [str(payload.get("type") or "transaksi")]

    amount = payload.get("amount")
    if isinstance(amount, int):
        parts.append(format_rupiah(amount))

    for key in ("category", "merchant"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    return " ".join(parts)


def _draft_digest(draft: Draft) -> str:
    """What the card held, short enough to repeat twenty times."""
    payload = draft.payload or {}

    if draft.kind == "batch":
        items = [i for i in (payload.get("items") or []) if isinstance(i, dict)]
        inner = "; ".join(_entry_digest(item) for item in items)
        summary = f"{len(items)} transaksi: {inner}"
    elif draft.kind == "recategorise":
        summary = f"pindah kategori {payload.get('from_category')} -> {payload.get('to_category')}"
    elif draft.kind in {"expense", "income", "transfer", "card_payment", "refund"}:
        summary = _entry_digest(payload)
    else:
        summary = str(draft.kind)
        amount = payload.get("amount") or payload.get("target_amount")
        if isinstance(amount, int):
            summary = f"{summary} {format_rupiah(amount)}"

    summary = " ".join(summary.split())

    if len(summary) > DIGEST_CHARS:
        summary = f"{summary[:DIGEST_CHARS].rstrip()}…"

    return summary


def _as_prompt(
    messages: list[Message], drafts: dict[uuid.UUID, Draft] | None = None
) -> list[dict[str, Any]]:
    """Render stored turns for the model.

    Card turns are rendered as an explicit statement that a tool was
    called. Without that the history contains only prose replies, and
    the model copies the pattern — answering "Draft transaksi: ..." in
    text without ever calling propose_*, so the user sees a reply
    claiming a draft that does not exist. Observed against the real
    model; `test_history_shows_that_tools_were_used` guards it.

    Each card also says what it held and what became of it, which the
    history used to leave out entirely. Every card read the same: "a
    draft card appeared". So a confirmed purchase and an abandoned one
    looked alike, and when the next message mentioned a second expense
    the model proposed a batch holding both — re-offering money already
    in the ledger. Confirming that would have posted it twice, and no
    idempotency key would have caught it: a new draft is a new
    operation, which everywhere else is exactly what is wanted.
    """
    rendered: list[dict[str, Any]] = []
    drafts = drafts or {}

    for message in messages:
        if message.body:
            rendered.append({"role": message.role.value, "content": _with_quote(message)})
        elif message.draft_id:
            draft = drafts.get(message.draft_id)
            card = (
                f"{_draft_digest(draft)} — {_DRAFT_OUTCOME.get(draft.status, '')}".strip(" —")
                if draft is not None
                else "isinya tidak lagi tersedia"
            )
            rendered.append(
                {
                    "role": "assistant",
                    "content": (
                        f"[Aku memanggil tool propose_* dan kartu draft tampil: {card} "
                        "Draft hanya muncul lewat tool, bukan lewat teks.]"
                    ),
                }
            )

    return rendered


def _drafts_for(db: DbSession, messages: list[Message]) -> dict[uuid.UUID, Draft]:
    """The Draft rows behind the card turns, in one query."""
    ids = {m.draft_id for m in messages if m.draft_id}

    if not ids:
        return {}

    return {d.id: d for d in db.scalars(select(Draft).where(Draft.id.in_(ids))).all()}


#: How much of a quoted turn the model is shown. The context window is
#: 24,576 tokens for prompt *and* output, and a reply to a long answer
#: would otherwise re-send the whole thing. The opening line is what
#: identifies which message was meant.
QUOTE_CHARS = 160


def _with_quote(message: Message) -> str:
    """The turn's text, prefixed with what it was replying to.

    Rendered here rather than stored on the row, so the quote follows
    whatever the original message says now and there is one copy of the
    wording. It goes in the content because the OpenAI-compatible shape
    has nowhere else to put it — and without it the model has no way to
    know which of ten earlier answers a short "yang itu" refers to.
    """
    quoted = message.reply_to

    if quoted is None or not quoted.body:
        return message.body or ""

    excerpt = " ".join(quoted.body.split())

    if len(excerpt) > QUOTE_CHARS:
        excerpt = f"{excerpt[:QUOTE_CHARS].rstrip()}…"

    who = "kamu" if quoted.role is MessageRole.ASSISTANT else "aku"

    return f'[Membalas pesan {who}: "{excerpt}"]\n{message.body}'


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
    reply_to_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> TurnResult:
    """Process one message and return the finished turn.

    Drains :func:`run_turn_events`, so the streaming and non-streaming
    paths cannot drift apart - there is one implementation and two
    presentations of it.
    """
    result: TurnResult | None = None

    async for event in run_turn_events(
        db,
        user_id=user_id,
        adapter=adapter,
        body=body,
        reply_to_id=reply_to_id,
        conversation_id=conversation_id,
    ):
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
    reply_to_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Process one user message, yielding progress as it happens.

    Events: ``token`` for each content fragment, ``tool`` when one is
    called, ``draft`` when a card is raised, and finally ``done``
    carrying the TurnResult. The browser gets something to show within
    a second instead of a blank wait.
    """
    conversation = get_or_create_conversation(db, user_id, conversation_id)

    # Named from the opening message, before it is stored, so a thread
    # is recognisable in the list from its very first turn.
    name_if_unnamed(conversation, body)

    db.add(
        Message(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            body=body,
            # Checked by the caller: it is the one holding the HTTP
            # request and able to answer a bad id with a status code.
            reply_to_id=reply_to_id,
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

    # Same reasoning as the wallets, one layer down. Unshown, the model
    # picks whatever word the sentence used - "ongkos" one month,
    # "Transport" the next - and the breakdown ends up with two rows for
    # one thing that no rule in the schema could have merged.
    categories = known_expense_categories(db, user_id) + known_income_categories(db, user_id)

    prompt: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(now_local, user_timezone, wallets, categories),
        }
    ]
    history = recent_messages(db, conversation.id)
    prompt += _as_prompt(history, _drafts_for(db, history))

    drafts: list[Draft] = []
    #: A read tool's result the client can draw, if this turn produced
    #: one. Set per turn, not per message: it belongs to the answer.
    view: dict | None = None
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

            # A breakdown is worth drawing rather than reading out. The
            # card is built from the tool's own output, so it carries
            # the figures the model was given and not the ones it chose
            # to repeat. Last one wins: if a turn asks twice, the card
            # shows what the answer ended up being about.
            if call.name in DRAWABLE_TOOLS and "error" not in output:
                view = {"kind": DRAWABLE_TOOLS[call.name], "data": output}

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
        view=view,
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
    refusals: list[str] = []

    for call in result.tool_calls:
        output = dispatch(db, user_id, call.name, call.arguments)

        if call.name not in PROPOSE_TOOL_NAMES:
            continue

        if "error" in output:
            refusals.append(str(output["error"]))
        else:
            drafts.extend(_collect_drafts(db, user_id, output))

    if drafts:
        return (result.content.strip() or "Ini draftnya. Periksa dulu, lalu konfirmasi."), drafts

    # The tool said why it would not build the draft, in a sentence
    # already written for a person. Swallowing that and offering
    # "sebutkan nominal dan kantongnya" instead is advice about a
    # problem the user may not have - they were told to rephrase when
    # the real answer was that two of their wallets are called BCA.
    if refusals:
        return refusals[0], []

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
