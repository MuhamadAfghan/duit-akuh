"""WSGI entry point for the FastAPI backend on cPanel.

cPanel's Python Selector runs the app under LiteSpeed's ``lswsgi``, which
speaks WSGI. FastAPI is ASGI, so the app is bridged rather than served by
uvicorn. The runner looks for a module-level ``application``.

Three things here are load-bearing, and each one cost a debugging session:

* **The bridge is built lazily, on the first request.** ``a2wsgi`` starts
  an event loop on a background thread when the middleware is
  constructed. ``lswsgi`` imports this module in a master process and
  then *forks* workers, and threads do not survive ``fork()`` — so a
  bridge built at import time leaves every worker waiting on a queue
  nobody is servicing, and requests hang until the gateway times out
  with no error in the log. Building it inside ``application()`` means it
  is created in the worker that will use it.
* **The environment is read before ``app`` is imported.** ``app.config``
  calls ``_require("DATABASE_URL")`` at import, so the values have to be
  in place first. Keeping them in ``shared/.env`` means a deploy never
  rewrites secrets (AC21: the LLM key and Cloudflare tokens live only
  there).
* **a2wsgi streams.** The chat endpoint returns NDJSON a line at a time,
  and a bridge that buffered would turn a streamed reply into one blob at
  the end.
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
    ``setdefault`` so a value already exported by the selector's own
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

_bridge = None


def application(environ, start_response):
    """WSGI callable. Builds the ASGI bridge on first use — see above."""
    global _bridge

    if _bridge is None:
        from a2wsgi import ASGIMiddleware
        from app.main import app as asgi_app

        _bridge = ASGIMiddleware(asgi_app)

    return _bridge(environ, start_response)
