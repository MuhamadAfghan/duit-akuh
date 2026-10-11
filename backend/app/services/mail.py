"""Sending transactional email.

Only two messages are ever sent, both about the account itself: a reset
link and a notice that the password changed. Templates and subjects
live in :mod:`app.emails`; this module is the transport and nothing
else.

Two things are deliberate:

* **Both parts go out.** A multipart/alternative message carries the
  plain-text body as well as the HTML one. Some clients render only the
  text part, and a message with no text alternative scores worse with
  spam filters — which for a password-reset mail is the difference
  between a working account and a stuck one.
* **A failure to send is not a failure of the request.** The caller
  hands this to a background task: whether the mail server is slow or
  down must not change what the API answers, because the answer is the
  same for addresses that have no account at all.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from ..config import get_settings
from ..emails import Email

log = logging.getLogger(__name__)


class MailNotConfigured(RuntimeError):
    """No SMTP host, user, or from-address is set."""


def build_message(*, to: str, email: Email, sender: str, sender_name: str) -> EmailMessage:
    """Assemble the MIME message, without sending it."""
    message = EmailMessage()
    message["Subject"] = email.subject
    message["From"] = formataddr((sender_name, sender))
    message["To"] = to
    # Transactional, and unwanted in anybody's Promotions tab or
    # auto-reply loop.
    message["Auto-Submitted"] = "auto-generated"

    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")

    return message


class SmtpMailer:
    """Sends through the mailbox configured in the environment."""

    def send(self, *, to: str, email: Email) -> None:
        settings = get_settings()

        if not settings.email_configured:
            raise MailNotConfigured(
                "SMTP_HOST, SMTP_USER dan MAIL_FROM harus diisi. Lihat backend/.env.example."
            )

        message = build_message(
            to=to,
            email=email,
            sender=settings.mail_from,
            sender_name=settings.mail_from_name,
        )

        password = settings.require_smtp_password()

        # Port 465 is implicit TLS: the connection is encrypted before
        # anything is said. 587 starts in the clear and upgrades, so the
        # STARTTLS call is mandatory rather than optional there.
        if settings.smtp_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.login(settings.smtp_user, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                smtp.login(settings.smtp_user, password)
                smtp.send_message(message)


class FakeMailer:
    """Collects messages instead of sending them.

    Used by tests, and as the fallback when no mailbox is configured so
    a developer can exercise the reset flow without credentials. The
    recorded subjects are what tests assert on; bodies are kept too, but
    nothing here is ever written to a log.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, Email]] = []

    def send(self, *, to: str, email: Email) -> None:
        self.sent.append((to, email))


#: Swapped in tests, exactly as ``services/ai`` swaps its adapter.
_mailer: SmtpMailer | FakeMailer | None = None


def get_mailer() -> SmtpMailer | FakeMailer:
    global _mailer

    if _mailer is None:
        _mailer = SmtpMailer() if get_settings().email_configured else FakeMailer()

    return _mailer


def set_mailer(mailer: SmtpMailer | FakeMailer | None) -> None:
    """Replace the process-wide mailer. ``None`` restores the default."""
    global _mailer
    _mailer = mailer


def send_quietly(*, to: str, email: Email) -> None:
    """Send, and swallow anything that goes wrong.

    This is what a background task calls. The request has already been
    answered by the time it runs, so raising would only produce an
    unhandled exception in a worker; the log line is the useful part.
    The address is logged because support needs it to trace a complaint,
    and no part of the message body is.
    """
    try:
        get_mailer().send(to=to, email=email)
    except Exception:  # noqa: BLE001 - a send must never take down a worker
        log.exception("Gagal mengirim email ke %s (%s)", to, email.subject)
