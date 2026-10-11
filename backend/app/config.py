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

    # --- Email. Transactional only: password reset and security notices.
    # These carry defaults because mail is optional: the app runs without
    # it, and a test that cares about one unrelated field should not have
    # to name every mail setting to build a Settings.
    smtp_host: str | None = None
    smtp_port: int = 465
    #: True for implicit TLS (port 465), False for STARTTLS (587).
    smtp_ssl: bool = True
    smtp_user: str | None = None
    mail_from: str | None = None
    mail_from_name: str = "lega"
    #: Origin the PWA is served from, used to build links inside emails.
    app_base_url: str = "http://localhost:3033"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def email_configured(self) -> bool:
        """Whether a password-reset email could be sent at all.

        Checked before offering the flow: a reset page that silently
        sends nothing is worse than one that says email is unavailable.
        """
        return bool(self.smtp_host and self.smtp_user and self.mail_from)

    def require_smtp_password(self) -> str:
        """Read the mailbox password at call time, never at import.

        Same reasoning as the LLM key: it stays out of any object that
        could end up in a log line or a traceback's frame locals.
        """
        return _require("SMTP_PASSWORD")

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
        smtp_host=os.environ.get("SMTP_HOST"),
        smtp_port=int(os.environ.get("SMTP_PORT", "465")),
        smtp_ssl=os.environ.get("SMTP_SSL", "true").strip().lower() not in {"0", "false", "no"},
        smtp_user=os.environ.get("SMTP_USER"),
        mail_from=os.environ.get("MAIL_FROM"),
        mail_from_name=os.environ.get("MAIL_FROM_NAME", "lega"),
        app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:3033").rstrip("/"),
    )
