"""reclassify transaction type

Revision ID: 4b7c1e95af02
Revises: e18a4b6c3d27
Create Date: 2026-10-13 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "4b7c1e95af02"
down_revision: str | None = "e18a4b6c3d27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The enum stores member NAMES, not values - that is SQLAlchemy's
#: default for `Enum(PyEnum)` and what the initial migration wrote.
_VALUES = (
    "OPENING",
    "INCOME",
    "EXPENSE",
    "TRANSFER",
    "CARD_PAYMENT",
    "REFUND",
    "REVERSAL",
    "RECLASSIFY",
)


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # PostgreSQL 12+ allows this inside a transaction as long as the
        # new label is not used in the same one. Nothing here uses it.
        op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'RECLASSIFY'")
        return

    if bind.dialect.name in {"mysql", "mariadb"}:
        # MySQL has no ALTER TYPE: the enum is the column, so the column
        # is restated with the full member list.
        members = ", ".join(f"'{value}'" for value in _VALUES)
        op.execute(f"ALTER TABLE transactions MODIFY COLUMN type ENUM({members}) NOT NULL")
        return

    # SQLite and anything else render the enum as VARCHAR with a CHECK
    # the tests build from the model, so there is nothing to alter.


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name in {"mysql", "mariadb"}:
        members = ", ".join(f"'{value}'" for value in _VALUES if value != "RECLASSIFY")
        op.execute(f"ALTER TABLE transactions MODIFY COLUMN type ENUM({members}) NOT NULL")

    # PostgreSQL cannot drop an enum label without rewriting the type,
    # and an unused label is harmless. Left in place on purpose.
