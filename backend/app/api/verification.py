"""Public verification status, faculty submissions and admin review."""

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..database import get_db
from ..models import (
    FacultyResearcherLink,
    Researcher,
    ResearcherVerification,
    User,
)
from ..schemas import VerificationDecision, VerificationSubmitRequest
from ..services import verification
from ..services.rate_limit import enforce_rate_limit
from .collaboration import NO_LINK
from .deps import require_admin, require_faculty

router = APIRouter(tags=["Researcher Verification"])

VERIFICATION_MAX = 5
VERIFICATION_WINDOW_SECONDS = 3600

StatusName = Literal["unverified", "pending", "verified", "rejected", "expired"]


def _link_for(db: Session, faculty_id: int) -> FacultyResearcherLink | None:
    return (
        db.query(FacultyResearcherLink)
        .filter(FacultyResearcherLink.faculty_user_id == faculty_id)
        .first()
    )


def _admin_payloads(
    db: Session, records: list[ResearcherVerification]
) -> list[dict]:
    researcher_names = {
        researcher.id: researcher.name
        for researcher in db.query(Researcher)
        .filter(Researcher.id.in_({record.researcher_id for record in records}))
        .all()
    } if records else {}

    user_ids = set()
    for record in records:
        if record.submitted_by_user_id is not None:
            user_ids.add(record.submitted_by_user_id)
        if record.reviewed_by_user_id is not None:
            user_ids.add(record.reviewed_by_user_id)
    emails = {
        user.id: user.email
        for user in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    now = int(time.time())
    return [
        verification.admin_payload(
            record,
            researcher_name=researcher_names.get(record.researcher_id),
            submitted_by_email=emails.get(record.submitted_by_user_id),
            reviewed_by_email=emails.get(record.reviewed_by_user_id),
            now=now,
        )
        for record in records
    ]


# --------------------------------------------------
# PUBLIC STATUS
# --------------------------------------------------

@router.get("/researchers/verification-summary")
def verification_summary(
    status: StatusName | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    latest_id_for = (
        select(func.max(ResearcherVerification.id))
        .where(ResearcherVerification.researcher_id == Researcher.id)
        .scalar_subquery()
    )
    latest = aliased(ResearcherVerification)
    query = db.query(Researcher.id, latest).outerjoin(
        latest, latest.id == latest_id_for
    )

    now = int(time.time())
    if status is not None:
        verified = latest.status == "verified"
        expired = and_(
            verified,
            latest.expires_at.is_not(None),
            latest.expires_at <= now,
        )
        if status == "unverified":
            query = query.filter(latest.id.is_(None))
        elif status == "expired":
            query = query.filter(expired)
        elif status == "verified":
            query = query.filter(
                verified,
                or_(latest.expires_at.is_(None), latest.expires_at > now),
            )
        else:
            query = query.filter(latest.status == status)

    total = query.order_by(None).count()
    rows = (
        query.order_by(Researcher.id).offset(offset).limit(limit).all()
    )
    return {
        "researchers": [
            verification.public_payload(researcher_id, record, now)
            for researcher_id, record in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/researchers/{researcher_id}/verification")
def researcher_verification_status(
    researcher_id: int,
    db: Session = Depends(get_db),
):
    researcher = db.get(Researcher, researcher_id)
    if researcher is None:
        raise HTTPException(status_code=404, detail="Researcher not found")

    latest = verification.latest_by_researcher(db, [researcher_id])
    return verification.public_payload(researcher_id, latest.get(researcher_id))


# --------------------------------------------------
# FACULTY SUBMISSION
# --------------------------------------------------

@router.get("/faculty/me/researcher-link/verification")
def my_researcher_verification(
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    link = _link_for(db, user.id)
    if link is None:
        raise HTTPException(status_code=400, detail=NO_LINK)

    latest = verification.latest_by_researcher(db, [link.researcher_id])
    return verification.owner_payload(
        link.researcher_id, latest.get(link.researcher_id)
    )


@router.post("/faculty/me/researcher-link/verification", status_code=201)
def submit_researcher_verification(
    payload: VerificationSubmitRequest,
    http_request: Request,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        db,
        http_request,
        scope="researcher-verification",
        identities=(("user", str(user.id)),),
        limit=VERIFICATION_MAX,
        window_seconds=VERIFICATION_WINDOW_SECONDS,
    )

    link = _link_for(db, user.id)
    if link is None:
        raise HTTPException(status_code=400, detail=NO_LINK)

    record = verification.submit(
        db,
        faculty=user,
        researcher_id=link.researcher_id,
        evidence_reference=payload.evidence_reference,
        note=payload.note,
    )
    return verification.submission_payload(record)


# --------------------------------------------------
# ADMIN REVIEW
# --------------------------------------------------

@router.get("/admin/verifications")
def list_verification_requests(
    status: StatusName | None = None,
    researcher_id: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(ResearcherVerification)
    if researcher_id is not None:
        query = query.filter(ResearcherVerification.researcher_id == researcher_id)

    now = int(time.time())
    if status is not None:
        verified = ResearcherVerification.status == "verified"
        expired = and_(
            verified,
            ResearcherVerification.expires_at.is_not(None),
            ResearcherVerification.expires_at <= now,
        )
        if status == "expired":
            query = query.filter(expired)
        elif status == "verified":
            query = query.filter(
                verified,
                or_(
                    ResearcherVerification.expires_at.is_(None),
                    ResearcherVerification.expires_at > now,
                ),
            )
        else:
            query = query.filter(ResearcherVerification.status == status)

    total = query.order_by(None).count()
    records = (
        query.order_by(ResearcherVerification.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "verifications": _admin_payloads(db, records),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/admin/researchers/{researcher_id}/verifications")
def researcher_verification_history(
    researcher_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    researcher = db.get(Researcher, researcher_id)
    if researcher is None:
        raise HTTPException(status_code=404, detail="Researcher not found")

    records = (
        db.query(ResearcherVerification)
        .filter(ResearcherVerification.researcher_id == researcher_id)
        .order_by(ResearcherVerification.id.desc())
        .all()
    )

    return {
        "researcher_id": researcher_id,
        "researcher_name": researcher.name,
        "verifications": _admin_payloads(db, records),
        "total": len(records),
    }


@router.put("/admin/verifications/{verification_id}")
def decide_verification_request(
    verification_id: int,
    payload: VerificationDecision,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = verification.decide(
        db,
        admin=admin,
        verification_id=verification_id,
        decision=payload.decision,
        review_note=payload.review_note,
        expires_in_days=payload.expires_in_days,
    )
    return _admin_payloads(db, [record])[0]
