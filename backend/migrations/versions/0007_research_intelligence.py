"""persisted research clustering results

Revision ID: 0007_research_intelligence
Revises: 0006_opportunities
Create Date: 2026-11-05 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_research_intelligence"
down_revision: Union[str, None] = "0006_opportunities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_cluster_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("semantic_used", sa.Boolean(), nullable=False),
        sa.Column("min_similarity", sa.Float(), nullable=False),
        sa.Column("researcher_count", sa.Integer(), nullable=False),
        sa.Column("cluster_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("research_cluster_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_cluster_runs_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_cluster_runs_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )

    op.create_table(
        "research_cluster_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("researcher_id", sa.Integer(), nullable=False),
        sa.Column("cluster_index", sa.Integer(), nullable=False),
        sa.Column("cluster_label", sa.String(length=300), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_cluster_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["researcher_id"], ["researchers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "researcher_id",
            name="uq_research_cluster_assignments_run_researcher",
        ),
    )
    with op.batch_alter_table(
        "research_cluster_assignments", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_cluster_assignments_id"),
            ["id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_cluster_assignments_cluster_index"),
            ["cluster_index"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_cluster_assignments_researcher_id"),
            ["researcher_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_cluster_assignments_run_id"),
            ["run_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "research_cluster_assignments", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_research_cluster_assignments_run_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_research_cluster_assignments_researcher_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_research_cluster_assignments_cluster_index")
        )
        batch_op.drop_index(batch_op.f("ix_research_cluster_assignments_id"))

    op.drop_table("research_cluster_assignments")

    with op.batch_alter_table("research_cluster_runs", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_research_cluster_runs_created_by_user_id")
        )
        batch_op.drop_index(batch_op.f("ix_research_cluster_runs_id"))

    op.drop_table("research_cluster_runs")
