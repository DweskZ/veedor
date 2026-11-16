"""create process_vectors (pgvector)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16

HNSW with cosine operators: the embeddings are L2-normalised, so cosine distance and inner product
rank identically; cosine stays correct even if a future model is not normalised. HNSW needs no
training step (IVFFlat must be built after the data and tuned), so the table can be filled
incrementally and re-built idempotently while the index stays valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIMENSION = 256  # minishlab/potion-multilingual-128M


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "process_vectors",
        sa.Column("ocid", sa.String(160), primary_key=True),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(DIMENSION), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("buyer_ruc", sa.String(20), nullable=True),
        sa.Column("method", sa.String(200), nullable=True),
        sa.Column("award_total", sa.Float(), nullable=True),
        sa.Column("main_cpc", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_process_vectors_buyer_ruc", "process_vectors", ["buyer_ruc"])
    op.create_index(
        "ix_process_vectors_embedding_hnsw",
        "process_vectors",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_process_vectors_embedding_hnsw", table_name="process_vectors")
    op.drop_index("ix_process_vectors_buyer_ruc", table_name="process_vectors")
    op.drop_table("process_vectors")
