import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FacultyProfile, FacultyResearcherLink, Researcher, StudentProfile
from ..schemas import (
    FacultyProfilePayload,
    FacultyProfileResponse,
    ProfileRecommendationRequest,
    StudentProfilePayload,
    StudentProfileResponse,
)
from ..services.recommendation import (
    RecommendationError,
    generate_recommendations,
)
from ..services.semantic_matching import SemanticMatchingError
from .deps import require_faculty, require_student
from ..services.rate_limit import (
    RECOMMENDATION_MAX,
    RECOMMENDATION_WINDOW_SECONDS,
    enforce_rate_limit,
)

router = APIRouter(tags=["Profiles"])

logger = logging.getLogger("researchtwin.profiles")

STUDENT_PROFILE_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
    "courses",
    "academic_details",
)

RECOMMENDATION_PROFILE_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
)

FACULTY_PROFILE_FIELDS = (
    "department",
    "designation",
    "research_areas",
    "expertise",
    "skills",
    "publications",
    "projects",
    "profile_url",
)


def _completion(values: dict) -> int:
    filled = sum(1 for value in values.values() if str(value).strip())
    return round(filled * 100 / len(values)) if values else 0


def _student_response(profile: StudentProfile | None) -> StudentProfileResponse:
    if profile is None:
        return StudentProfileResponse(profile_completion=0, updated_at=None)

    values = {field: getattr(profile, field) for field in STUDENT_PROFILE_FIELDS}
    return StudentProfileResponse(
        **values,
        profile_completion=_completion(values),
        updated_at=profile.updated_at,
    )


def _faculty_response(profile: FacultyProfile | None) -> FacultyProfileResponse:
    if profile is None:
        return FacultyProfileResponse(profile_completion=0, updated_at=None)

    values = {field: getattr(profile, field) for field in FACULTY_PROFILE_FIELDS}
    return FacultyProfileResponse(
        **values,
        profile_completion=_completion(values),
        updated_at=profile.updated_at,
    )


# --------------------------------------------------
# STUDENT PROFILE
# --------------------------------------------------

@router.get(
    "/students/me/profile",
    response_model=StudentProfileResponse,
)
def get_my_student_profile(
    user=Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == user.id)
        .first()
    )
    return _student_response(profile)


@router.put(
    "/students/me/profile",
    response_model=StudentProfileResponse,
)
def update_my_student_profile(
    payload: StudentProfilePayload,
    user=Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == user.id)
        .first()
    )

    if profile is None:
        profile = StudentProfile(user_id=user.id, updated_at=int(time.time()))
        db.add(profile)

    for field, value in payload.model_dump().items():
        setattr(profile, field, value.strip())

    profile.updated_at = int(time.time())
    db.commit()
    db.refresh(profile)

    return _student_response(profile)


@router.post("/students/me/recommendations")
def recommendations_for_my_profile(
    payload: ProfileRecommendationRequest,
    request: Request,
    user=Depends(require_student),
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
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == user.id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="Save your student profile before requesting recommendations",
        )

    student_profile = {
        field: getattr(profile, field) for field in RECOMMENDATION_PROFILE_FIELDS
    }

    try:
        recommendations = generate_recommendations(
            student_profile=student_profile,
            db=db,
            top_k=payload.top_k,
        )
    except (RecommendationError, SemanticMatchingError) as exc:
        logger.error("Recommendation request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Recommendation service unavailable",
        ) from exc

    return {
        "student_profile": student_profile,
        "profile_completion": _completion(
            {field: getattr(profile, field) for field in STUDENT_PROFILE_FIELDS}
        ),
        "recommendations": recommendations,
    }


# --------------------------------------------------
# FACULTY PROFILE
# --------------------------------------------------

@router.get(
    "/faculty/me/profile",
    response_model=FacultyProfileResponse,
)
def get_my_faculty_profile(
    user=Depends(require_faculty),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(FacultyProfile)
        .filter(FacultyProfile.user_id == user.id)
        .first()
    )
    if profile is None:
        researcher = (
            db.query(Researcher)
            .join(FacultyResearcherLink, FacultyResearcherLink.researcher_id == Researcher.id)
            .filter(FacultyResearcherLink.faculty_user_id == user.id)
            .first()
        )
        if researcher is not None:
            values = {field: getattr(researcher, field) or "" for field in FACULTY_PROFILE_FIELDS}
            return FacultyProfileResponse(**values, profile_completion=_completion(values))
    return _faculty_response(profile)


@router.put(
    "/faculty/me/profile",
    response_model=FacultyProfileResponse,
)
def update_my_faculty_profile(
    payload: FacultyProfilePayload,
    user=Depends(require_faculty),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(FacultyProfile)
        .filter(FacultyProfile.user_id == user.id)
        .first()
    )

    if profile is None:
        profile = FacultyProfile(user_id=user.id, updated_at=int(time.time()))
        db.add(profile)

    for field, value in payload.model_dump().items():
        setattr(profile, field, value.strip())

    profile.updated_at = int(time.time())
    db.commit()
    db.refresh(profile)

    return _faculty_response(profile)
