"""create reviews table

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ocid", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed_signal', 'dismissed')", name="ck_reviews_status"
        ),
    )
    op.create_index("ix_reviews_ocid_created_at", "reviews", ["ocid", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reviews_ocid_created_at", table_name="reviews")
    op.drop_table("reviews")
