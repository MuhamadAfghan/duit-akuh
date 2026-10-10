"""Passenger entry point for the FastAPI backend on cPanel.

cPanel's Python Selector runs apps through Phusion Passenger, which
speaks WSGI. FastAPI is ASGI, so the app is wrapped rather than served
by uvicorn. Passenger looks for a module-level ``application``.

Two things are deliberate:

* The environment is read from ``shared/.env`` before ``app`` is
  imported. ``app.config`` calls ``_require("DATABASE_URL")`` at import
  time, so anything missing has to be in place first, and keeping the
  values in a file outside the release means a deploy never rewrites
  secrets (AC21: the LLM key and Cloudflare tokens live only here).
* ``a2wsgi`` streams. The chat endpoint returns NDJSON a line at a time,
  and a bridge that buffered would turn a streamed reply into a single
  blob at the end.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# The release directory is the import root, so `app.main` resolves.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _load_env(path: Path) -> None:
    """Minimal .env reader.

    Avoids a python-dotenv dependency for ~15 lines, and uses
    ``setdefault`` so a value already exported by Passenger's own
    env-vars config wins over the file.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_load_env(_HERE / ".env")

from a2wsgi import ASGIMiddleware  # noqa: E402  (needs the env loaded first)

from app.main import app as _asgi_app  # noqa: E402

application = ASGIMiddleware(_asgi_app)
