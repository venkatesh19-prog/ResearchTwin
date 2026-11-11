from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from .database import Base


class Researcher(Base):
    __tablename__ = "researchers"

    id = Column(Integer, primary_key=True)

    # Basic information
    name = Column(String(100), nullable=False)
    department = Column(String(150))
    designation = Column(String(100))
    experience = Column(Integer)

    # Research information
    research_areas = Column(Text)
    expertise = Column(Text)
    skills = Column(Text)

    # Research work
    publications = Column(Text)
    projects = Column(Text)

    # External profile
    profile_url = Column(String(300))


class ResearcherVerification(Base):
    """One verification request and its review; rows form the audit history.

    The newest row per researcher is the current state. Evidence references
    and review notes are private and must never appear in public responses.
    """

    __tablename__ = "researcher_verifications"

    id = Column(Integer, primary_key=True)
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(20), nullable=False, default="pending", index=True)
    evidence_reference = Column(Text, nullable=False, default="")
    note = Column(Text, nullable=False, default="")
    review_note = Column(Text, nullable=False, default="")
    submitted_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_at = Column(Integer, nullable=False)
    reviewed_at = Column(Integer, nullable=True)
    expires_at = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        # At most one pending request per researcher, while keeping every
        # reviewed request as history. NULLs do not conflict in either database.
        Index(
            "uq_researcher_verifications_pending",
            "researcher_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(254), nullable=False, unique=True, index=True)
    full_name = Column(String(120), nullable=False)
    role = Column(String(20), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(Integer, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(Integer, nullable=False)
    expires_at = Column(Integer, nullable=False)
    revoked_at = Column(Integer, nullable=True)


class AuditEvent(Base):
    """One administrative or collaboration action, kept for accountability.

    ``detail`` holds a small JSON object with non-secret context only.
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(64), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, index=True)
    target_id = Column(Integer, nullable=True, index=True)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(Integer, nullable=False, index=True)


class SearchHistory(Base):
    """One researcher-directory query saved for a user's own recent list."""

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query = Column(String(200), nullable=False)
    created_at = Column(Integer, nullable=False)


class Group(Base):
    """A named role cohort (for example ``students`` or ``faculty``)."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    created_at = Column(Integer, nullable=False)


class GroupMembership(Base):
    """One account's membership in one group; unique per (group, user)."""

    __tablename__ = "group_memberships"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_memberships_group_user"),
    )


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"

    bucket_hash = Column(String(64), primary_key=True)
    window_start = Column(Integer, nullable=False)
    count = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False, index=True)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    research_areas = Column(Text, nullable=False, default="")
    expertise = Column(Text, nullable=False, default="")
    skills = Column(Text, nullable=False, default="")
    projects = Column(Text, nullable=False, default="")
    publications = Column(Text, nullable=False, default="")
    courses = Column(Text, nullable=False, default="")
    academic_details = Column(Text, nullable=False, default="")
    updated_at = Column(Integer, nullable=False)


class FacultyProfile(Base):
    __tablename__ = "faculty_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    department = Column(String(150), nullable=False, default="")
    designation = Column(String(100), nullable=False, default="")
    research_areas = Column(Text, nullable=False, default="")
    expertise = Column(Text, nullable=False, default="")
    skills = Column(Text, nullable=False, default="")
    publications = Column(Text, nullable=False, default="")
    projects = Column(Text, nullable=False, default="")
    profile_url = Column(String(300), nullable=False, default="")
    updated_at = Column(Integer, nullable=False)


class FacultyResearcherLink(Base):
    """Binds a faculty account to the researcher directory record it owns.

    The directory records and the login accounts are separate by design, so
    collaboration requests addressed to a researcher need an explicit,
    verifiable owner instead of a name match.
    """

    __tablename__ = "faculty_researcher_links"

    id = Column(Integer, primary_key=True)
    faculty_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)


