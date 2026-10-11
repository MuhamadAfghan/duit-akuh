"""Transactional email templates.

Two of them, both about the account itself: a reset link, and a notice
that the password changed. Neither markets anything, which is why
neither carries an unsubscribe link. A security notice the recipient can
switch off is a hole, not a courtesy, and CAN-SPAM's unsubscribe rule
covers commercial mail, not this.

Templates are plain files with ``{{placeholder}}`` rather than Jinja, for
two reasons: nothing else in the project needs a template engine, and
the substitution here is deliberately dumb. Every value is HTML-escaped
in the HTML part, so an address somebody typed into the email field
cannot smuggle markup into the message.

Rendering raises when a placeholder is left unfilled. An email that
ships the literal text ``{{reset_url}}`` is a dead end for the person
reading it, and that failure must happen in our process, not in their
inbox.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

_DIR = Path(__file__).parent
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

#: Subjects live here, not in the template files, so the sender can read
#: one without parsing the other. Keep them under 45 characters: Gmail on
#: a phone truncates past roughly that.
SUBJECTS: dict[str, str] = {
    "reset_password": "Bikin password baru",
    "password_changed": "Password akun lu baru diganti",
}


class TemplateError(RuntimeError):
    """A template is missing, or a placeholder was left unfilled."""


@dataclass(frozen=True, slots=True)
class Email:
    subject: str
    html: str
    text: str


def _fill(template: str, values: dict[str, str], *, as_html: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        value = str(values[key])
        return escape(value, quote=True) if as_html else value

    filled = _PLACEHOLDER.sub(replace, template)

    leftover = sorted(set(_PLACEHOLDER.findall(filled)))
    if leftover:
        raise TemplateError(f"Placeholder belum diisi: {', '.join(leftover)}")

    return filled


def render(name: str, **values: str) -> Email:
    """Render one template to its HTML and plain-text parts.

    Both parts are returned because a transactional message should carry
    both: some clients render only the text part, and a message with no
    text alternative scores worse with spam filters.
    """
    if name not in SUBJECTS:
        raise TemplateError(f"Template tidak dikenal: {name}")

    try:
        html_source = (_DIR / f"{name}.html").read_text(encoding="utf-8")
        text_source = (_DIR / f"{name}.txt").read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - packaging slip
        raise TemplateError(f"Berkas template hilang untuk {name}") from exc

    return Email(
        subject=SUBJECTS[name],
        html=_fill(html_source, values, as_html=True),
        text=_fill(text_source, values, as_html=False),
    )
