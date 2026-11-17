"""create ask_usage (shared counters of the question route)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16

One row per counter bucket: the model-call budget of a UTC day (``budget:2026-11-16``) and the per-client
request counters of a minute or an hour (``m:<client hash>:<minute>``, ``h:<client hash>:<hour>``). The
API increments them with one atomic ``INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit`` statement,
so every worker and every restart sees the same count. The client is stored only as a truncated hash and rows
are deleted after two days.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ask_usage",
        sa.Column("bucket", sa.String(96), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ask_usage_updated_at", "ask_usage", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_ask_usage_updated_at", table_name="ask_usage")
    op.drop_table("ask_usage")
