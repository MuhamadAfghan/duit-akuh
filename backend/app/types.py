"""Column types that behave identically on PostgreSQL and MySQL/MariaDB.

The deployment target is a cPanel shared host with MariaDB 10.6 and no
PostgreSQL available at all, while PostgreSQL stays the better engine for
this schema. Rather than fork the models, the three places where the two
engines genuinely differ are isolated here:

* JSON documents — PostgreSQL has JSONB; MariaDB 10.6 has no native JSON
  type (``JSON`` there is an alias for ``LONGTEXT`` plus a
  ``json_valid()`` CHECK).
* Timestamps — PostgreSQL has ``timestamptz``; MariaDB has no
  timezone-aware type whatsoever.
* UUIDs — PostgreSQL has ``uuid``; MariaDB only gained one in 10.7, so
  ``sqlalchemy.Uuid`` stores ``CHAR(32)`` here.

Nothing outside this module and ``app.models`` needs to know which engine
is in use: ``app/domain/`` is pure, and ``app/services/`` contains no
dialect-specific SQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Text, types
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.engine import Dialect

#: A JSON document column.
#:
#: Keeps JSONB on PostgreSQL — binary and indexable — and falls back to
#: the generic type elsewhere, where SQLAlchemy does the serialising. No
#: query in this codebase indexes *into* a document, so the fallback
#: costs nothing but the ability to add such an index later on MariaDB.
JsonDoc = JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class UtcDateTime(types.TypeDecorator):
    """A timestamp that is always timezone-aware UTC on the Python side.

    PostgreSQL round-trips an aware datetime unchanged. MariaDB stores
    wall-clock digits in ``DATETIME`` and hands them back *naive*, so
    without this decorator the first comparison against :func:`utcnow`
    would raise ``TypeError: can't subtract offset-naive and
    offset-aware datetimes`` — and, worse, any comparison that happened
    to succeed would be silently wrong. Converting here means every call
    site keeps the single invariant "timestamps are aware UTC".

    Two details that are easy to get wrong on MariaDB:

    * ``fsp=6``. Left to itself MariaDB truncates ``DATETIME`` to whole
      seconds, which collapses orderings that depend on sub-second
      resolution.
    * The session time zone. ``app.db`` pins every MySQL connection to
      ``+00:00`` so a server-side ``CURRENT_TIMESTAMP`` default is UTC
      too. This host's system zone is WIB (+07), so without that pin
      server-defaulted rows would read back seven hours out.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))

        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            # Refusing beats guessing: a naive value is ambiguous, and
            # storing the wrong instant in a ledger is unrecoverable.
            raise ValueError(
                "refusing to store a naive datetime; attach a timezone "
                "(app.models.utcnow returns an aware UTC value)"
            )

        value = value.astimezone(timezone.utc)

        # MariaDB would reject the offset outright.
        return value.replace(tzinfo=None) if dialect.name == "mysql" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
