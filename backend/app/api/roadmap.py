import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Researcher, RoadmapProgress, StudentProfile, User
from ..schemas import RoadmapProgressUpdate
from ..services.expertise_gap import analyze as analyze_expertise_gaps
from ..services.readiness_roadmap import build_student_roadmap
from ..services.skill_gap import calculate_skill_gap
from ..services.verification import latest_by_researcher
from .deps import require_student

router = APIRouter(tags=["Roadmap"])


def _get_profile(db: Session, user_id: int) -> StudentProfile:
    profile = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == user_id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="Save your student profile before generating a roadmap",
        )

    return profile


def _get_researcher(db: Session, researcher_id: int) -> Researcher:
    researcher = (
        db.query(Researcher)
        .filter(Researcher.id == researcher_id)
        .first()
    )

    if researcher is None:
        raise HTTPException(status_code=404, detail="Researcher not found")

    return researcher


def _completed_milestones(
    db: Session,
    user_id: int,
    researcher_id: int,
) -> set[tuple[str, int]]:
    rows = (
        db.query(RoadmapProgress)
        .filter(
            RoadmapProgress.user_id == user_id,
            RoadmapProgress.researcher_id == researcher_id,
            RoadmapProgress.is_completed.is_(True),
        )
        .all()
    )

    return {(row.skill, row.milestone_index) for row in rows}


def _roadmap(
    db: Session,
    user: User,
    profile: StudentProfile,
    researcher: Researcher,
) -> dict:
    """Build the roadmap from the saved profile and the stored researcher row.

    Skill data is never taken from the request body, so a client cannot
    invent matched skills or gaps.
    """
    skill_data = calculate_skill_gap(profile.skills, researcher)

    return build_student_roadmap(
        researcher={
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department,
        },
        skill_data=skill_data,
        completed_milestones=_completed_milestones(
            db, user.id, researcher.id
        ),
    )


@router.get("/students/me/expertise-gaps")
def get_my_expertise_gaps(
    limit: int = Query(default=25, ge=1, le=100),
    verified_only: bool = False,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    """Compare the saved profile with the whole directory, not one researcher."""
    profile = _get_profile(db, user.id)
    researchers = db.query(Researcher).order_by(Researcher.id).all()
    verification = latest_by_researcher(
        db, [researcher.id for researcher in researchers]
    )

    return analyze_expertise_gaps(
        profile,
        researchers,
        verification,
        limit=limit,
        verified_only=verified_only,
    )


@router.get("/students/me/researchers/{researcher_id}/roadmap")
def get_my_researcher_roadmap(
    researcher_id: int,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _get_profile(db, user.id)
    researcher = _get_researcher(db, researcher_id)

    return _roadmap(db, user, profile, researcher)


@router.put("/students/me/researchers/{researcher_id}/roadmap/progress")
def update_my_roadmap_progress(
    researcher_id: int,
    payload: RoadmapProgressUpdate,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _get_profile(db, user.id)
    researcher = _get_researcher(db, researcher_id)

    roadmap = _roadmap(db, user, profile, researcher)

    item = next(
        (
            candidate
            for candidate in roadmap["skill_gaps"]
            if candidate["skill"] == payload.skill
        ),
        None,
    )

    if item is None or payload.milestone_index >= item["milestones_total"]:
        raise HTTPException(
            status_code=404,
            detail="That milestone is not part of your current roadmap",
        )

    skill = item["skill"]
    now = int(time.time())

    dialect = db.get_bind().dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise HTTPException(status_code=503, detail="Progress storage is unavailable")
    insert = postgresql_insert if dialect == "postgresql" else sqlite_insert
    statement = insert(RoadmapProgress).values(
        user_id=user.id,
        researcher_id=researcher_id,
        skill=skill,
        milestone_index=payload.milestone_index,
        is_completed=payload.completed,
        updated_at=now,
    )
    db.execute(statement.on_conflict_do_update(
        index_elements=["user_id", "researcher_id", "skill", "milestone_index"],
        set_={"is_completed": payload.completed, "updated_at": now},
    ))
    db.commit()

    return _roadmap(db, user, profile, researcher)
