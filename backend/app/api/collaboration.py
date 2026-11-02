import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    CollaborationRequest,
    FacultyResearcherLink,
    Researcher,
    StudentProfile,
    User,
)
from ..schemas import (
    CollaborationDecision,
    CollaborationRequestCreate,
    FacultyResearcherLinkCreate,
)
from ..services.audit import record_event
from ..services.rate_limit import (
    RECOMMENDATION_MAX,
    RECOMMENDATION_WINDOW_SECONDS,
    enforce_rate_limit,
)
from .deps import require_admin, require_faculty, require_student

router = APIRouter(tags=["Collaboration"])

NO_LINK = "Contact an administrator to verify your identity and link your account to a researcher directory record"


def _researcher_brief(researcher: Researcher | None) -> dict:
    if researcher is None:
        return {"id": None, "name": None, "department": None}

    return {
        "id": researcher.id,
        "name": researcher.name,
        "department": researcher.department,
    }


def _request_payload(record: CollaborationRequest, researcher: Researcher | None) -> dict:
    return {
        "id": record.id,
        "researcher_id": record.researcher_id,
        "researcher": _researcher_brief(researcher),
        "message": record.message,
        "status": record.status,
        "faculty_response": record.faculty_response,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "reviewed_at": record.reviewed_at,
    }


def _student_brief(student: User | None, profile: StudentProfile | None) -> dict:
    return {
        "full_name": student.full_name if student else "Unknown student",
        # The account email is deliberately not shared; collaboration runs
        # through this application until an official channel is agreed.
        "research_areas": profile.research_areas if profile else "",
        "expertise": profile.expertise if profile else "",
        "skills": profile.skills if profile else "",
        "projects": profile.projects if profile else "",
        "publications": profile.publications if profile else "",
        "courses": profile.courses if profile else "",
        "academic_details": profile.academic_details if profile else "",
    }


def _link_for(db: Session, faculty_id: int) -> FacultyResearcherLink | None:
    return (
        db.query(FacultyResearcherLink)
        .filter(FacultyResearcherLink.faculty_user_id == faculty_id)
        .first()
    )


# --------------------------------------------------
# STUDENT SIDE
# --------------------------------------------------

