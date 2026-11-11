import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class ResearcherBase(BaseModel):
    name: str
    department: Optional[str] = None
    designation: Optional[str] = None
    experience: Optional[int] = None

    research_areas: Optional[str] = None
    expertise: Optional[str] = None
    skills: Optional[str] = None

    publications: Optional[str] = None
    projects: Optional[str] = None

    profile_url: Optional[str] = None


class ResearcherCreate(ResearcherBase):
    name: str = Field(min_length=1, max_length=100)
    department: Optional[str] = Field(default=None, max_length=150)
    designation: Optional[str] = Field(default=None, max_length=100)
    experience: Optional[int] = Field(default=None, ge=0, le=80)
    research_areas: Optional[str] = Field(default=None, max_length=10000)
    expertise: Optional[str] = Field(default=None, max_length=10000)
    skills: Optional[str] = Field(default=None, max_length=10000)
    publications: Optional[str] = Field(default=None, max_length=20000)
    projects: Optional[str] = Field(default=None, max_length=20000)
    profile_url: Optional[str] = Field(default=None, max_length=300)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Researcher name is required")
        return value

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        from urllib.parse import urlparse

        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Profile URL must use http or https")
        return value.strip()


class ResearcherResponse(ResearcherBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["student", "faculty"]

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name is required")
        return value

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password is required")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    user: UserResponse


class StudentProfilePayload(BaseModel):
    research_areas: str = Field(default="", max_length=4000)
    expertise: str = Field(default="", max_length=4000)
    skills: str = Field(default="", max_length=4000)
    projects: str = Field(default="", max_length=4000)
    publications: str = Field(default="", max_length=4000)
    courses: str = Field(default="", max_length=4000)
    academic_details: str = Field(default="", max_length=4000)

    model_config = ConfigDict(extra="forbid")


class StudentProfileResponse(StudentProfilePayload):
    profile_completion: int
    updated_at: Optional[int] = None


class FacultyProfilePayload(BaseModel):
    department: str = Field(default="", max_length=150)
    designation: str = Field(default="", max_length=100)
    research_areas: str = Field(default="", max_length=4000)
    expertise: str = Field(default="", max_length=4000)
    skills: str = Field(default="", max_length=4000)
    publications: str = Field(default="", max_length=4000)
    projects: str = Field(default="", max_length=4000)
    profile_url: str = Field(default="", max_length=300)

    model_config = ConfigDict(extra="forbid")

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str) -> str:
        return ResearcherCreate.validate_profile_url(value) or ""


class FacultyProfileResponse(FacultyProfilePayload):
    profile_completion: int
    updated_at: Optional[int] = None


class ProfileRecommendationRequest(BaseModel):
    top_k: int = Field(default=5, ge=1, le=10)


class RoadmapProgressUpdate(BaseModel):
    skill: str = Field(min_length=1, max_length=150)
    milestone_index: int = Field(ge=0, le=20)
    completed: bool

    model_config = ConfigDict(extra="forbid")


