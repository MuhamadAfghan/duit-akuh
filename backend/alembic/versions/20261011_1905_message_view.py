"""message view

Revision ID: e18a4b6c3d27
Revises: c7d93f20a165
Create Date: 2026-10-11 19:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e18a4b6c3d27"
down_revision: str | None = "c7d93f20a165"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out here rather than imported from app/types.py, the way every
# other migration in this directory does it: a migration describes the
# schema as it was at this revision, and importing the live definition
# would make old migrations change meaning when the model does.
#
# JSONB only on PostgreSQL. MariaDB has no such type - its JSON is a
# LONGTEXT alias with a json_valid() CHECK.
JSON_DOC = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("messages", sa.Column("view", JSON_DOC, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "view")
