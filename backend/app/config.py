"""Runtime configuration, read from the environment.

Secrets never have defaults here. The PRD requires the LLM key and the
Cloudflare Access tokens to live only on the server, so a missing value
must fail loudly rather than fall back to something that looks like it
works.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is required but not set. See backend/.env.example."
        )
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str
    #: Where the PWA is served from, for CORS.
    cors_origins: tuple[str, ...]

    # --- AI service (PRD section 13). Optional until the adapter lands. ---
    llm_base_url: str | None
    llm_model: str
    stt_base_url: str | None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def require_llm_api_key(self) -> str:
        """Read the LLM key at call time, never at import.

        Keeps it out of any object that might be logged or serialised.
        """
        return _require("LLM_API_KEY")

    def require_stt_credentials(self) -> tuple[str, str]:
        """Cloudflare Access service token for the speech endpoint."""
        return _require("CF_ACCESS_CLIENT_ID"), _require("CF_ACCESS_CLIENT_SECRET")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3033")

    return Settings(
        database_url=_require("DATABASE_URL"),
        app_env=os.environ.get("APP_ENV", "development"),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        llm_base_url=os.environ.get("LLM_BASE_URL"),
        llm_model=os.environ.get("LLM_MODEL", "qwen3.5-9b"),
        stt_base_url=os.environ.get("STT_BASE_URL"),
    )
