import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Researcher, StudentProfile as SavedStudentProfile, User
from ..services.recommendation import (
    RecommendationError,
    generate_recommendations,
)
from ..services.semantic_matching import SemanticMatchingError
from ..services.readiness_roadmap import generate_readiness_roadmap
from ..services.skill_gap import calculate_skill_gap
from ..services.rate_limit import (
    RECOMMENDATION_MAX,
    RECOMMENDATION_WINDOW_SECONDS,
    enforce_rate_limit,
)
from .deps import require_student

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"]
)

logger = logging.getLogger("researchtwin.recommendations")


class StudentProfile(BaseModel):
    research_areas: str = Field(default="", max_length=4000)
    expertise: str = Field(default="", max_length=4000)
    skills: str = Field(default="", max_length=4000)
    projects: str = Field(default="", max_length=4000)
    publications: str = Field(default="", max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)

    model_config = ConfigDict(extra="ignore")


@router.post("/researchers")
def recommend_researchers(
    student: StudentProfile,
    request: Request,
    response: Response,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        db,
        request,
        scope="recommendations",
        identities=(("user", str(user.id)),),
        limit=RECOMMENDATION_MAX,
        window_seconds=RECOMMENDATION_WINDOW_SECONDS,
    )

    profile = (
        db.query(SavedStudentProfile)
        .filter(SavedStudentProfile.user_id == user.id)
        .first()
    )
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="Save your student profile before requesting recommendations",
        )

    student_profile = {
        field: getattr(profile, field)
        for field in (
            "research_areas",
            "expertise",
            "skills",
            "projects",
            "publications",
        )
    }

    try:
        recommendations = generate_recommendations(
            student_profile=student_profile,
            db=db,
            top_k=student.top_k
        )
    except (RecommendationError, SemanticMatchingError) as exc:
        logger.error("Recommendation request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Recommendation service unavailable"
        ) from exc

    response.headers["Deprecation"] = "true"
    response.headers["Link"] = (
        '</students/me/recommendations>; rel="successor-version"'
    )

    return {
        "student_profile": student_profile,
        "recommendations": recommendations
    }


class RoadmapRequest(BaseModel):
    researcher_id: int
    matched_skills: list[str] = Field(default_factory=list)
    skill_gap: list[str] = Field(default_factory=list)


@router.post("/roadmap/researcher")
def create_researcher_roadmap(
    request: RoadmapRequest,
    response: Response,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    researcher = db.query(Researcher).filter(
        Researcher.id == request.researcher_id
    ).first()

    if researcher is None:
        raise HTTPException(
            status_code=404,
            detail="Researcher not found"
        )

    profile = (
        db.query(SavedStudentProfile)
        .filter(SavedStudentProfile.user_id == user.id)
        .first()
    )
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="Save your student profile before generating a roadmap",
        )

    # Skill data is derived from the saved profile and the stored researcher
    # row. The client-submitted skill lists in this body are ignored.
    skill_data = calculate_skill_gap(profile.skills, researcher)

    response.headers["Deprecation"] = "true"
    response.headers["Link"] = (
        f'</students/me/researchers/{researcher.id}/roadmap>; rel="successor-version"'
    )

    return generate_readiness_roadmap(
        researcher={
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department
        },
        matched_skills=skill_data["matched_skills"],
        skill_gap=skill_data["skill_gap"] if skill_data["student_skills_provided"] else []
    )
