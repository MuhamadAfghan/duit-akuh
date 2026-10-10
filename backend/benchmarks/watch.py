"""Watch a benchmark run in progress, from another terminal.

    .venv/Scripts/python -m benchmarks.watch

Reads the database rather than the runner's output, so it works even
for a run already under way — including one whose stdout is buffered
into a file and therefore showing nothing yet.

Progress is inferred from the benchmark users the runner creates, one
per case, and from `ai_request_logs`. Press Ctrl+C to stop watching;
the run itself is untouched.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.models import AiRequestLog, User  # noqa: E402

TOTAL_CASES = 103
POLL_SECONDS = 3


def snapshot(session) -> tuple[int, int, float | None, int]:
    cases = (
        session.scalar(select(func.count()).select_from(User).where(User.email.like("bench-%")))
        or 0
    )

    calls = session.scalar(select(func.count()).select_from(AiRequestLog)) or 0

    recent = datetime.now(timezone.utc) - timedelta(minutes=2)
    latency = session.scalar(
        select(func.avg(AiRequestLog.latency_ms)).where(AiRequestLog.created_at > recent)
    )

    errors = (
        session.scalar(
            select(func.count()).select_from(AiRequestLog).where(AiRequestLog.status == "error")
        )
        or 0
    )

    return int(cases), int(calls), float(latency) if latency else None, int(errors)


def main() -> int:
    from sqlalchemy.orm import Session

    engine = get_engine()
    started = time.monotonic()
    previous = 0
    # Where the run already was when watching began. The rate has to be
    # measured from progress seen since then, not from the absolute
    # count - attaching to a run that is already 75 cases in would
    # otherwise compute an enormous rate and report no time remaining.
    baseline: int | None = None

    print(f"Memantau benchmark ({TOTAL_CASES} kasus). Ctrl+C untuk berhenti.\n")

    try:
        while True:
            with Session(bind=engine) as session:
                cases, calls, latency, errors = snapshot(session)

            elapsed = time.monotonic() - started
            done = min(cases, TOTAL_CASES)
            bar_width = 30
            filled = int(bar_width * done / TOTAL_CASES)
            bar = "#" * filled + "." * (bar_width - filled)

            if baseline is None:
                baseline = done

            observed = done - baseline
            rate = observed / elapsed if elapsed > 0 and observed else 0
            remaining = (TOTAL_CASES - done) / rate if rate > 0 else 0

            latency_text = f"{latency / 1000:.1f}s" if latency else "-"
            eta = f"{remaining / 60:.0f}m" if remaining else "-"

            line = (
                f"\r  [{bar}] {done:3}/{TOTAL_CASES}  "
                f"panggilan AI {calls:4}  "
                f"latensi {latency_text:>6}  "
                f"error {errors:2}  "
                f"sisa ~{eta:>4}"
            )
            # \r and an explicit flush: one line that rewrites itself,
            # which needs no scrollback and shows motion immediately.
            sys.stdout.write(line)
            sys.stdout.flush()

            if cases == 0 and previous == 0 and elapsed > 30:
                sys.stdout.write("\n  (belum ada kasus — runner sudah jalan?)\n")
                sys.stdout.flush()
                return 1

            # The runner deletes its users at the end, so a drop back to
            # zero after real progress means it finished.
            if previous > 0 and cases == 0:
                sys.stdout.write("\n\n  Selesai — runner sudah membersihkan datanya.\n")
                return 0

            previous = cases
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        sys.stdout.write("\n  Berhenti memantau. Benchmark tetap berjalan.\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
