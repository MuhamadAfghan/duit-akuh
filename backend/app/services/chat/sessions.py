"""Named chat threads (PRD FR14, FR15).

One conversation per user became several. What the single thread
protected — that there is always a current one, and that the user never
has to pick before they can type — is kept here instead of by a unique
constraint: :func:`active_conversation` resolves the newest unarchived
thread and creates one when there is none.

Nothing in here touches money. A conversation owns messages, messages
point at drafts, and drafts own the figures; archiving or renaming a
thread changes none of that, and a posted transaction outlives every
one of them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ...models import Conversation, Message

#: Long enough for a sentence worth recognising, short enough to fit a
#: phone header without a second line.
TITLE_CHARS = 48

#: What the list shows under each title.
PREVIEW_CHARS = 90


class ConversationNotFound(Exception):
    """Missing, archived out of reach, or someone else's — all the same
    answer, because telling them apart confirms which ids exist."""


@dataclass(frozen=True)
class ConversationRow:
    """A conversation plus what the list needs to draw it."""

    conversation: Conversation
    preview: str | None
    last_at: datetime | None


# ----------------------------------------------------------------------


def _clip(text: str, limit: int) -> str:
    flat = " ".join((text or "").split())

    return f"{flat[:limit].rstrip()}…" if len(flat) > limit else flat


def _last_seq():
    """Each conversation's newest message, as a correlated subquery.

    Ordering by this rather than by a stored `last_message_at` column:
    `seq` is already the thread's ordering key, globally unique and
    monotonic, so there is no second value to keep in step and nothing
    to drift if a write path forgets to touch it.
    """
    return (
        select(func.max(Message.seq))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )


def owned(db: DbSession, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)

    if conversation is None or conversation.user_id != user_id:
        raise ConversationNotFound

    return conversation


def active_conversation(
    db: DbSession, user_id: uuid.UUID, conversation_id: uuid.UUID | None = None
) -> Conversation:
    """The thread a turn belongs to.

    Named explicitly, or else the most recently used unarchived one, or
    else a new one. An archived thread *can* still be named explicitly:
    archiving hides it from the list, it does not seal it, and a user
    who opened one to read it should be able to answer in it.
    """
    if conversation_id is not None:
        return owned(db, user_id, conversation_id)

    conversation = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.is_archived.is_(False))
        .order_by(func.coalesce(_last_seq(), 0).desc(), Conversation.created_at.desc())
        .limit(1)
    ).first()

    if conversation is None:
        conversation = create_conversation(db, user_id)

    return conversation


def create_conversation(db: DbSession, user_id: uuid.UUID) -> Conversation:
    """A new, empty thread.

    Untitled on purpose: :func:`name_if_unnamed` fills it from the first
    message, so the list never carries a row of "Obrolan baru".
    """
    conversation = Conversation(id=uuid.uuid4(), user_id=user_id)
    db.add(conversation)
    db.flush()

    return conversation


def name_if_unnamed(conversation: Conversation, body: str) -> None:
    """Title a thread from its opening message.

    Not asked of the model. A title is worth one round trip to nobody,
    and the first thing a person typed is what they will recognise the
    thread by — a tidier summary of it is a different sentence from the
    one they remember writing.
    """
    if conversation.title:
        return

    title = _clip(body, TITLE_CHARS)

    if title:
        conversation.title = title


def rename(db: DbSession, conversation: Conversation, title: str) -> Conversation:
    cleaned = " ".join((title or "").split())[: TITLE_CHARS * 2]

    if not cleaned:
        raise ValueError("Nama tidak boleh kosong")

    conversation.title = cleaned
    db.flush()

    return conversation


def set_flags(
    db: DbSession,
    conversation: Conversation,
    *,
    is_pinned: bool | None = None,
    is_archived: bool | None = None,
) -> Conversation:
    if is_pinned is not None:
        conversation.is_pinned = is_pinned

    if is_archived is not None:
        conversation.is_archived = is_archived

        # A pin is a claim on the top of the list, and an archived
        # thread is not in the list. Leaving both set means unarchiving
        # later silently promotes it.
        if is_archived:
            conversation.is_pinned = False

    db.flush()

    return conversation


def list_conversations(
    db: DbSession, user_id: uuid.UUID, *, include_archived: bool = False
) -> list[ConversationRow]:
    """Every thread, newest activity first, pinned ones above.

    Two queries, not one per row: the previews come from a single join
    against each conversation's highest `seq`, which is portable across
    both engines in a way PostgreSQL's DISTINCT ON would not be.
    """
    query = select(Conversation).where(Conversation.user_id == user_id)

    if not include_archived:
        query = query.where(Conversation.is_archived.is_(False))

    conversations = list(
        db.scalars(
            query.order_by(
                Conversation.is_pinned.desc(),
                func.coalesce(_last_seq(), 0).desc(),
                Conversation.created_at.desc(),
            )
        ).all()
    )

    if not conversations:
        return []

    ids = [c.id for c in conversations]

    newest = (
        select(Message.conversation_id, func.max(Message.seq).label("seq"))
        .where(Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
        .subquery()
    )

    tails = {
        message.conversation_id: message
        for message in db.scalars(
            select(Message).join(
                newest,
                (Message.conversation_id == newest.c.conversation_id)
                & (Message.seq == newest.c.seq),
            )
        ).all()
    }

    rows = []

    for conversation in conversations:
        tail = tails.get(conversation.id)

        rows.append(
            ConversationRow(
                conversation=conversation,
                # A card-only turn has no body; the thread is not empty,
                # it simply has nothing to quote, so the preview is
                # omitted rather than faked.
                preview=_clip(tail.body, PREVIEW_CHARS) if tail and tail.body else None,
                last_at=tail.created_at if tail else None,
            )
        )

    return rows
