from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .database import Base


class Researcher(Base):
    __tablename__ = "researchers"

    id = Column(Integer, primary_key=True, index=True)

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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), nullable=False, unique=True, index=True)
    full_name = Column(String(120), nullable=False)
    role = Column(String(20), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(Integer, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
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


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"

    bucket_hash = Column(String(64), primary_key=True)
    window_start = Column(Integer, nullable=False)
    count = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False, index=True)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, index=True)
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

    id = Column(Integer, primary_key=True, index=True)
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

    id = Column(Integer, primary_key=True, index=True)
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

    id = Column(Integer, primary_key=True, index=True)
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


class RoadmapProgress(Base):
    """One completed or re-opened milestone for a student and researcher."""

    __tablename__ = "roadmap_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
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
