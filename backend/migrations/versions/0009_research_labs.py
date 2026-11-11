"""research labs and inter-university collaboration

Revision ID: 0009_research_labs
Revises: 0008_research_outputs
Create Date: 2026-11-05 22:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_research_labs"
down_revision: Union[str, None] = "0008_research_outputs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("institutions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_institutions_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_institutions_name"), ["name"], unique=True
        )

    op.create_table(
        "institution_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("institution_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_institution_memberships_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_institution_memberships_institution_id"),
            ["institution_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_institution_memberships_user_id"),
            ["user_id"],
            unique=True,
        )

    op.create_table(
        "research_labs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("research_areas", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id", "name", name="uq_research_labs_institution_name"
        ),
    )
    with op.batch_alter_table("research_labs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_labs_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_labs_institution_id"),
            ["institution_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_labs_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_labs_visibility"),
            ["visibility"],
            unique=False,
        )

    op.create_table(
        "research_lab_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lab_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lab_id"], ["research_labs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lab_id", "user_id", name="uq_research_lab_members_lab_user"
        ),
    )
    with op.batch_alter_table("research_lab_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_lab_members_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_lab_members_lab_id"),
            ["lab_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_lab_members_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "interuniversity_collaborations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requester_lab_id", sa.Integer(), nullable=False),
        sa.Column("partner_lab_id", sa.Integer(), nullable=False),
        sa.Column("initiated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.Column("responded_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requester_lab_id"], ["research_labs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["partner_lab_id"], ["research_labs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(
        "interuniversity_collaborations", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_interuniversity_collaborations_id"),
            ["id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_interuniversity_collaborations_requester_lab_id"),
            ["requester_lab_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_interuniversity_collaborations_partner_lab_id"),
            ["partner_lab_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_interuniversity_collaborations_initiated_by_user_id"),
            ["initiated_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_interuniversity_collaborations_decided_by_user_id"),
            ["decided_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_interuniversity_collaborations_status"),
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "interuniversity_collaborations", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_interuniversity_collaborations_status")
        )
        batch_op.drop_index(
            batch_op.f("ix_interuniversity_collaborations_decided_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_interuniversity_collaborations_initiated_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_interuniversity_collaborations_partner_lab_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_interuniversity_collaborations_requester_lab_id")
        )
        batch_op.drop_index(batch_op.f("ix_interuniversity_collaborations_id"))
    op.drop_table("interuniversity_collaborations")

    with op.batch_alter_table("research_lab_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_lab_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_research_lab_members_lab_id"))
        batch_op.drop_index(batch_op.f("ix_research_lab_members_id"))
    op.drop_table("research_lab_members")

    with op.batch_alter_table("research_labs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_labs_visibility"))
        batch_op.drop_index(batch_op.f("ix_research_labs_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_research_labs_institution_id"))
        batch_op.drop_index(batch_op.f("ix_research_labs_id"))
    op.drop_table("research_labs")

    with op.batch_alter_table("institution_memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_institution_memberships_user_id"))
        batch_op.drop_index(
            batch_op.f("ix_institution_memberships_institution_id")
        )
        batch_op.drop_index(batch_op.f("ix_institution_memberships_id"))
    op.drop_table("institution_memberships")

    with op.batch_alter_table("institutions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_institutions_name"))
        batch_op.drop_index(batch_op.f("ix_institutions_id"))
    op.drop_table("institutions")
