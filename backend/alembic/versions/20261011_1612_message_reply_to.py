"""message reply_to

Revision ID: 3f1b7c0a94de
Revises: 8c4ad17be2f1
Create Date: 2026-10-11 16:12:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3f1b7c0a94de"
down_revision: str | None = "8c4ad17be2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `sa.Uuid`, not `sa.UUID`: the first renders native `uuid` on
    # PostgreSQL and CHAR(32) elsewhere, the second emits a native type
    # MariaDB only has from 10.7. Same choice as app/types.py makes for
    # every other id column here.
    op.add_column(
        "messages",
        sa.Column("reply_to_id", sa.Uuid(as_uuid=True), nullable=True),
    )

    # Self-referential, and SET NULL on purpose: deleting a quoted
    # message must not delete the reply that pointed at it.
    op.create_foreign_key(
        "fk_messages_reply_to_id_messages",
        "messages",
        "messages",
        ["reply_to_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_reply_to_id_messages", "messages", type_="foreignkey")
    op.drop_column("messages", "reply_to_id")
