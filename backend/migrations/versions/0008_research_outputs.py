"""literature, proposals, theses and publication submissions

Revision ID: 0008_research_outputs
Revises: 0007_research_intelligence
Create Date: 2026-11-05 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_research_outputs"
down_revision: Union[str, None] = "0007_research_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "literature_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("authors", sa.Text(), nullable=False),
        sa.Column("venue", sa.String(length=300), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("citation_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "citation_key",
            name="uq_literature_entries_owner_citation_key",
        ),
    )
    with op.batch_alter_table("literature_entries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_literature_entries_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_literature_entries_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_literature_entries_review_status"),
            ["review_status"],
            unique=False,
        )

    op.create_table(
        "research_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("research_proposals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_proposals_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_research_proposals_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_proposals_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "proposal_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["research_proposals.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("proposal_sections", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_proposal_sections_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_sections_proposal_id"),
            ["proposal_id"],
            unique=False,
        )

    op.create_table(
        "proposal_collaborators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["research_proposals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_id",
            "user_id",
            name="uq_proposal_collaborators_proposal_user",
        ),
    )
    with op.batch_alter_table("proposal_collaborators", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_proposal_collaborators_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_collaborators_proposal_id"),
            ["proposal_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_collaborators_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "proposal_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["research_proposals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_id",
            "version_number",
            name="uq_proposal_versions_proposal_version",
        ),
    )
    with op.batch_alter_table("proposal_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_proposal_versions_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_versions_proposal_id"),
            ["proposal_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_versions_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )

    op.create_table(
        "proposal_citations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("literature_entry_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["research_proposals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["literature_entry_id"], ["literature_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["section_id"], ["proposal_sections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_id",
            "literature_entry_id",
            name="uq_proposal_citations_proposal_entry",
        ),
    )
    with op.batch_alter_table("proposal_citations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_proposal_citations_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_citations_proposal_id"),
            ["proposal_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_citations_literature_entry_id"),
            ["literature_entry_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_citations_section_id"),
            ["section_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_citations_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )

    op.create_table(
        "thesis_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supervisor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("thesis_records", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_thesis_records_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_records_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_records_supervisor_user_id"),
            ["supervisor_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_records_status"), ["status"], unique=False
        )

    op.create_table(
        "thesis_milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_at", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["thesis_id"], ["thesis_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("thesis_milestones", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_thesis_milestones_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_milestones_thesis_id"),
            ["thesis_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_milestones_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_milestones_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )

    op.create_table(
        "thesis_progress_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("milestone_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["thesis_id"], ["thesis_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("thesis_progress_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_thesis_progress_events_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_progress_events_thesis_id"),
            ["thesis_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_progress_events_actor_user_id"),
            ["actor_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_progress_events_event_type"),
            ["event_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_thesis_progress_events_created_at"),
            ["created_at"],
            unique=False,
        )

    op.create_table(
        "publication_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("venue", sa.String(length=300), nullable=False),
        sa.Column("venue_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("doi", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.Integer(), nullable=True),
        sa.Column("decision_at", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("publication_submissions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_publication_submissions_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_publication_submissions_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_submissions_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "publication_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["publication_submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "revision_number",
            name="uq_publication_revisions_submission_number",
        ),
    )
    with op.batch_alter_table("publication_revisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_publication_revisions_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_publication_revisions_submission_id"),
            ["submission_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_revisions_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )

    op.create_table(
        "publication_status_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("from_status", sa.String(length=20), nullable=False),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["publication_submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("publication_status_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_publication_status_events_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_publication_status_events_submission_id"),
            ["submission_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_status_events_actor_user_id"),
            ["actor_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_status_events_to_status"),
            ["to_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_publication_status_events_created_at"),
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("publication_status_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_publication_status_events_created_at"))
        batch_op.drop_index(batch_op.f("ix_publication_status_events_to_status"))
        batch_op.drop_index(batch_op.f("ix_publication_status_events_actor_user_id"))
        batch_op.drop_index(
            batch_op.f("ix_publication_status_events_submission_id")
        )
        batch_op.drop_index(batch_op.f("ix_publication_status_events_id"))
    op.drop_table("publication_status_events")

    with op.batch_alter_table("publication_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_publication_revisions_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_publication_revisions_submission_id"))
        batch_op.drop_index(batch_op.f("ix_publication_revisions_id"))
    op.drop_table("publication_revisions")

    with op.batch_alter_table("publication_submissions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_publication_submissions_status"))
        batch_op.drop_index(batch_op.f("ix_publication_submissions_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_publication_submissions_id"))
    op.drop_table("publication_submissions")

    with op.batch_alter_table("thesis_progress_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_thesis_progress_events_created_at"))
        batch_op.drop_index(batch_op.f("ix_thesis_progress_events_event_type"))
        batch_op.drop_index(batch_op.f("ix_thesis_progress_events_actor_user_id"))
        batch_op.drop_index(batch_op.f("ix_thesis_progress_events_thesis_id"))
        batch_op.drop_index(batch_op.f("ix_thesis_progress_events_id"))
    op.drop_table("thesis_progress_events")

    with op.batch_alter_table("thesis_milestones", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_thesis_milestones_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_thesis_milestones_status"))
        batch_op.drop_index(batch_op.f("ix_thesis_milestones_thesis_id"))
        batch_op.drop_index(batch_op.f("ix_thesis_milestones_id"))
    op.drop_table("thesis_milestones")

    with op.batch_alter_table("thesis_records", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_thesis_records_status"))
        batch_op.drop_index(batch_op.f("ix_thesis_records_supervisor_user_id"))
        batch_op.drop_index(batch_op.f("ix_thesis_records_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_thesis_records_id"))
    op.drop_table("thesis_records")

    with op.batch_alter_table("proposal_citations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposal_citations_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_citations_section_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_citations_literature_entry_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_citations_proposal_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_citations_id"))
    op.drop_table("proposal_citations")

    with op.batch_alter_table("proposal_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposal_versions_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_versions_proposal_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_versions_id"))
    op.drop_table("proposal_versions")

    with op.batch_alter_table("proposal_collaborators", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposal_collaborators_user_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_collaborators_proposal_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_collaborators_id"))
    op.drop_table("proposal_collaborators")

    with op.batch_alter_table("proposal_sections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposal_sections_proposal_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_sections_id"))
    op.drop_table("proposal_sections")

    with op.batch_alter_table("research_proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_proposals_status"))
        batch_op.drop_index(batch_op.f("ix_research_proposals_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_research_proposals_id"))
    op.drop_table("research_proposals")

    with op.batch_alter_table("literature_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_literature_entries_review_status"))
        batch_op.drop_index(batch_op.f("ix_literature_entries_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_literature_entries_id"))
    op.drop_table("literature_entries")
