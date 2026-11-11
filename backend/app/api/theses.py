"""Thesis tracking with supervisors, milestones and progress history."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    ThesisMilestone,
    ThesisProgressEvent,
    ThesisRecord,
    User,
)
from ..schemas import (
    ThesisCreate,
    ThesisMilestoneCreate,
    ThesisMilestoneUpdate,
    ThesisUpdate,
)
from ..services import research_outputs
from .deps import get_current_user, require_role

router = APIRouter(tags=["Theses"])

THESIS_NOT_FOUND = "Thesis not found"


def _thesis_access(
    db: Session, user: User, thesis_id: int
) -> tuple[ThesisRecord, str]:
    thesis = db.get(ThesisRecord, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail=THESIS_NOT_FOUND)
    if thesis.owner_user_id == user.id:
        return thesis, "owner"
    if thesis.supervisor_user_id == user.id:
        return thesis, "supervisor"
    raise HTTPException(status_code=404, detail=THESIS_NOT_FOUND)


def _require_owner(access_role: str) -> None:
    if access_role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the thesis owner can perform this action",
        )


def _supervisor(db: Session, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    supervisor = db.get(User, user_id)
    if supervisor is None:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    if supervisor.role != "faculty" or not supervisor.is_active:
        raise HTTPException(
            status_code=422,
            detail="Supervisor must be an active faculty account",
        )
    return supervisor


def _get_milestone(
    db: Session, thesis_id: int, milestone_id: int
) -> ThesisMilestone:
    milestone = (
        db.query(ThesisMilestone)
        .filter(
            ThesisMilestone.id == milestone_id,
            ThesisMilestone.thesis_id == thesis_id,
        )
        .first()
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail="Thesis milestone not found")
    return milestone


def _renumber_milestones(db: Session, thesis_id: int) -> None:
    remaining = (
        db.query(ThesisMilestone)
        .filter(ThesisMilestone.thesis_id == thesis_id)
        .order_by(ThesisMilestone.position.asc(), ThesisMilestone.id.asc())
        .all()
    )
    for index, milestone in enumerate(remaining):
        milestone.position = index


def _touch(thesis: ThesisRecord) -> None:
    thesis.updated_at = research_outputs.now()


@router.get("/theses")
def list_theses(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ThesisRecord).filter(
        or_(
            ThesisRecord.owner_user_id == user.id,
            ThesisRecord.supervisor_user_id == user.id,
        )
    )
    total = query.order_by(None).count()
    rows = (
        query.order_by(
            ThesisRecord.updated_at.desc(), ThesisRecord.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "theses": [
            research_outputs.thesis_summary(
                db,
                thesis,
                "owner" if thesis.owner_user_id == user.id else "supervisor",
            )
            for thesis in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/theses", status_code=201)
def create_thesis(
    payload: ThesisCreate,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    supervisor = _supervisor(db, payload.supervisor_user_id)
    timestamp = research_outputs.now()
    thesis = ThesisRecord(
        owner_user_id=user.id,
        supervisor_user_id=supervisor.id if supervisor else None,
        title=payload.title,
        abstract=payload.abstract,
        status="proposed",
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(thesis)
    db.flush()
    research_outputs.record_thesis_event(
        db,
        thesis,
        actor_user_id=user.id,
        event_type="thesis_created",
        note=f"Thesis '{thesis.title}' created.",
    )
    if supervisor is not None:
        research_outputs.record_thesis_event(
            db,
            thesis,
            actor_user_id=user.id,
            event_type="supervisor_assigned",
            note=f"{supervisor.full_name} assigned as supervisor.",
        )
    db.commit()
    db.refresh(thesis)
    return research_outputs.thesis_payload(db, thesis, "owner")


@router.get("/theses/{thesis_id}")
def get_thesis(
    thesis_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, access_role = _thesis_access(db, user, thesis_id)
    return research_outputs.thesis_payload(db, thesis, access_role)


@router.put("/theses/{thesis_id}")
def update_thesis(
    thesis_id: int,
    payload: ThesisUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, access_role = _thesis_access(db, user, thesis_id)
    _require_owner(access_role)

    changes = payload.model_dump(exclude_unset=True)
    note = changes.pop("note", "")

    new_status = changes.get("status")
    if new_status is not None:
        if new_status == thesis.status:
            raise HTTPException(
                status_code=409,
                detail=f"The thesis is already {thesis.status}",
            )
        allowed = research_outputs.THESIS_STATUS_TRANSITIONS.get(
            thesis.status, set()
        )
        if new_status not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot move a thesis from {thesis.status} to {new_status}",
            )

    supervisor_change = False
    new_supervisor_id = None
    if "supervisor_user_id" in changes:
        new_supervisor_id = changes.pop("supervisor_user_id")
        if new_supervisor_id != thesis.supervisor_user_id:
            supervisor = _supervisor(db, new_supervisor_id)
            supervisor_change = True
        else:
            supervisor = None

    if not changes and not supervisor_change:
        return research_outputs.thesis_payload(db, thesis, access_role)

    if supervisor_change:
        previous = thesis.supervisor_user_id
        thesis.supervisor_user_id = new_supervisor_id
        if new_supervisor_id is None:
            event_type = "supervisor_cleared"
            note_text = "Supervisor cleared."
        elif previous is None:
            event_type = "supervisor_assigned"
            note_text = f"{supervisor.full_name} assigned as supervisor."
        else:
            event_type = "supervisor_changed"
            note_text = f"{supervisor.full_name} assigned as supervisor."
        research_outputs.record_thesis_event(
            db,
            thesis,
            actor_user_id=user.id,
            event_type=event_type,
            note=note_text,
        )

    previous_status = thesis.status
    for field, value in changes.items():
        setattr(thesis, field, value)
    if new_status is not None:
        research_outputs.record_thesis_event(
            db,
            thesis,
            actor_user_id=user.id,
            event_type="status_changed",
            note=note,
            from_status=previous_status,
            to_status=new_status,
        )

    _touch(thesis)
    db.commit()
    db.refresh(thesis)
    return research_outputs.thesis_payload(db, thesis, access_role)


@router.delete("/theses/{thesis_id}")
def delete_thesis(
    thesis_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, access_role = _thesis_access(db, user, thesis_id)
    _require_owner(access_role)

    db.query(ThesisProgressEvent).filter(
        ThesisProgressEvent.thesis_id == thesis.id
    ).delete(synchronize_session=False)
    db.query(ThesisMilestone).filter(
        ThesisMilestone.thesis_id == thesis.id
    ).delete(synchronize_session=False)
    db.delete(thesis)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# MILESTONES
# --------------------------------------------------


@router.post("/theses/{thesis_id}/milestones", status_code=201)
def add_thesis_milestone(
    thesis_id: int,
    payload: ThesisMilestoneCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, _ = _thesis_access(db, user, thesis_id)

    position = (
        db.query(ThesisMilestone)
        .filter(ThesisMilestone.thesis_id == thesis.id)
        .count()
    )
    timestamp = research_outputs.now()
    milestone = ThesisMilestone(
        thesis_id=thesis.id,
        title=payload.title,
        due_at=payload.due_at,
        status="pending",
        position=position,
        completed_at=None,
        created_by_user_id=user.id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(milestone)
    db.flush()
    research_outputs.record_thesis_event(
        db,
        thesis,
        actor_user_id=user.id,
        event_type="milestone_added",
        note=f"Milestone '{milestone.title}' added.",
        milestone_id=milestone.id,
    )
    _touch(thesis)
    db.commit()
    db.refresh(milestone)
    return research_outputs.milestone_payload(milestone)


@router.put("/theses/{thesis_id}/milestones/{milestone_id}")
def update_thesis_milestone(
    thesis_id: int,
    milestone_id: int,
    payload: ThesisMilestoneUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, _ = _thesis_access(db, user, thesis_id)
    milestone = _get_milestone(db, thesis.id, milestone_id)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return research_outputs.milestone_payload(milestone)

    new_status = changes.get("status")
    event_type = "milestone_updated"
    if new_status is not None and new_status != milestone.status:
        if new_status == "completed":
            milestone.completed_at = research_outputs.now()
            event_type = "milestone_completed"
        else:
            milestone.completed_at = None
            event_type = "milestone_reopened"
    elif new_status == milestone.status:
        changes.pop("status", None)

    if not changes:
        return research_outputs.milestone_payload(milestone)

    for field, value in changes.items():
        setattr(milestone, field, value)
    milestone.updated_at = research_outputs.now()

    if event_type == "milestone_completed":
        note = f"Milestone '{milestone.title}' completed."
    elif event_type == "milestone_reopened":
        note = f"Milestone '{milestone.title}' reopened."
    else:
        note = f"Milestone '{milestone.title}' updated."
    research_outputs.record_thesis_event(
        db,
        thesis,
        actor_user_id=user.id,
        event_type=event_type,
        note=note,
        milestone_id=milestone.id,
    )
    _touch(thesis)
    db.commit()
    db.refresh(milestone)
    return research_outputs.milestone_payload(milestone)


@router.delete("/theses/{thesis_id}/milestones/{milestone_id}")
def delete_thesis_milestone(
    thesis_id: int,
    milestone_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, access_role = _thesis_access(db, user, thesis_id)
    _require_owner(access_role)
    milestone = _get_milestone(db, thesis.id, milestone_id)
    title = milestone.title

    db.delete(milestone)
    db.flush()
    _renumber_milestones(db, thesis.id)
    research_outputs.record_thesis_event(
        db,
        thesis,
        actor_user_id=user.id,
        event_type="milestone_deleted",
        note=f"Milestone '{title}' deleted.",
    )
    _touch(thesis)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# HISTORY
# --------------------------------------------------


@router.get("/theses/{thesis_id}/history")
def thesis_history(
    thesis_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thesis, _ = _thesis_access(db, user, thesis_id)
    query = (
        db.query(ThesisProgressEvent, User)
        .outerjoin(User, ThesisProgressEvent.actor_user_id == User.id)
        .filter(ThesisProgressEvent.thesis_id == thesis.id)
    )
    total = query.order_by(None).count()
    rows = (
        query.order_by(ThesisProgressEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "events": [
            research_outputs.thesis_event_payload(
                event, actor.full_name if actor else None
            )
            for event, actor in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
