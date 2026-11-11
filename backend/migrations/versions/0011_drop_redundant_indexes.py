"""drop redundant primary-key and unique-prefix indexes

Revision ID: 0011_drop_redundant_indexes
Revises: 0010_repair_batch_2
Create Date: 2026-11-05 00:00:00.000000

Primary-key indexes duplicate the database's own primary-key btree. The
single-column indexes below duplicate the leading column of an existing
full unique constraint, so any query that could use them can use the unique
index instead. Partial unique indexes are intentionally left alone because
they do not cover rows outside their predicate.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_drop_redundant_indexes"
down_revision: Union[str, None] = "0010_repair_batch_2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REDUNDANT_INDEXES = (
    ("audit_events", "ix_audit_events_id", ["id"]),
    ("auth_sessions", "ix_auth_sessions_id", ["id"]),
    ("collaboration_requests", "ix_collaboration_requests_id", ["id"]),
    ("collaboration_workspaces", "ix_collaboration_workspaces_id", ["id"]),
    ("faculty_profiles", "ix_faculty_profiles_id", ["id"]),
    ("faculty_researcher_links", "ix_faculty_researcher_links_id", ["id"]),
    ("group_memberships", "ix_group_memberships_id", ["id"]),
    ("group_memberships", "ix_group_memberships_group_id", ["group_id"]),
    ("groups", "ix_groups_id", ["id"]),
    ("institution_memberships", "ix_institution_memberships_id", ["id"]),
    ("institutions", "ix_institutions_id", ["id"]),
    (
        "interuniversity_collaborations",
        "ix_interuniversity_collaborations_id",
        ["id"],
    ),
    ("literature_entries", "ix_literature_entries_id", ["id"]),
    (
        "literature_entries",
        "ix_literature_entries_owner_user_id",
        ["owner_user_id"],
    ),
    ("opportunities", "ix_opportunities_id", ["id"]),
    (
        "opportunity_applications",
        "ix_opportunity_applications_id",
        ["id"],
    ),
    ("proposal_citations", "ix_proposal_citations_id", ["id"]),
    (
        "proposal_citations",
        "ix_proposal_citations_proposal_id",
        ["proposal_id"],
    ),
    ("proposal_collaborators", "ix_proposal_collaborators_id", ["id"]),
    (
        "proposal_collaborators",
        "ix_proposal_collaborators_proposal_id",
        ["proposal_id"],
    ),
    ("proposal_sections", "ix_proposal_sections_id", ["id"]),
    ("proposal_versions", "ix_proposal_versions_id", ["id"]),
    (
        "proposal_versions",
        "ix_proposal_versions_proposal_id",
        ["proposal_id"],
    ),
    ("publication_revisions", "ix_publication_revisions_id", ["id"]),
    (
        "publication_revisions",
        "ix_publication_revisions_submission_id",
        ["submission_id"],
    ),
    (
        "publication_status_events",
        "ix_publication_status_events_id",
        ["id"],
    ),
    (
        "publication_submissions",
        "ix_publication_submissions_id",
        ["id"],
    ),
    (
        "research_cluster_assignments",
        "ix_research_cluster_assignments_id",
        ["id"],
    ),
    (
        "research_cluster_assignments",
        "ix_research_cluster_assignments_run_id",
        ["run_id"],
    ),
    ("research_cluster_runs", "ix_research_cluster_runs_id", ["id"]),
    ("research_lab_members", "ix_research_lab_members_id", ["id"]),
    (
        "research_lab_members",
        "ix_research_lab_members_lab_id",
        ["lab_id"],
    ),
    ("research_labs", "ix_research_labs_id", ["id"]),
    (
        "research_labs",
        "ix_research_labs_institution_id",
        ["institution_id"],
    ),
    ("research_proposals", "ix_research_proposals_id", ["id"]),
    ("research_team_invitations", "ix_research_team_invitations_id", ["id"]),
    ("research_team_members", "ix_research_team_members_id", ["id"]),
    (
        "research_team_members",
        "ix_research_team_members_team_id",
        ["team_id"],
    ),
    ("research_teams", "ix_research_teams_id", ["id"]),
    ("researcher_verifications", "ix_researcher_verifications_id", ["id"]),
    ("researchers", "ix_researchers_id", ["id"]),
    ("roadmap_progress", "ix_roadmap_progress_id", ["id"]),
    ("roadmap_progress", "ix_roadmap_progress_user_id", ["user_id"]),
    ("student_profiles", "ix_student_profiles_id", ["id"]),
    ("thesis_milestones", "ix_thesis_milestones_id", ["id"]),
    ("thesis_progress_events", "ix_thesis_progress_events_id", ["id"]),
    ("thesis_records", "ix_thesis_records_id", ["id"]),
    ("users", "ix_users_id", ["id"]),
    ("workspace_comments", "ix_workspace_comments_id", ["id"]),
    ("workspace_members", "ix_workspace_members_id", ["id"]),
    (
        "workspace_members",
        "ix_workspace_members_workspace_id",
        ["workspace_id"],
    ),
    ("workspace_milestones", "ix_workspace_milestones_id", ["id"]),
    ("workspace_tasks", "ix_workspace_tasks_id", ["id"]),
)


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index_name in {
        index["name"] for index in inspector.get_indexes(table_name)
    }


def upgrade() -> None:
    for table_name, index_name, _ in REDUNDANT_INDEXES:
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)


def downgrade() -> None:
    for table_name, index_name, column_names in REDUNDANT_INDEXES:
        if not _index_exists(table_name, index_name):
            op.create_index(index_name, table_name, column_names, unique=False)
