"""Researcher verification state, submission and review rules.

Each row is one immutable request plus its review; the newest row per
researcher is the current state. Verified rows can carry an expiry, which is
derived into an ``expired`` public status instead of rewriting history.
"""

import time

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ResearcherVerification, User
from .audit import record_event

STATUSES = ("unverified", "pending", "verified", "rejected", "expired")


def effective_status(
    record: ResearcherVerification | None, now: int | None = None
) -> str:
    if record is None:
        return "unverified"
    if record.status == "verified" and record.expires_at is not None:
        now = int(time.time()) if now is None else now
        if record.expires_at <= now:
            return "expired"
    return record.status


def _verified_at(record: ResearcherVerification | None, status: str) -> int | None:
    if record is None or status not in {"verified", "expired"}:
        return None
    return record.reviewed_at


def _visible_expiry(record: ResearcherVerification | None, status: str) -> int | None:
    if record is None or status not in {"verified", "expired"}:
        return None
    return record.expires_at


def latest_by_researcher(
    db: Session, researcher_ids: list[int] | set[int] | None = None
) -> dict[int, ResearcherVerification]:
    """Return the newest verification row for each researcher."""
    query = db.query(ResearcherVerification)
    if researcher_ids is not None:
        ids = list(researcher_ids)
        if not ids:
            return {}
        query = query.filter(ResearcherVerification.researcher_id.in_(ids))

    latest: dict[int, ResearcherVerification] = {}
    for row in query.order_by(ResearcherVerification.id.desc()).all():
        latest.setdefault(row.researcher_id, row)
    return latest


def public_payload(
    researcher_id: int,
    record: ResearcherVerification | None,
    now: int | None = None,
) -> dict:
    """Public status: no evidence, notes or reviewer identity."""
    status = effective_status(record, now)
    return {
        "researcher_id": researcher_id,
        "status": status,
        "verified_at": _verified_at(record, status),
        "expires_at": _visible_expiry(record, status),
    }


def owner_payload(
    researcher_id: int, record: ResearcherVerification | None, now: int | None = None
) -> dict:
    status = effective_status(record, now)
    if record is None:
        return {
            "id": None,
            "researcher_id": researcher_id,
            "status": status,
            "evidence_reference": "",
            "note": "",
            "review_note": "",
            "submitted_at": None,
            "reviewed_at": None,
            "expires_at": None,
            "verified_at": None,
        }
    return {
        "id": record.id,
        "researcher_id": record.researcher_id,
        "status": status,
        "evidence_reference": record.evidence_reference,
        "note": record.note,
        "review_note": record.review_note,
        "submitted_at": record.submitted_at,
        "reviewed_at": record.reviewed_at,
        "expires_at": _visible_expiry(record, status),
        "verified_at": _verified_at(record, status),
    }


def submission_payload(record: ResearcherVerification) -> dict:
    """The submitting faculty member's view of a newly created request."""
    return {
        "id": record.id,
        "researcher_id": record.researcher_id,
        "status": effective_status(record),
        "evidence_reference": record.evidence_reference,
        "note": record.note,
        "review_note": record.review_note,
        "submitted_at": record.submitted_at,
        "reviewed_at": record.reviewed_at,
        "expires_at": record.expires_at,
        "verified_at": None,
    }


def admin_payload(
    record: ResearcherVerification,
    *,
    researcher_name: str | None = None,
    submitted_by_email: str | None = None,
    reviewed_by_email: str | None = None,
    now: int | None = None,
) -> dict:
    status = effective_status(record, now)
    return {
        "id": record.id,
        "researcher_id": record.researcher_id,
        "researcher_name": researcher_name,
        "status": status,
        "evidence_reference": record.evidence_reference,
        "note": record.note,
        "review_note": record.review_note,
        "submitted_by_user_id": record.submitted_by_user_id,
        "submitted_by_email": submitted_by_email,
        "reviewed_by_user_id": record.reviewed_by_user_id,
        "reviewed_by_email": reviewed_by_email,
        "submitted_at": record.submitted_at,
        "reviewed_at": record.reviewed_at,
        "expires_at": _visible_expiry(record, status),
        "verified_at": _verified_at(record, status),
    }


def submit(
    db: Session,
    *,
    faculty: User,
    researcher_id: int,
    evidence_reference: str,
    note: str,
    now: int | None = None,
) -> ResearcherVerification:
    """Create one pending request; a researcher has at most one pending."""
    now = int(time.time()) if now is None else now

    existing = (
        db.query(ResearcherVerification)
        .filter(
            ResearcherVerification.researcher_id == researcher_id,
            ResearcherVerification.status == "pending",
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A verification request is already pending for this record",
        )

    record = ResearcherVerification(
        researcher_id=researcher_id,
        status="pending",
        evidence_reference=evidence_reference,
        note=note,
        review_note="",
        submitted_by_user_id=faculty.id,
        reviewed_by_user_id=None,
        submitted_at=now,
        reviewed_at=None,
        expires_at=None,
        created_at=now,
    )
    try:
        db.add(record)
        db.flush()
        record_event(
            db,
            actor=faculty,
            action="researcher_verification.submit",
            target_type="researcher",
            target_id=researcher_id,
            detail={"verification_id": record.id},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A verification request is already pending for this record",
        ) from exc

    db.refresh(record)
    return record


def decide(
    db: Session,
    *,
    admin: User,
    verification_id: int,
    decision: str,
    review_note: str,
    expires_in_days: int | None = None,
    now: int | None = None,
) -> ResearcherVerification:
    record = db.get(ResearcherVerification, verification_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Verification request not found")

    if effective_status(record, now) != "pending":
        raise HTTPException(
            status_code=409,
            detail="This verification request has already been reviewed",
        )

    now = int(time.time()) if now is None else now
    values = {
        "status": "verified" if decision == "verify" else "rejected",
        "review_note": review_note,
        "reviewed_by_user_id": admin.id,
        "reviewed_at": now,
        "expires_at": (
            now + expires_in_days * 86_400
            if decision == "verify" and expires_in_days is not None
            else None
        ),
    }

    result = db.execute(
        update(ResearcherVerification)
        .where(
            ResearcherVerification.id == verification_id,
            ResearcherVerification.status == "pending",
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This verification request has already been reviewed",
        )

    record_event(
        db,
        actor=admin,
        action=(
            "researcher_verification.approve"
            if decision == "verify"
            else "researcher_verification.reject"
        ),
        target_type="researcher",
        target_id=record.researcher_id,
        detail={"verification_id": verification_id},
    )
    db.commit()
    db.refresh(record)
    return record
