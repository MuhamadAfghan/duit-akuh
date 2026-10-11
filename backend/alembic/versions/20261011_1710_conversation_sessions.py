"""conversation sessions

Revision ID: 9a2e5d4c71b8
Revises: 3f1b7c0a94de
Create Date: 2026-10-11 17:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a2e5d4c71b8"
down_revision: str | None = "3f1b7c0a94de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("title", sa.String(length=120), nullable=True))

    # Added with a server_default so existing rows get a value, then
    # dropped: the application always supplies one, and leaving the
    # default in place would let an INSERT that forgot the column look
    # correct.
    for column in ("is_pinned", "is_archived"):
        op.add_column(
            "conversations",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # `existing_type` and `existing_nullable` are not optional on
        # MySQL: ALTER there rewrites the whole column definition, so
        # alembic has to be told what the rest of it is or it emits a
        # statement that drops the NOT NULL along with the default.
        op.alter_column(
            "conversations",
            column,
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=None,
        )

    # The constraint that said one thread per user. Dropping it is the
    # whole migration; everything above is what replaces the structure
    # it was standing in for.
    op.drop_constraint("uq_conversation_per_user", "conversations", type_="unique")

    op.create_index(
        "ix_conversations_user_archived", "conversations", ["user_id", "is_archived"]
    )


def downgrade() -> None:
    # Refused before anything is dropped, not after: MySQL does not roll
    # DDL back, so a downgrade that got halfway would leave the table in
    # a shape neither revision describes.
    raise RuntimeError(
        "Tidak bisa turun dari 9a2e5d4c71b8: menghidupkan lagi "
        "uq_conversation_per_user butuh keputusan percakapan mana yang "
        "disimpan dan ke mana pesan sisanya pindah."
    )
