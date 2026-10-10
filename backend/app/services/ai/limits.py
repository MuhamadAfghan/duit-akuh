"""Rate limiting and queueing for the AI service (PRD section 13).

`lumi-ai` allows 16 parallel requests **shared with other applications
on the same box**, and has no SLA. Three limits sit in front of it, each
answering a different failure:

* **Per-user rate limit** — one person cannot spend everyone's budget.
  Counted from ``ai_request_logs``, which is already written for every
  call, so this needs no extra table and works across worker processes.
* **Per-user single flight** — a second turn while the first is still
  running is a double-tap, not a second question. It is refused rather
  than queued.
* **Global concurrency** — a cap well below 16, so the product never
  starves the other services sharing the GPU.

A waiter that cannot get a slot in time is told the service is busy.
That matters because Cloudflare drops a request whose response has not
started within 100 seconds: waiting longer than that produces a 524 the
user cannot interpret, instead of a sentence they can.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ...models import AiRequestLog

#: Messages one user may send in the window. Generous for a person,
#: ineffective as a way to monopolise the GPU.
RATE_LIMIT = 20
RATE_WINDOW = timedelta(minutes=1)

#: Simultaneous calls this application will make. Deliberately well under
#: the server's 16: the rest belongs to the other services on the box.
MAX_CONCURRENCY = 6

#: How long a request will wait for a slot. Comfortably inside
#: Cloudflare's 100s, leaving room for the generation itself.
QUEUE_TIMEOUT_SECONDS = 20.0


class AiBusy(Exception):
    """No slot became free in time."""

    code = "ai_busy"


class AiRateLimited(Exception):
    """This user has made too many requests recently."""

    code = "ai_rate_limited"


class AlreadyProcessing(Exception):
    """This user already has a turn in flight."""

    code = "already_processing"


def recent_request_count(db: DbSession, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
    """AI calls this user made inside the rate window."""
    now = now or datetime.now(timezone.utc)

    return (
        db.scalar(
            select(func.count())
            .select_from(AiRequestLog)
            .where(
                AiRequestLog.user_id == user_id,
                AiRequestLog.created_at > now - RATE_WINDOW,
            )
        )
        or 0
    )


def check_rate_limit(db: DbSession, user_id: uuid.UUID, *, now: datetime | None = None) -> None:
    """Raise if the user is over their allowance.

    Counts rows already written rather than keeping a counter in memory,
    so the limit holds across worker processes and survives a restart.
    """
    if recent_request_count(db, user_id, now=now) >= RATE_LIMIT:
        raise AiRateLimited(
            f"Terlalu banyak permintaan. Coba lagi dalam {int(RATE_WINDOW.total_seconds())} detik."
        )


class AiGate:
    """Bounds how many AI calls are in flight, globally and per user.

    Per-process: with several uvicorn workers each gets its own gate, so
    `MAX_CONCURRENCY` is a per-worker figure. That is fine while the
    pilot runs one worker; a shared counter would need Redis, and the
    rate limit above already caps the damage either way.
    """

    def __init__(
        self, *, max_concurrency: int = MAX_CONCURRENCY, timeout: float = QUEUE_TIMEOUT_SECONDS
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._timeout = timeout
        self._in_flight: set[uuid.UUID] = set()
        self._max = max_concurrency

    @property
    def available(self) -> int:
        """Free slots right now, for a waiting indicator."""
        return self._semaphore._value  # noqa: SLF001 - no public accessor exists

    def is_processing(self, user_id: uuid.UUID) -> bool:
        return user_id in self._in_flight

    @asynccontextmanager
    async def slot(self, user_id: uuid.UUID):
        """Hold a slot for one user turn.

        Refuses a second concurrent turn from the same user outright:
        queueing it would mean the double-tap eventually runs twice.
        """
        if user_id in self._in_flight:
            raise AlreadyProcessing("Pesan sebelumnya masih diproses.")

        self._in_flight.add(user_id)

        try:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=self._timeout)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise AiBusy(
                    "Layanan AI sedang penuh. Coba lagi sebentar lagi, "
                    "atau catat manual lewat halaman Data."
                ) from exc

            try:
                yield
            finally:
                self._semaphore.release()
        finally:
            self._in_flight.discard(user_id)


#: Process-wide gate. Replaced in tests.
gate = AiGate()