@router.post("/students/me/collaboration-requests", status_code=201)
def create_my_collaboration_request(
    payload: CollaborationRequestCreate,
    http_request: Request,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        db,
        http_request,
        scope="collaboration-requests",
        identities=(("user", str(user.id)),),
        limit=RECOMMENDATION_MAX,
        window_seconds=RECOMMENDATION_WINDOW_SECONDS,
    )

    researcher = (
        db.query(Researcher)
        .filter(Researcher.id == payload.researcher_id)
        .first()
    )

    if researcher is None:
        raise HTTPException(status_code=404, detail="Researcher not found")

    existing = (
        db.query(CollaborationRequest)
        .filter(
            CollaborationRequest.student_user_id == user.id,
            CollaborationRequest.researcher_id == researcher.id,
            CollaborationRequest.status == "pending",
        )
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending request with this researcher",
        )

    now = int(time.time())
    record = CollaborationRequest(
        student_user_id=user.id,
        researcher_id=researcher.id,
        message=payload.message,
        status="pending",
        faculty_response="",
        created_at=now,
        updated_at=now,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return _request_payload(record, researcher)


@router.get("/students/me/collaboration-requests")
def list_my_collaboration_requests(
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    records = (
        db.query(CollaborationRequest)
        .filter(CollaborationRequest.student_user_id == user.id)
        .order_by(CollaborationRequest.created_at.desc())
        .all()
    )

    researchers = {
        researcher.id: researcher
        for researcher in db.query(Researcher).filter(
            Researcher.id.in_({record.researcher_id for record in records})
        ).all()
    } if records else {}

    return {
        "requests": [
            _request_payload(record, researchers.get(record.researcher_id))
            for record in records
        ]
    }


# --------------------------------------------------
# ADMIN ASSIGNMENT
# --------------------------------------------------

@router.put("/admin/faculty/{faculty_user_id}/researcher-link")
def assign_faculty_researcher_link(
    faculty_user_id: int,
    payload: FacultyResearcherLinkCreate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.get(User, faculty_user_id)
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty account not found")
    if faculty.role != "faculty" or not faculty.is_active:
        raise HTTPException(status_code=422, detail="Target must be an active faculty account")

    researcher = (
        db.query(Researcher)
        .filter(Researcher.id == payload.researcher_id)
        .first()
    )

    if researcher is None:
        raise HTTPException(status_code=404, detail="Researcher not found")

    link = _link_for(db, faculty_user_id)
    if link is not None:
        if link.researcher_id != researcher.id:
            raise HTTPException(
                status_code=409,
                detail="This faculty account is already linked to another researcher record",
            )
        return {"linked": True, "researcher": _researcher_brief(researcher)}

    taken = (
        db.query(FacultyResearcherLink)
        .filter(FacultyResearcherLink.researcher_id == researcher.id)
        .first()
    )

    if taken is not None:
        raise HTTPException(
            status_code=409,
            detail="This researcher record is already linked to another account",
        )

    db.add(FacultyResearcherLink(
        faculty_user_id=faculty_user_id,
        researcher_id=researcher.id,
        created_at=int(time.time()),
    ))
    record_event(
        db,
        actor=user,
        action="faculty_link.assign",
        target_type="faculty_user",
        target_id=faculty_user_id,
        detail={"researcher_id": researcher.id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This faculty account or researcher record is already linked",
        ) from exc

    return {"linked": True, "researcher": _researcher_brief(researcher)}


@router.delete("/admin/faculty/{faculty_user_id}/researcher-link")
def remove_faculty_researcher_link(
    faculty_user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    link = _link_for(db, faculty_user_id)

    if link is None:
        raise HTTPException(
            status_code=404,
            detail="No researcher link exists for that faculty account",
        )

    researcher_id = link.researcher_id
    db.delete(link)
    record_event(
        db,
        actor=user,
        action="faculty_link.remove",
        target_type="faculty_user",
        target_id=faculty_user_id,
        detail={"researcher_id": researcher_id},
    )
    db.commit()

    return {"linked": False}


# --------------------------------------------------
# FACULTY SIDE
# --------------------------------------------------

@router.put("/faculty/me/researcher-link")
def set_my_researcher_link(
    payload: FacultyResearcherLinkCreate,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    # Public faculty registration cannot prove directory-record ownership.
    link = _link_for(db, user.id)
    if link is None or link.researcher_id != payload.researcher_id:
        raise HTTPException(status_code=403, detail=NO_LINK)

    researcher = db.get(Researcher, link.researcher_id)
    if researcher is None:
        raise HTTPException(status_code=404, detail="Researcher not found")

    return {"linked": True, "researcher": _researcher_brief(researcher)}


@router.get("/faculty/me/researcher-link")
def get_my_researcher_link(
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    link = _link_for(db, user.id)

    if link is None:
        return {"linked": False, "researcher": None}

    researcher = db.get(Researcher, link.researcher_id)

    return {"linked": True, "researcher": _researcher_brief(researcher)}


@router.get("/faculty/me/collaboration-requests")
def list_faculty_collaboration_requests(
    status: Literal["pending", "accepted", "rejected"] | None = None,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    link = _link_for(db, user.id)

    if link is None:
        raise HTTPException(status_code=400, detail=NO_LINK)

    query = db.query(CollaborationRequest).filter(
        CollaborationRequest.researcher_id == link.researcher_id
    )

    if status:
        query = query.filter(CollaborationRequest.status == status)

    records = query.order_by(CollaborationRequest.created_at.desc()).all()

    students = {
        student.id: student
        for student in db.query(User).filter(
            User.id.in_({record.student_user_id for record in records})
        ).all()
    } if records else {}

    profiles = {
        profile.user_id: profile
        for profile in db.query(StudentProfile).filter(
            StudentProfile.user_id.in_({record.student_user_id for record in records})
        ).all()
    } if records else {}

    researcher = db.get(Researcher, link.researcher_id)

    return {
        "researcher": _researcher_brief(researcher),
        "requests": [
            {
                **_request_payload(record, researcher),
                "student": _student_brief(
                    students.get(record.student_user_id),
                    profiles.get(record.student_user_id),
                ),
            }
            for record in records
        ]
    }


@router.put("/faculty/me/collaboration-requests/{request_id}/decision")
def decide_collaboration_request(
    request_id: int,
    payload: CollaborationDecision,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    link = _link_for(db, user.id)

    if link is None:
        raise HTTPException(status_code=400, detail=NO_LINK)

    record = db.get(CollaborationRequest, request_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Request not found")

    if record.researcher_id != link.researcher_id:
        raise HTTPException(
            status_code=403,
            detail="You can only respond to requests addressed to your linked record",
        )

    now = int(time.time())
    result = db.execute(
        update(CollaborationRequest)
        .where(
            CollaborationRequest.id == request_id,
            CollaborationRequest.researcher_id == link.researcher_id,
            CollaborationRequest.status == "pending",
        )
        .values(
            status="accepted" if payload.decision == "accept" else "rejected",
            faculty_response=payload.response,
            reviewed_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This request has already been reviewed")

    record_event(
        db,
        actor=user,
        action="collaboration.decision",
        target_type="collaboration_request",
        target_id=request_id,
        detail={
            "decision": payload.decision,
            "researcher_id": link.researcher_id,
        },
    )
    db.commit()
    db.refresh(record)

    researcher = db.get(Researcher, record.researcher_id)

    return _request_payload(record, researcher)
