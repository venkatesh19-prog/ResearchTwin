"""research opportunities, funding calls and applications

Revision ID: 0006_opportunities
Revises: 0005_workspaces_and_teams
Create Date: 2026-11-05 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_opportunities"
down_revision: Union[str, None] = "0005_workspaces_and_teams"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("organization", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=150), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=False),
        sa.Column("deadline_at", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("researcher_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("required_skills", sa.Text(), nullable=False),
        sa.Column("required_research_areas", sa.Text(), nullable=False),
        sa.Column("required_expertise", sa.Text(), nullable=False),
        sa.Column("eligibility", sa.Text(), nullable=False),
        sa.Column("external_source", sa.String(length=50), nullable=True),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["researcher_id"], ["researchers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_source",
            "external_id",
            name="uq_opportunities_external_ref",
        ),
    )
    with op.batch_alter_table("opportunities", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_opportunities_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_opportunities_category"), ["category"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_opportunities_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunities_deadline_at"),
            ["deadline_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunities_researcher_id"),
            ["researcher_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunities_status"), ["status"], unique=False
        )

    op.create_table(
        "opportunity_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(
        "opportunity_applications", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_opportunity_applications_id"),
            ["id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunity_applications_opportunity_id"),
            ["opportunity_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunity_applications_reviewed_by_user_id"),
            ["reviewed_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunity_applications_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_opportunity_applications_student_user_id"),
            ["student_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "uq_opportunity_applications_pending",
            ["opportunity_id", "student_user_id"],
            unique=True,
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "opportunity_applications", schema=None
    ) as batch_op:
        batch_op.drop_index(
            "uq_opportunity_applications_pending",
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )
        batch_op.drop_index(
            batch_op.f("ix_opportunity_applications_student_user_id")
        )
        batch_op.drop_index(batch_op.f("ix_opportunity_applications_status"))
        batch_op.drop_index(
            batch_op.f("ix_opportunity_applications_reviewed_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_opportunity_applications_opportunity_id")
        )
        batch_op.drop_index(batch_op.f("ix_opportunity_applications_id"))

    op.drop_table("opportunity_applications")

    with op.batch_alter_table("opportunities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_opportunities_status"))
        batch_op.drop_index(batch_op.f("ix_opportunities_researcher_id"))
        batch_op.drop_index(batch_op.f("ix_opportunities_deadline_at"))
        batch_op.drop_index(batch_op.f("ix_opportunities_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_opportunities_category"))
        batch_op.drop_index(batch_op.f("ix_opportunities_id"))

    op.drop_table("opportunities")