class CollaborationRequest(Base):
    """A student's request to work with one researcher record."""

    __tablename__ = "collaboration_requests"

    id = Column(Integer, primary_key=True)
    student_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="pending", index=True)
    faculty_response = Column(Text, nullable=False, default="")
    reviewed_at = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)

    __table_args__ = (
        # One pending request per student/researcher pair; decided requests
        # remain as history.
        Index(
            "uq_collaboration_requests_pending",
            "student_user_id",
            "researcher_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )


class CollaborationWorkspace(Base):
    """The shared working space created when a collaboration is accepted."""

    __tablename__ = "collaboration_workspaces"

    id = Column(Integer, primary_key=True)
    collaboration_request_id = Column(
        Integer,
        ForeignKey("collaboration_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    faculty_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class WorkspaceMember(Base):
    """One account's membership and workspace-local role."""

    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(
        Integer,
        ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False, default="member")
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_user"
        ),
    )


class WorkspaceTask(Base):
    __tablename__ = "workspace_tasks"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(
        Integer,
        ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="todo", index=True)
    assignee_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    due_at = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class WorkspaceComment(Base):
    __tablename__ = "workspace_comments"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(
        Integer,
        ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Integer,
        ForeignKey("workspace_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    author_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body = Column(Text, nullable=False)
    created_at = Column(Integer, nullable=False)


class WorkspaceMilestone(Base):
    __tablename__ = "workspace_milestones"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(
        Integer,
        ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    due_at = Column(Integer, nullable=True)
    completed_at = Column(Integer, nullable=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class ResearchTeam(Base):
    """A self-organised research team, separate from auth role groups."""

    __tablename__ = "research_teams"

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, default="")
    research_areas = Column(Text, nullable=False, default="")
    expertise = Column(Text, nullable=False, default="")
    skills = Column(Text, nullable=False, default="")
    projects = Column(Text, nullable=False, default="")
    publications = Column(Text, nullable=False, default="")
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class ResearchTeamMember(Base):
    __tablename__ = "research_team_members"

    id = Column(Integer, primary_key=True)
    team_id = Column(
        Integer,
        ForeignKey("research_teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False, default="member")
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "team_id", "user_id", name="uq_research_team_members_team_user"
        ),
    )


class ResearchTeamInvitation(Base):
    __tablename__ = "research_team_invitations"

    id = Column(Integer, primary_key=True)
    team_id = Column(
        Integer,
        ForeignKey("research_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(Integer, nullable=False)
    responded_at = Column(Integer, nullable=True)

    __table_args__ = (
        # One outstanding invitation per team and account; reviewed rows are
        # kept as history.
        Index(
            "uq_research_team_invitations_pending",
            "team_id",
            "invited_user_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )


class Opportunity(Base):
    """One research opportunity or funding call.

    A single table keeps search, deadlines, eligibility requirements and
    application tracking coherent across both categories. ``researcher_id``
    is only meaningful for research opportunities; funding records are
    institutional and never carry a researcher.
    """

    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True)
    category = Column(String(20), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    organization = Column(String(200), nullable=False, default="")
    location = Column(String(150), nullable=False, default="")
    url = Column(String(300), nullable=False, default="")
    deadline_at = Column(Integer, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    required_skills = Column(Text, nullable=False, default="")
    required_research_areas = Column(Text, nullable=False, default="")
    required_expertise = Column(Text, nullable=False, default="")
    eligibility = Column(Text, nullable=False, default="")
    external_source = Column(String(50), nullable=True)
    external_id = Column(String(200), nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)

    __table_args__ = (
        # Imported records are deduplicated by their source reference. NULLs
        # remain distinct in both SQLite and PostgreSQL for local records.
        UniqueConstraint(
            "external_source",
            "external_id",
            name="uq_opportunities_external_ref",
        ),
    )


class OpportunityApplication(Base):
    """A student's application to one opportunity, with owner review."""

    __tablename__ = "opportunity_applications"

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(
        Integer,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="pending", index=True)
    decision_note = Column(Text, nullable=False, default="")
    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)
    reviewed_at = Column(Integer, nullable=True)

    __table_args__ = (
        # One outstanding application per student and opportunity; withdrawn
        # and reviewed rows remain as history.
        Index(
            "uq_opportunity_applications_pending",
            "opportunity_id",
            "student_user_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )


class ResearchClusterRun(Base):
    """One offline clustering result; the newest run is the read cache."""

    __tablename__ = "research_cluster_runs"

    id = Column(Integer, primary_key=True)
    method = Column(String(50), nullable=False)
    semantic_used = Column(Boolean, nullable=False, default=False)
    min_similarity = Column(Float, nullable=False)
    researcher_count = Column(Integer, nullable=False)
    cluster_count = Column(Integer, nullable=False)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)


class ResearchClusterAssignment(Base):
    """A researcher's persisted cluster membership within one run."""

    __tablename__ = "research_cluster_assignments"

    id = Column(Integer, primary_key=True)
    run_id = Column(
        Integer,
        ForeignKey("research_cluster_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cluster_index = Column(Integer, nullable=False, index=True)
    cluster_label = Column(String(300), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "researcher_id",
            name="uq_research_cluster_assignments_run_researcher",
        ),
    )


class LiteratureEntry(Base):
    """One private reference record owned by an account.

    ``tags`` is a comma-separated normalised list; ``notes`` and review state
    are private to the owner and are never exposed through proposal citations.
    """

    __tablename__ = "literature_entries"

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(300), nullable=False)
    authors = Column(Text, nullable=False, default="")
    venue = Column(String(300), nullable=False, default="")
    year = Column(Integer, nullable=True)
    doi = Column(String(200), nullable=False, default="")
    url = Column(String(500), nullable=False, default="")
    abstract = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    tags = Column(Text, nullable=False, default="")
    review_status = Column(
        String(20), nullable=False, default="to_read", index=True
    )
    citation_key = Column(String(100), nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)

    __table_args__ = (
        # Citation keys are optional, but must be unique within one library.
        UniqueConstraint(
            "owner_user_id",
            "citation_key",
            name="uq_literature_entries_owner_citation_key",
        ),
    )


class ResearchProposal(Base):
    """A proposal owned by an account and optionally shared with collaborators."""

    __tablename__ = "research_proposals"

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class ProposalSection(Base):
    """One ordered section of a proposal; positions restart at zero."""

    __tablename__ = "proposal_sections"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(
        Integer,
        ForeignKey("research_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    heading = Column(String(200), nullable=False)
    body = Column(Text, nullable=False, default="")
    position = Column(Integer, nullable=False)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class ProposalCollaborator(Base):
    """A proposal-local role: ``editor`` can change content, ``viewer`` cannot."""

    __tablename__ = "proposal_collaborators"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(
        Integer,
        ForeignKey("research_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False, default="viewer")
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "proposal_id", "user_id", name="uq_proposal_collaborators_proposal_user"
        ),
    )


class ProposalVersion(Base):
    """An immutable content snapshot taken after every proposal mutation."""

    __tablename__ = "proposal_versions"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(
        Integer,
        ForeignKey("research_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False)
    snapshot = Column(Text, nullable=False)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "proposal_id",
            "version_number",
            name="uq_proposal_versions_proposal_version",
        ),
    )


class ProposalCitation(Base):
    """A proposal's use of one private literature entry, optionally in a section."""

    __tablename__ = "proposal_citations"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(
        Integer,
        ForeignKey("research_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    literature_entry_id = Column(
        Integer,
        ForeignKey("literature_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id = Column(
        Integer,
        ForeignKey("proposal_sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "proposal_id",
            "literature_entry_id",
            name="uq_proposal_citations_proposal_entry",
        ),
    )


class ThesisRecord(Base):
    """A student's thesis, separate from the skill-readiness roadmap."""

    __tablename__ = "thesis_records"

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supervisor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(300), nullable=False)
    abstract = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="proposed", index=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class ThesisMilestone(Base):
    """One ordered milestone with an optional deadline."""

    __tablename__ = "thesis_milestones"

    id = Column(Integer, primary_key=True)
    thesis_id = Column(
        Integer,
        ForeignKey("thesis_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    due_at = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    position = Column(Integer, nullable=False)
    completed_at = Column(Integer, nullable=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class ThesisProgressEvent(Base):
    """Append-only thesis history; milestone ids survive milestone deletion."""

    __tablename__ = "thesis_progress_events"

    id = Column(Integer, primary_key=True)
    thesis_id = Column(
        Integer,
        ForeignKey("thesis_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(40), nullable=False, index=True)
    note = Column(Text, nullable=False, default="")
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    milestone_id = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False, index=True)


class PublicationSubmission(Base):
    """One manuscript's submission lifecycle at a venue."""

    __tablename__ = "publication_submissions"

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(300), nullable=False)
    venue = Column(String(300), nullable=False, default="")
    venue_type = Column(String(30), nullable=False, default="journal")
    status = Column(String(20), nullable=False, default="draft", index=True)
    doi = Column(String(200), nullable=False, default="")
    url = Column(String(500), nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    submitted_at = Column(Integer, nullable=True)
    decision_at = Column(Integer, nullable=True)
    published_at = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class PublicationRevision(Base):
    """One revision round attached to a submission."""

    __tablename__ = "publication_revisions"

    id = Column(Integer, primary_key=True)
    submission_id = Column(
        Integer,
        ForeignKey("publication_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number = Column(Integer, nullable=False)
    notes = Column(Text, nullable=False)
    submitted_at = Column(Integer, nullable=False)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "revision_number",
            name="uq_publication_revisions_submission_number",
        ),
    )


class PublicationStatusEvent(Base):
    """Append-only record of one submission status transition."""

    __tablename__ = "publication_status_events"

    id = Column(Integer, primary_key=True)
    submission_id = Column(
        Integer,
        ForeignKey("publication_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_status = Column(String(20), nullable=False)
    to_status = Column(String(20), nullable=False, index=True)
    note = Column(Text, nullable=False, default="")
    created_at = Column(Integer, nullable=False, index=True)


class RoadmapProgress(Base):
    """One completed or re-opened milestone for a student and researcher."""

    __tablename__ = "roadmap_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    researcher_id = Column(
        Integer,
        ForeignKey("researchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill = Column(String(150), nullable=False)
    milestone_index = Column(Integer, nullable=False)
    is_completed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "researcher_id",
            "skill",
            "milestone_index",
            name="uq_roadmap_progress_milestone",
        ),
    )


class Institution(Base):
    """A university or research institution used to scope lab records."""

    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    created_at = Column(Integer, nullable=False)


class InstitutionMembership(Base):
    """One account's affiliation with one institution.

    Affiliations are provisioned by a platform administrator. A user belongs
    to at most one institution, which keeps lab and collaboration scoping
    unambiguous.
    """

    __tablename__ = "institution_memberships"

    id = Column(Integer, primary_key=True)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at = Column(Integer, nullable=False)


class ResearchLab(Base):
    """An institution-scoped lab directory entry, separate from teams/groups."""

    __tablename__ = "research_labs"

    id = Column(Integer, primary_key=True)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    research_areas = Column(Text, nullable=False, default="")
    visibility = Column(
        String(20), nullable=False, default="institution", index=True
    )
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "institution_id", "name", name="uq_research_labs_institution_name"
        ),
    )


class ResearchLabMember(Base):
    __tablename__ = "research_lab_members"

    id = Column(Integer, primary_key=True)
    lab_id = Column(
        Integer,
        ForeignKey("research_labs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "lab_id", "user_id", name="uq_research_lab_members_lab_user"
        ),
    )


class InterUniversityCollaboration(Base):
    """A proposed or active collaboration between labs at two institutions."""

    __tablename__ = "interuniversity_collaborations"

    id = Column(Integer, primary_key=True)
    requester_lab_id = Column(
        Integer,
        ForeignKey("research_labs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    partner_lab_id = Column(
        Integer,
        ForeignKey("research_labs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    initiated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decided_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="proposed", index=True)
    resolution_note = Column(Text, nullable=False, default="")
    responded_at = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)
    # Canonical unordered lab pair ("lowest:highest"). The partial unique index
    # allows one open collaboration per pair regardless of which side proposed.
    pair_key = Column(String(32), nullable=True)

    __table_args__ = (
        Index(
            "uq_interuniversity_collaborations_open_pair",
            "pair_key",
            unique=True,
            sqlite_where=text(
                "pair_key IS NOT NULL AND status IN ('proposed', 'active')"
            ),
            postgresql_where=text(
                "pair_key IS NOT NULL AND status IN ('proposed', 'active')"
            ),
        ),
    )