class CollaborationRequestCreate(BaseModel):
    researcher_id: int
    message: str = Field(min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def require_message_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Add a short message for the researcher")
        return value


class FacultyResearcherLinkCreate(BaseModel):
    researcher_id: int

    model_config = ConfigDict(extra="forbid")


class CollaborationDecision(BaseModel):
    decision: Literal["accept", "reject"]
    response: str = Field(default="", max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("response")
    @classmethod
    def normalize_response(cls, value: str) -> str:
        return value.strip()


class CollaborationRequestResponse(BaseModel):
    id: int
    researcher_id: int
    researcher_name: Optional[str] = None
    researcher_department: Optional[str] = None
    message: str
    status: str
    faculty_response: str
    created_at: int
    updated_at: int
    reviewed_at: Optional[int] = None


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: int

    model_config = ConfigDict(from_attributes=True)


class AccountStatusUpdate(BaseModel):
    active: bool

    model_config = ConfigDict(extra="forbid")


class AccountRoleUpdate(BaseModel):
    role: Literal["student", "faculty", "admin"]

    model_config = ConfigDict(extra="forbid")


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password is required")
        return value


class GroupResponse(BaseModel):
    id: int
    name: str
    member_count: int
    created_at: int


class GroupMemberResponse(BaseModel):
    membership_id: int
    user_id: int
    email: str
    full_name: str
    role: str
    created_at: int


class GroupMembershipCreate(BaseModel):
    user_id: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class AuditEventResponse(BaseModel):
    id: int
    actor_user_id: Optional[int] = None
    actor_email: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[int] = None
    detail: str
    created_at: int


class VerificationSubmitRequest(BaseModel):
    evidence_reference: str = Field(min_length=3, max_length=2000)
    note: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("evidence_reference")
    @classmethod
    def require_evidence(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Provide a verifiable evidence reference")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()


class VerificationDecision(BaseModel):
    decision: Literal["verify", "reject"]
    review_note: str = Field(default="", max_length=2000)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)

    model_config = ConfigDict(extra="forbid")

    @field_validator("review_note")
    @classmethod
    def normalize_review_note(cls, value: str) -> str:
        return value.strip()


class WorkspaceTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    assignee_user_id: Optional[int] = Field(default=None, ge=1)
    due_at: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task title is required")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class WorkspaceTaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[Literal["todo", "in_progress", "done"]] = None
    assignee_user_id: Optional[int] = Field(default=None, ge=1)
    due_at: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Task title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Task title cannot be blank")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Use an empty string to clear the description")
        return value.strip()

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Task status cannot be cleared")
        return value


class WorkspaceCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    task_id: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("body")
    @classmethod
    def require_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Comment text is required")
        return value


class WorkspaceMilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Milestone title is required")
        return value


class WorkspaceMilestoneUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[Literal["pending", "completed"]] = None
    due_at: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Milestone title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Milestone title cannot be blank")
        return value

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Milestone status cannot be cleared")
        return value


class ResearchTeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    research_areas: str = Field(default="", max_length=4000)
    expertise: str = Field(default="", max_length=4000)
    skills: str = Field(default="", max_length=4000)
    projects: str = Field(default="", max_length=4000)
    publications: str = Field(default="", max_length=4000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Team name is required")
        return value

    @field_validator(
        "description",
        "research_areas",
        "expertise",
        "skills",
        "projects",
        "publications",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class ResearchTeamInvitationCreate(BaseModel):
    user_id: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class ResearchTeamInvitationDecision(BaseModel):
    decision: Literal["accept", "decline"]

    model_config = ConfigDict(extra="forbid")


class TeamRecommendationRequest(BaseModel):
    top_k: int = Field(default=5, ge=1, le=10)


class OpportunityCreate(BaseModel):
    category: Literal["research", "funding"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    organization: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=150)
    url: str = Field(default="", max_length=300)
    deadline_at: Optional[int] = Field(default=None, ge=0)
    status: Literal["draft", "open", "closed"] = "open"
    researcher_id: Optional[int] = Field(default=None, ge=1)
    required_skills: str = Field(default="", max_length=4000)
    required_research_areas: str = Field(default="", max_length=4000)
    required_expertise: str = Field(default="", max_length=4000)
    eligibility: str = Field(default="", max_length=4000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Opportunity title is required")
        return value

    @field_validator(
        "description",
        "organization",
        "location",
        "required_skills",
        "required_research_areas",
        "required_expertise",
        "eligibility",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return ResearcherCreate.validate_profile_url(value) or ""


class OpportunityUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    organization: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=150)
    url: Optional[str] = Field(default=None, max_length=300)
    deadline_at: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["draft", "open", "closed"]] = None
    required_skills: Optional[str] = Field(default=None, max_length=4000)
    required_research_areas: Optional[str] = Field(default=None, max_length=4000)
    required_expertise: Optional[str] = Field(default=None, max_length=4000)
    eligibility: Optional[str] = Field(default=None, max_length=4000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Opportunity title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Opportunity title cannot be blank")
        return value

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Opportunity status cannot be cleared")
        return value

    @field_validator(
        "description",
        "organization",
        "location",
        "required_skills",
        "required_research_areas",
        "required_expertise",
        "eligibility",
    )
    @classmethod
    def normalize_clearable_text(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return ResearcherCreate.validate_profile_url(value) or ""


class OpportunityApplicationCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def require_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Add a short message for the opportunity owner")
        return value


class OpportunityApplicationDecision(BaseModel):
    decision: Literal["accept", "reject"]
    note: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()


class OpportunityMatchRequest(BaseModel):
    category: Literal["research", "funding"] = "research"
    top_k: int = Field(default=5, ge=1, le=20)
    eligible_only: bool = False

    model_config = ConfigDict(extra="forbid")


class FundingImportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)

    model_config = ConfigDict(extra="forbid")

    @field_validator("source", "query")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value


class ClusterRebuildRequest(BaseModel):
    min_similarity: float = Field(default=0.18, ge=0.05, le=0.95)
    use_semantic: bool = True

    model_config = ConfigDict(extra="forbid")


class TopicPredictionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=10)

    model_config = ConfigDict(extra="forbid")

    @field_validator("text")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Provide text to classify")
        return value


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        value = tag.strip().lower()
        if not value:
            raise ValueError("Tags cannot be blank")
        if len(value) > 50:
            raise ValueError("Each tag must be 50 characters or fewer")
        if value not in normalized:
            normalized.append(value)
    return normalized


class LiteratureEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    authors: str = Field(default="", max_length=2000)
    venue: str = Field(default="", max_length=300)
    year: Optional[int] = Field(default=None, ge=1800, le=2100)
    doi: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    review_status: Literal["to_read", "reading", "reviewed", "archived"] = "to_read"
    citation_key: Optional[str] = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Literature title is required")
        return value

    @field_validator("authors", "venue", "doi", "abstract", "notes")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return ResearcherCreate.validate_profile_url(value) or ""

    @field_validator("citation_key")
    @classmethod
    def normalize_citation_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)


class LiteratureEntryUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    authors: Optional[str] = Field(default=None, max_length=2000)
    venue: Optional[str] = Field(default=None, max_length=300)
    year: Optional[int] = Field(default=None, ge=1800, le=2100)
    doi: Optional[str] = Field(default=None, max_length=200)
    url: Optional[str] = Field(default=None, max_length=500)
    abstract: Optional[str] = Field(default=None, max_length=10000)
    notes: Optional[str] = Field(default=None, max_length=20000)
    tags: Optional[list[str]] = Field(default=None, max_length=20)
    review_status: Optional[
        Literal["to_read", "reading", "reviewed", "archived"]
    ] = None
    citation_key: Optional[str] = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Literature title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Literature title cannot be blank")
        return value

    @field_validator("authors", "venue", "doi", "abstract", "notes")
    @classmethod
    def normalize_clearable_text(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return ResearcherCreate.validate_profile_url(value) or ""

    @field_validator("review_status")
    @classmethod
    def normalize_review_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Review status cannot be cleared")
        return value

    @field_validator("citation_key")
    @classmethod
    def normalize_citation_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: Optional[list[str]]) -> list[str]:
        if value is None:
            return []
        return _normalize_tags(value)


class ResearchProposalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Proposal title is required")
        return value


class ResearchProposalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[Literal["draft", "submitted", "archived"]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Proposal title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Proposal title cannot be blank")
        return value

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Proposal status cannot be cleared")
        return value


class ProposalSectionCreate(BaseModel):
    heading: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("heading")
    @classmethod
    def require_heading(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Section heading is required")
        return value

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        return value.strip()


class ProposalSectionUpdate(BaseModel):
    heading: Optional[str] = Field(default=None, min_length=1, max_length=200)
    body: Optional[str] = Field(default=None, max_length=20000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("heading")
    @classmethod
    def normalize_heading(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Section heading cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Section heading cannot be blank")
        return value

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()


class ProposalCollaboratorCreate(BaseModel):
    user_id: int = Field(ge=1)
    role: Literal["editor", "viewer"] = "viewer"

    model_config = ConfigDict(extra="forbid")


class ProposalCitationCreate(BaseModel):
    literature_entry_id: int = Field(ge=1)
    section_id: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class ThesisCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    abstract: str = Field(default="", max_length=20000)
    supervisor_user_id: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Thesis title is required")
        return value

    @field_validator("abstract")
    @classmethod
    def normalize_abstract(cls, value: str) -> str:
        return value.strip()


class ThesisUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    abstract: Optional[str] = Field(default=None, max_length=20000)
    supervisor_user_id: Optional[int] = Field(default=None, ge=1)
    status: Optional[
        Literal[
            "proposed",
            "in_progress",
            "submitted",
            "defended",
            "completed",
            "withdrawn",
        ]
    ] = None
    note: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Thesis title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Thesis title cannot be blank")
        return value

    @field_validator("abstract", "note")
    @classmethod
    def normalize_clearable_text(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Thesis status cannot be cleared")
        return value


class ThesisMilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Milestone title is required")
        return value


class ThesisMilestoneUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    due_at: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["pending", "completed"]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Milestone title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Milestone title cannot be blank")
        return value

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Milestone status cannot be cleared")
        return value


class PublicationSubmissionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    venue: str = Field(default="", max_length=300)
    venue_type: Literal[
        "journal", "conference", "workshop", "book_chapter", "other"
    ] = "journal"
    doi: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=20000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Submission title is required")
        return value

    @field_validator("venue", "doi", "notes")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return ResearcherCreate.validate_profile_url(value) or ""


class PublicationSubmissionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    venue: Optional[str] = Field(default=None, max_length=300)
    venue_type: Optional[
        Literal["journal", "conference", "workshop", "book_chapter", "other"]
    ] = None
    doi: Optional[str] = Field(default=None, max_length=200)
    url: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=20000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Submission title cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Submission title cannot be blank")
        return value

    @field_validator("venue", "doi", "notes")
    @classmethod
    def normalize_clearable_text(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("venue_type")
    @classmethod
    def normalize_venue_type(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Venue type cannot be cleared")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return ResearcherCreate.validate_profile_url(value) or ""


class PublicationStatusUpdate(BaseModel):
    status: Literal[
        "draft",
        "submitted",
        "under_review",
        "revision_requested",
        "accepted",
        "rejected",
        "published",
        "withdrawn",
    ]
    note: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()


class PublicationRevisionCreate(BaseModel):
    notes: str = Field(min_length=1, max_length=10000)
    submitted_at: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("notes")
    @classmethod
    def require_notes(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Describe the revision")
        return value


class AccountDataExport(BaseModel):
    """One account's personal data, without credential or token material."""

    generated_at: int
    account: AdminUserResponse
    student_profile: Optional[dict] = None
    faculty_profile: Optional[dict] = None
    faculty_link: Optional[dict] = None
    collaboration_requests: list[dict]
    faculty_inbox: list[dict]
    roadmap_progress: list[dict]
    sessions: dict
    audit_events: list[dict]


class InstitutionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Institution name is required")
        return value


class InstitutionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Institution name is required")
        return value


class ResearchLabCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    research_areas: str = Field(default="", max_length=2000)
    visibility: Literal["public", "institution"] = "institution"

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Lab name is required")
        return value

    @field_validator("description", "research_areas")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class ResearchLabUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    research_areas: Optional[str] = Field(default=None, max_length=2000)
    visibility: Optional[Literal["public", "institution"]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Lab name cannot be cleared")
        value = value.strip()
        if not value:
            raise ValueError("Lab name cannot be blank")
        return value

    @field_validator("description", "research_areas")
    @classmethod
    def normalize_clearable_text(cls, value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("visibility")
    @classmethod
    def normalize_visibility(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Visibility cannot be cleared")
        return value


class ResearchLabMemberCreate(BaseModel):
    user_id: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class InterUniversityCollaborationCreate(BaseModel):
    requester_lab_id: int = Field(ge=1)
    partner_lab_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Collaboration title is required")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class InterUniversityCollaborationStatusUpdate(BaseModel):
    status: Literal["active", "declined", "completed", "withdrawn"]
    note: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()


class SearchHistoryCreate(BaseModel):
    query: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Search text is required")
        return value


class SearchHistoryResponse(BaseModel):
    id: int
    query: str
    created_at: int

    model_config = ConfigDict(from_attributes=True)
