"""Rate limiting and queueing in front of the AI service (PRD section 13).

The server allows 16 parallel requests shared with other applications
and has no SLA, so these limits are what stop one user — or this
product — from starving it. What is worth proving is that each limit
refuses in a way the caller can act on, and that none of them block long
enough to hit Cloudflare's 100-second deadline.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.ai.limits import (
    RATE_LIMIT,
    RATE_WINDOW,
    AiBusy,
    AiGate,
    AiRateLimited,
    AlreadyProcessing,
    check_rate_limit,
    recent_request_count,
)

from .conftest import requires_db

pytestmark_async = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ----------------------------------------------------------------------
# The gate
# ----------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_slot_is_released_when_the_turn_finishes():
    gate = AiGate(max_concurrency=1, timeout=0.1)
    user = uuid.uuid4()

    async with gate.slot(user):
        assert gate.available == 0

    assert gate.available == 1
    assert not gate.is_processing(user)


@pytest.mark.anyio
async def test_a_slot_is_released_even_when_the_turn_raises():
    """A failed turn must not leak a slot, or the gate closes for good."""
    gate = AiGate(max_concurrency=1, timeout=0.1)
    user = uuid.uuid4()

    with pytest.raises(RuntimeError):
        async with gate.slot(user):
            raise RuntimeError("model exploded")

    assert gate.available == 1
    assert not gate.is_processing(user)


@pytest.mark.anyio
async def test_a_second_turn_from_the_same_user_is_refused_not_queued():
    """A double tap is one question twice, not two questions."""
    gate = AiGate(max_concurrency=4, timeout=0.1)
    user = uuid.uuid4()

    async with gate.slot(user):
        with pytest.raises(AlreadyProcessing):
            async with gate.slot(user):
                pass


@pytest.mark.anyio
async def test_different_users_run_concurrently():
    gate = AiGate(max_concurrency=2, timeout=0.5)
    a, b = uuid.uuid4(), uuid.uuid4()

    async with gate.slot(a), gate.slot(b):
        assert gate.available == 0


@pytest.mark.anyio
async def test_waiting_past_the_timeout_reports_busy_rather_than_hanging():
    """Hanging would mean Cloudflare 524s, which the user cannot read."""
    gate = AiGate(max_concurrency=1, timeout=0.05)
    holder, waiter = uuid.uuid4(), uuid.uuid4()

    async with gate.slot(holder):
        with pytest.raises(AiBusy) as excinfo:
            async with gate.slot(waiter):
                pass

    assert "penuh" in str(excinfo.value)
    # And the refused waiter did not leave itself marked in flight.
    assert not gate.is_processing(waiter)


@pytest.mark.anyio
async def test_a_waiter_gets_the_slot_once_it_frees():
    gate = AiGate(max_concurrency=1, timeout=2.0)
    a, b = uuid.uuid4(), uuid.uuid4()
    order = []

    async def first():
        async with gate.slot(a):
            order.append("a-start")
            await asyncio.sleep(0.05)
            order.append("a-end")

    async def second():
        await asyncio.sleep(0.01)
        async with gate.slot(b):
            order.append("b-start")

    await asyncio.gather(first(), second())

    assert order == ["a-start", "a-end", "b-start"], "b waited rather than being refused"


@pytest.mark.anyio
async def test_concurrency_never_exceeds_the_cap():
    gate = AiGate(max_concurrency=3, timeout=5.0)
    peak = 0
    current = 0

    async def turn():
        nonlocal peak, current
        async with gate.slot(uuid.uuid4()):
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.02)
            current -= 1

    await asyncio.gather(*(turn() for _ in range(12)))

    assert peak == 3
    assert gate.available == 3


# ----------------------------------------------------------------------
# The rate limit
# ----------------------------------------------------------------------


@requires_db
@pytest.mark.integration
def test_the_rate_limit_counts_only_recent_requests(session, user):
    from app.models import AiRequestLog

    now = datetime.now(timezone.utc)

    # Old enough to have fallen out of the window.
    for _ in range(RATE_LIMIT + 5):
        session.add(
            AiRequestLog(
                user_id=user.id,
                kind="chat",
                model="fake",
                status="ok",
                created_at=now - RATE_WINDOW - timedelta(seconds=10),
            )
        )
    session.flush()

    assert recent_request_count(session, user.id, now=now) == 0
    check_rate_limit(session, user.id, now=now)


@requires_db
@pytest.mark.integration
def test_too_many_recent_requests_are_refused(session, user):
    from app.models import AiRequestLog

    now = datetime.now(timezone.utc)

    for _ in range(RATE_LIMIT):
        session.add(
            AiRequestLog(
                user_id=user.id,
                kind="chat",
                model="fake",
                status="ok",
                created_at=now - timedelta(seconds=5),
            )
        )
    session.flush()

    with pytest.raises(AiRateLimited):
        check_rate_limit(session, user.id, now=now)


@requires_db
@pytest.mark.integration
def test_the_rate_limit_is_per_user(session, user, other_user):
    from app.models import AiRequestLog

    now = datetime.now(timezone.utc)

    for _ in range(RATE_LIMIT):
        session.add(
            AiRequestLog(
                user_id=user.id,
                kind="chat",
                model="fake",
                status="ok",
                created_at=now - timedelta(seconds=5),
            )
        )
    session.flush()

    with pytest.raises(AiRateLimited):
        check_rate_limit(session, user.id, now=now)

    # The other user is unaffected.
    check_rate_limit(session, other_user.id, now=now)


@requires_db
@pytest.mark.integration
def test_failed_requests_count_too(session, user):
    """Otherwise a loop of failures is an unlimited way to hammer the GPU."""
    from app.models import AiRequestLog

    now = datetime.now(timezone.utc)

    for _ in range(RATE_LIMIT):
        session.add(
            AiRequestLog(
                user_id=user.id,
                kind="chat",
                model="",
                status="error",
                error="boom",
                created_at=now - timedelta(seconds=5),
            )
        )
    session.flush()

    with pytest.raises(AiRateLimited):
        check_rate_limit(session, user.id, now=now)
