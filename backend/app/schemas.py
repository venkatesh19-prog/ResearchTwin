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
