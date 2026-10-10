"""Run the Indonesian chat benchmark against the real model.

The PRD gates the pilot on "≥90% draft pada benchmark minimal 100 pesan
Indonesia mempunyai nominal, akun, tanggal, dan jenis yang tepat sebelum
koreksi" (section 10), and on a p95 draft latency under ten seconds
(section 9). This measures both.

Not part of the test suite. It costs GPU time on a shared box and needs
a working `LLM_API_KEY`, so it is run deliberately:

    .venv/Scripts/python -m benchmarks.run
    .venv/Scripts/python -m benchmarks.run --tags amount date --repeat 2

Each case runs in its own fresh user with the same five wallets, so one
case cannot affect the next, and everything is deleted afterwards.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.corpus import ALL_CASES, Case  # noqa: E402

FIXTURE_WALLETS = [
    ("BCA", "bank", "bca", 5_000_000, None),
    ("Mandiri", "bank", "mandiri", 2_000_000, None),
    ("GoPay", "ewallet", "gopay", 200_000, None),
    ("Cash", "cash", "cash", 150_000, None),
    ("CC BCA", "credit_card", "cc", 0, 10_000_000),
]


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile.

    `int(n * 0.95) - 1` truncates, which on small samples lands below
    the median - a p95 under p50 is nonsense, and it would understate
    the figure the pilot gate is read from. Rounding up is the standard
    nearest-rank definition.
    """
    if not sorted_values:
        return 0.0

    import math

    rank = max(1, math.ceil(fraction * len(sorted_values)))

    return sorted_values[rank - 1]


@dataclass
class Outcome:
    case: Case
    seconds: float
    passed: bool
    failures: list[str]
    reply: str
    drafts: list[dict]
    error: str | None = None


def _expected_date(spec: str | None, today: date) -> date | None:
    if spec is None:
        return None
    if spec == "today":
        return today
    if spec == "yesterday":
        return today - timedelta(days=1)
    if spec.startswith("-"):
        return today - timedelta(days=int(spec[1:]))
    return date.fromisoformat(spec)


