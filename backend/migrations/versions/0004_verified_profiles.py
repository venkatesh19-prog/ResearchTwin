"""verified researcher profile requests

Revision ID: 0004_verified_profiles
Revises: 0003_groups
Create Date: 2026-11-05 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_verified_profiles"
down_revision: Union[str, None] = "0003_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "researcher_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("researcher_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["researcher_id"], ["researchers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("researcher_verifications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_researcher_verifications_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_researcher_verifications_researcher_id"),
            ["researcher_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_researcher_verifications_reviewed_by_user_id"),
            ["reviewed_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_researcher_verifications_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_researcher_verifications_submitted_by_user_id"),
            ["submitted_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "uq_researcher_verifications_pending",
            ["researcher_id"],
            unique=True,
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    with op.batch_alter_table("researcher_verifications", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_researcher_verifications_pending",
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )
        batch_op.drop_index(
            batch_op.f("ix_researcher_verifications_submitted_by_user_id")
        )
        batch_op.drop_index(batch_op.f("ix_researcher_verifications_status"))
        batch_op.drop_index(
            batch_op.f("ix_researcher_verifications_reviewed_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_researcher_verifications_researcher_id")
        )
        batch_op.drop_index(batch_op.f("ix_researcher_verifications_id"))

    op.drop_table("researcher_verifications")
