"""collaboration workspaces and research teams

Revision ID: 0005_workspaces_and_teams
Revises: 0004_verified_profiles
Create Date: 2026-11-05 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_workspaces_and_teams"
down_revision: Union[str, None] = "0004_verified_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collaboration_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collaboration_request_id", sa.Integer(), nullable=False),
        sa.Column("researcher_id", sa.Integer(), nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("faculty_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collaboration_request_id"],
            ["collaboration_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["researcher_id"], ["researchers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["faculty_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("collaboration_workspaces", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_collaboration_workspaces_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_collaboration_workspaces_collaboration_request_id"),
            ["collaboration_request_id"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_collaboration_workspaces_faculty_user_id"),
            ["faculty_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_collaboration_workspaces_researcher_id"),
            ["researcher_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_collaboration_workspaces_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_collaboration_workspaces_student_user_id"),
            ["student_user_id"],
            unique=False,
        )

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["collaboration_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_user"
        ),
    )
    with op.batch_alter_table("workspace_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workspace_members_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_members_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_members_workspace_id"),
            ["workspace_id"],
            unique=False,
        )

    op.create_table(
        "workspace_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("due_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["collaboration_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workspace_tasks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workspace_tasks_assignee_user_id"),
            ["assignee_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_tasks_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_tasks_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_tasks_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_tasks_workspace_id"),
            ["workspace_id"],
            unique=False,
        )

    op.create_table(
        "workspace_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["collaboration_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["workspace_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workspace_comments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workspace_comments_author_user_id"),
            ["author_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_comments_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_comments_task_id"), ["task_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_comments_workspace_id"),
            ["workspace_id"],
            unique=False,
        )

    op.create_table(
        "workspace_milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_at", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["collaboration_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workspace_milestones", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workspace_milestones_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_milestones_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_milestones_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_milestones_workspace_id"),
            ["workspace_id"],
            unique=False,
        )

    op.create_table(
        "research_teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("research_areas", sa.Text(), nullable=False),
        sa.Column("expertise", sa.Text(), nullable=False),
        sa.Column("skills", sa.Text(), nullable=False),
        sa.Column("projects", sa.Text(), nullable=False),
        sa.Column("publications", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("research_teams", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_teams_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_teams_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )

    op.create_table(
        "research_team_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["research_teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id", "user_id", name="uq_research_team_members_team_user"
        ),
    )
    with op.batch_alter_table("research_team_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_team_members_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_team_members_team_id"),
            ["team_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_team_members_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "research_team_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("invited_user_id", sa.Integer(), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("responded_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["research_teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("research_team_invitations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_team_invitations_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_team_invitations_invited_by_user_id"),
            ["invited_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_team_invitations_invited_user_id"),
            ["invited_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_team_invitations_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_team_invitations_team_id"),
            ["team_id"],
            unique=False,
        )
        batch_op.create_index(
            "uq_research_team_invitations_pending",
            ["team_id", "invited_user_id"],
            unique=True,
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    with op.batch_alter_table("research_team_invitations", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_research_team_invitations_pending",
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )
        batch_op.drop_index(batch_op.f("ix_research_team_invitations_team_id"))
        batch_op.drop_index(batch_op.f("ix_research_team_invitations_status"))
        batch_op.drop_index(
            batch_op.f("ix_research_team_invitations_invited_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_research_team_invitations_invited_by_user_id")
        )
        batch_op.drop_index(batch_op.f("ix_research_team_invitations_id"))
    op.drop_table("research_team_invitations")

    with op.batch_alter_table("research_team_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_team_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_research_team_members_team_id"))
        batch_op.drop_index(batch_op.f("ix_research_team_members_id"))
    op.drop_table("research_team_members")

    with op.batch_alter_table("research_teams", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_teams_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_research_teams_id"))
    op.drop_table("research_teams")

    with op.batch_alter_table("workspace_milestones", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workspace_milestones_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_milestones_status"))
        batch_op.drop_index(batch_op.f("ix_workspace_milestones_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_milestones_created_by_user_id"))
    op.drop_table("workspace_milestones")

    with op.batch_alter_table("workspace_comments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workspace_comments_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_comments_task_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_comments_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_comments_author_user_id"))
    op.drop_table("workspace_comments")

    with op.batch_alter_table("workspace_tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workspace_tasks_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_tasks_status"))
        batch_op.drop_index(batch_op.f("ix_workspace_tasks_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_tasks_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_tasks_assignee_user_id"))
    op.drop_table("workspace_tasks")

    with op.batch_alter_table("workspace_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workspace_members_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_members_id"))
    op.drop_table("workspace_members")

    with op.batch_alter_table("collaboration_workspaces", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collaboration_workspaces_student_user_id"))
        batch_op.drop_index(batch_op.f("ix_collaboration_workspaces_status"))
        batch_op.drop_index(batch_op.f("ix_collaboration_workspaces_researcher_id"))
        batch_op.drop_index(batch_op.f("ix_collaboration_workspaces_faculty_user_id"))
        batch_op.drop_index(
            batch_op.f("ix_collaboration_workspaces_collaboration_request_id")
        )
        batch_op.drop_index(batch_op.f("ix_collaboration_workspaces_id"))
    op.drop_table("collaboration_workspaces")
