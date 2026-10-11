"""transaction group

Revision ID: c7d93f20a165
Revises: 9a2e5d4c71b8
Create Date: 2026-10-11 18:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d93f20a165"
down_revision: str | None = "9a2e5d4c71b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `sa.Uuid`, not `sa.UUID`: native `uuid` on PostgreSQL, CHAR(32)
    # elsewhere. No foreign key - the group has no table, it is only a
    # label shared by transactions confirmed in one swipe.
    op.add_column("transactions", sa.Column("group_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_transactions_user_group", "transactions", ["user_id", "group_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_user_group", table_name="transactions")
    op.drop_column("transactions", "group_id")
