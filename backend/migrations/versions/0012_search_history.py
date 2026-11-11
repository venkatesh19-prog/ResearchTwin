"""add per-user search history

Revision ID: 0012_search_history
Revises: 0011_drop_redundant_indexes
Create Date: 2026-11-09 00:00:00.000000

Each account keeps its own short list of committed directory queries so the
researcher directory can offer recent searches. Rows cascade with the owning
user and the list length is bounded by the application, not the schema.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_search_history"
down_revision: Union[str, None] = "0011_drop_redundant_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_search_history_user_id"),
        "search_history",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_search_history_user_id"),
        table_name="search_history",
    )
    op.drop_table("search_history")
