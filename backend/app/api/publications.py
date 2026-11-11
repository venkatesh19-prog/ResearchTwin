"""Publication submission tracking with venues, transitions and revisions."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    PublicationRevision,
    PublicationStatusEvent,
    PublicationSubmission,
    User,
)
from ..schemas import (
    PublicationRevisionCreate,
    PublicationStatusUpdate,
    PublicationSubmissionCreate,
    PublicationSubmissionUpdate,
)
from ..services import research_outputs
from .deps import get_current_user

router = APIRouter(tags=["Publication Submissions"])

VenueType = Literal["journal", "conference", "workshop", "book_chapter", "other"]
SubmissionStatus = Literal[
    "draft",
    "submitted",
    "under_review",
    "revision_requested",
    "accepted",
    "rejected",
    "published",
    "withdrawn",
]

SUBMISSION_NOT_FOUND = "Publication submission not found"


def _owned_submission(
    db: Session, user: User, submission_id: int
) -> PublicationSubmission:
    submission = db.get(PublicationSubmission, submission_id)
    if submission is None or submission.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail=SUBMISSION_NOT_FOUND)
    return submission


def _touch(submission: PublicationSubmission) -> None:
    submission.updated_at = research_outputs.now()


@router.get("/publication-submissions")
def list_publication_submissions(
    status: SubmissionStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PublicationSubmission).filter(
        PublicationSubmission.owner_user_id == user.id
    )
    if status is not None:
        query = query.filter(PublicationSubmission.status == status)
    total = query.order_by(None).count()
    rows = (
        query.order_by(
            PublicationSubmission.updated_at.desc(),
            PublicationSubmission.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "submissions": research_outputs.publication_summaries(db, rows),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/publication-submissions", status_code=201)
def create_publication_submission(
    payload: PublicationSubmissionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    timestamp = research_outputs.now()
    submission = PublicationSubmission(
        owner_user_id=user.id,
        title=payload.title,
        venue=payload.venue,
        venue_type=payload.venue_type,
        status="draft",
        doi=payload.doi,
        url=payload.url,
        notes=payload.notes,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return research_outputs.publication_payload(db, submission)


@router.get("/publication-submissions/{submission_id}")
def get_publication_submission(
    submission_id: int,
    revision_offset: int = Query(default=0, ge=0),
    revision_limit: int = Query(default=100, ge=1, le=200),
    history_offset: int = Query(default=0, ge=0),
    history_limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = _owned_submission(db, user, submission_id)
    return research_outputs.publication_payload(
        db,
        submission,
        revision_offset=revision_offset,
        revision_limit=revision_limit,
        history_offset=history_offset,
        history_limit=history_limit,
    )


@router.put("/publication-submissions/{submission_id}")
def update_publication_submission(
    submission_id: int,
    payload: PublicationSubmissionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = _owned_submission(db, user, submission_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return research_outputs.publication_payload(db, submission)
    for field, value in changes.items():
        setattr(submission, field, value)
    _touch(submission)
    db.commit()
    db.refresh(submission)
    return research_outputs.publication_payload(db, submission)


@router.delete("/publication-submissions/{submission_id}")
def delete_publication_submission(
    submission_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = _owned_submission(db, user, submission_id)
    db.query(PublicationStatusEvent).filter(
        PublicationStatusEvent.submission_id == submission.id
    ).delete(synchronize_session=False)
    db.query(PublicationRevision).filter(
        PublicationRevision.submission_id == submission.id
    ).delete(synchronize_session=False)
    db.delete(submission)
    db.commit()
    return {"deleted": True}


@router.post("/publication-submissions/{submission_id}/status")
def update_publication_status(
    submission_id: int,
    payload: PublicationStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = _owned_submission(db, user, submission_id)

    if payload.status == submission.status:
        raise HTTPException(
            status_code=409,
            detail=f"The submission is already {submission.status}",
        )
    allowed = research_outputs.PUBLICATION_STATUS_TRANSITIONS.get(
        submission.status, set()
    )
    if payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot move a submission from {submission.status} "
                f"to {payload.status}"
            ),
        )

    previous = submission.status
    timestamp = research_outputs.now()
    values = {"status": payload.status, "updated_at": timestamp}
    if payload.status == "submitted" and submission.submitted_at is None:
        values["submitted_at"] = timestamp
    if payload.status in {"accepted", "rejected"}:
        values["decision_at"] = timestamp
    if payload.status == "published":
        values["published_at"] = timestamp
        if submission.decision_at is None:
            values["decision_at"] = timestamp

    result = db.execute(
        update(PublicationSubmission)
        .where(
            PublicationSubmission.id == submission.id,
            PublicationSubmission.status == previous,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The submission status changed; refresh and retry",
        )

    db.add(
        PublicationStatusEvent(
            submission_id=submission.id,
            actor_user_id=user.id,
            from_status=previous,
            to_status=payload.status,
            note=payload.note,
            created_at=timestamp,
        )
    )
    db.commit()
    db.refresh(submission)
    return research_outputs.publication_payload(db, submission)


@router.post(
    "/publication-submissions/{submission_id}/revisions", status_code=201
)
def add_publication_revision(
    submission_id: int,
    payload: PublicationRevisionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = _owned_submission(db, user, submission_id)
    if submission.status not in research_outputs.PUBLICATION_REVISION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                "Revisions can only be recorded after the manuscript "
                f"is submitted; current status is {submission.status}"
            ),
        )

    research_outputs.lock_publication_for_revision(db, submission.id)
    latest = (
        db.query(func.max(PublicationRevision.revision_number))
        .filter(PublicationRevision.submission_id == submission.id)
        .scalar()
    )
    timestamp = research_outputs.now()
    revision = PublicationRevision(
        submission_id=submission.id,
        revision_number=int(latest or 0) + 1,
        notes=payload.notes,
        submitted_at=(
            payload.submitted_at
            if payload.submitted_at is not None
            else timestamp
        ),
        created_by_user_id=user.id,
        created_at=timestamp,
    )
    db.add(revision)
    _touch(submission)
    db.commit()
    db.refresh(revision)
    return research_outputs.revision_payload(revision)
