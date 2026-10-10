"""CSV export (PRD section 9, AC10)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..domain.periods import PERIOD_KEYWORDS, PeriodError, resolve_period
from ..services.export import export_transactions
from .deps import CurrentUser, DbSessionDep

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/transactions.csv")
def transactions_csv(
    user: CurrentUser,
    db: DbSessionDep,
    period: Annotated[str, Query(description=f"One of: {', '.join(PERIOD_KEYWORDS)}")] = "semua",
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> StreamingResponse:
    """Export transactions as CSV, honouring the same period filters as the UI.

    AC10 requires the export to match the filter the user applied, so
    this takes the same arguments as the reports rather than always
    dumping everything.
    """
    try:
        resolved = resolve_period(
            period,
            now=datetime.now(timezone.utc),
            timezone_name=user.timezone,
            start=start,
            end=end,
        )
    except PeriodError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_period", "message": str(exc)}
        ) from exc

    # From the period's own label, not its bounds: an unbounded "semua"
    # would otherwise produce transaksi-1970-01-01-2200-01-01.csv.
    slug = re.sub(r"[^a-z0-9]+", "-", resolved.label.lower()).strip("-")
    filename = f"transaksi-{slug}.csv"

    return StreamingResponse(
        export_transactions(db, user.id, resolved),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