def _draft_date(payload: dict) -> date | None:
    raw = payload.get("occurred_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def check(case: Case, drafts: list[dict], today: date) -> list[str]:
    """Compare a turn's drafts against the case. Returns failure reasons."""
    if case.expect in {"none", "refuse"}:
        if drafts:
            kinds = ", ".join(d["kind"] for d in drafts)
            return [f"expected no draft, got {len(drafts)} ({kinds})"]
        return []

    if not drafts:
        return ["expected a draft, got none"]

    failures: list[str] = []
    first = drafts[0]
    payload = first.get("payload") or {}

    if case.kind is not None:
        actual = payload.get("type") or first.get("kind")
        if actual != case.kind:
            failures.append(f"jenis: expected {case.kind}, got {actual}")

    if case.amount is not None:
        actual = payload.get("amount") or payload.get("target_amount")
        if actual != case.amount:
            failures.append(f"nominal: expected {case.amount}, got {actual}")

    if case.account is not None:
        actual = payload.get("account_name") or payload.get("_from_name")
        if actual != case.account:
            failures.append(f"akun: expected {case.account}, got {actual}")

    if case.to_account is not None:
        actual = payload.get("_to_name")
        if actual != case.to_account:
            failures.append(f"akun tujuan: expected {case.to_account}, got {actual}")

    if case.fee is not None and payload.get("fee") != case.fee:
        failures.append(f"biaya: expected {case.fee}, got {payload.get('fee')}")

    expected_date = _expected_date(case.date, today)
    if expected_date is not None:
        actual_date = _draft_date(payload) or today
        if actual_date != expected_date:
            failures.append(f"tanggal: expected {expected_date}, got {actual_date}")

    return failures


def run_case(app_module, adapter, case: Case, today: date) -> Outcome:
    """Run one case against a throwaway user."""
    from fastapi.testclient import TestClient

    from app.api import routes_chat

    routes_chat.set_adapter(adapter)
    email = f"bench-{uuid.uuid4().hex[:10]}@example.com"

    # Timed around the chat turn alone. The PRD's target is the AI draft
    # response, so including registration and five wallet creations
    # would quietly inflate every figure.
    started = time.monotonic()

    try:
        with TestClient(app_module.app) as client:
            client.post(
                "/auth/register", json={"email": email, "password": "benchmark-pass-123"}
            ).raise_for_status()

            names: dict[str, str] = {}

            for name, kind, alias, balance, limit in FIXTURE_WALLETS:
                body = {
                    "name": name,
                    "type": kind,
                    "alias": alias,
                    "opening_balance": balance,
                }
                if limit:
                    body["credit_limit"] = limit
                created = client.post("/accounts", json=body)
                created.raise_for_status()
                names[created.json()["id"]] = name

            started = time.monotonic()
            response = client.post("/chat/messages", json={"body": case.message})
            elapsed = time.monotonic() - started

            if response.status_code != 200:
                return Outcome(
                    case,
                    time.monotonic() - started,
                    False,
                    [f"HTTP {response.status_code}"],
                    "",
                    [],
                    error=response.text[:200],
                )

            turn = response.json()
            drafts = turn["drafts"]

            # Resolve wallet ids to names so the corpus can name wallets.
            for draft in drafts:
                payload = draft.get("payload") or {}
                payload["_from_name"] = names.get(payload.get("from_account_id"))
                payload["_to_name"] = names.get(payload.get("to_account_id")) or names.get(
                    payload.get("card_account_id")
                )

            failures = check(case, drafts, today)

            return Outcome(case, elapsed, not failures, failures, turn["reply"], drafts)
    except Exception as exc:  # noqa: BLE001 - one bad case must not end the run
        return Outcome(
            case, time.monotonic() - started, False, ["exception"], "", [], error=str(exc)[:200]
        )
    finally:
        routes_chat.set_adapter(None)


def cleanup(engine) -> int:
    """Delete every benchmark user and everything hanging off them."""
    from sqlalchemy.orm import Session

    from app.models import (
        Account,
        AiRequestLog,
        Allocation,
        AuditEvent,
        Budget,
        Conversation,
        Draft,
        Entry,
        Goal,
        LoginAttempt,
        Message,
        Transaction,
        User,
    )
    from app.models import (
        Session as SessionRow,
    )

    with Session(bind=engine) as db:
        users = db.query(User).filter(User.email.like("bench-%@example.com")).all()
        ids = [u.id for u in users]

        if not ids:
            return 0

        for model in (
            AiRequestLog,
            Message,
            Conversation,
            AuditEvent,
            Entry,
            Draft,
            Transaction,
            Budget,
            Allocation,
            Goal,
            Account,
            SessionRow,
        ):
            db.query(model).filter(model.user_id.in_(ids)).delete(synchronize_session=False)

        db.query(LoginAttempt).filter(LoginAttempt.email.in_([u.email for u in users])).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()

        return len(ids)


def report(outcomes: list[Outcome]) -> int:
    """Print the summary. Returns a process exit code."""
    total = len(outcomes)
    passed = sum(1 for o in outcomes if o.passed)
    rate = passed / total * 100 if total else 0.0

    latencies = sorted(o.seconds for o in outcomes)
    p50 = statistics.median(latencies) if latencies else 0
    p95 = _percentile(latencies, 0.95)

    failures = [o for o in outcomes if not o.passed]

    if failures:
        print("\nGAGAL\n" + "=" * 72)
        for outcome in failures:
            print(f"\n[{outcome.case.id}] {outcome.case.message}")
            print(f"   probes : {outcome.case.probes}")
            for reason in outcome.failures:
                print(f"   -> {reason}")
            if outcome.error:
                print(f"   error  : {outcome.error}")
            if outcome.reply:
                print(f"   reply  : {outcome.reply[:120]}")

    # Per-field, which is how the PRD states its gate.
    field_failures: dict[str, int] = {}
    for outcome in failures:
        for reason in outcome.failures:
            field = reason.split(":")[0]
            field_failures[field] = field_failures.get(field, 0) + 1

    print("\nRINGKASAN\n" + "=" * 72)
    print(f"  kasus        : {total}")
    print(f"  lulus        : {passed} ({rate:.1f}%)")
    print(f"  gagal        : {len(failures)}")
    print(f"  latensi p50  : {p50:.2f}s")
    print(f"  latensi p95  : {p95:.2f}s   (target PRD <= 10s)")

    if field_failures:
        print("\n  kegagalan per field:")
        for field, count in sorted(field_failures.items(), key=lambda kv: -kv[1]):
            print(f"    {field:16} {count}")

    by_tag: dict[str, list[bool]] = {}
    for outcome in outcomes:
        for tag in outcome.case.tags or ("untagged",):
            by_tag.setdefault(tag, []).append(outcome.passed)

    print("\n  per tag:")
    for tag, results in sorted(by_tag.items()):
        ok = sum(results)
        print(f"    {tag:12} {ok}/{len(results)}")

    gate_accuracy = rate >= 90
    gate_latency = p95 <= 10

    print("\n  gerbang pilot:")
    print(f"    akurasi >= 90%  : {'LULUS' if gate_accuracy else 'BELUM'} ({rate:.1f}%)")
    print(f"    p95 <= 10 detik : {'LULUS' if gate_latency else 'BELUM'} ({p95:.2f}s)")

    return 0 if (gate_accuracy and gate_latency) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tags", nargs="*", help="Only cases carrying one of these tags")
    parser.add_argument("--ids", nargs="*", help="Only these case ids")
    parser.add_argument("--limit", type=int, help="Stop after this many cases")
    parser.add_argument(
        "--fake", action="store_true", help="Use the scripted adapter; checks the harness itself"
    )
    args = parser.parse_args()

    cases = list(ALL_CASES)

    if args.tags:
        wanted = set(args.tags)
        cases = [c for c in cases if wanted & set(c.tags)]
    if args.ids:
        wanted = set(args.ids)
        cases = [c for c in cases if c.id in wanted]
    if args.limit:
        cases = cases[: args.limit]

    if not cases:
        print("Tidak ada kasus yang cocok.")
        return 1

    import app.main as app_module
    from app.db import get_engine

    if args.fake:
        from app.services.ai.fake import FakeAdapter

        adapter = FakeAdapter()
    else:
        from app.services.ai.openai_compat import OpenAiCompatAdapter

        if not os.environ.get("LLM_API_KEY"):
            print("LLM_API_KEY belum diatur.")
            return 1

        adapter = OpenAiCompatAdapter(
            base_url=os.environ["LLM_BASE_URL"],
            api_key=os.environ["LLM_API_KEY"],
            model=os.environ.get("LLM_MODEL", "qwen3.5-9b"),
        )

    today = datetime.now(timezone.utc).astimezone().date()
    outcomes: list[Outcome] = []

    print(f"Menjalankan {len(cases)} kasus terhadap {os.environ.get('LLM_MODEL', 'fake')}…\n")

    try:
        for index, case in enumerate(cases, 1):
            outcome = run_case(app_module, adapter, case, today)
            outcomes.append(outcome)
            mark = "ok  " if outcome.passed else "GAGAL"
            print(
                f"  {index:3}/{len(cases)}  {mark} {case.id}  {outcome.seconds:5.1f}s  "
                f"{case.message[:52]}"
            )
    finally:
        removed = cleanup(get_engine())
        print(f"\n  dibersihkan: {removed} pengguna benchmark")

    return report(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
