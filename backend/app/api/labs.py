"""Research lab directory and inter-university collaboration."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    InterUniversityCollaboration,
    ResearchLab,
    ResearchLabMember,
    User,
)
from ..schemas import (
    InterUniversityCollaborationCreate,
    InterUniversityCollaborationStatusUpdate,
    ResearchLabCreate,
    ResearchLabMemberCreate,
    ResearchLabUpdate,
)
from ..services import labs as lab_service
from ..services.audit import record_event
from .deps import get_current_user, get_optional_user, require_faculty

router = APIRouter(tags=["Research Labs"])

LAB_NOT_FOUND = "Lab not found"
COLLABORATION_NOT_FOUND = "Collaboration not found"


def _like_pattern(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _member_lab_ids(user_id: int):
    return select(ResearchLabMember.lab_id).where(
        ResearchLabMember.user_id == user_id
    )


def _lab_or_404(db: Session, lab_id: int) -> ResearchLab:
    lab = db.get(ResearchLab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail=LAB_NOT_FOUND)
    return lab


# --------------------------------------------------
# LAB DIRECTORY
# --------------------------------------------------


@router.get("/labs")
def list_labs(
    q: str | None = Query(default=None, max_length=200),
    institution_id: int | None = Query(default=None, ge=1),
    mine: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if mine and user is None:
        raise HTTPException(
            status_code=401, detail="Authentication required"
        )

    query = db.query(ResearchLab)
    if mine:
        query = query.filter(ResearchLab.id.in_(_member_lab_ids(user.id)))
    elif user is None:
        query = query.filter(ResearchLab.visibility == "public")
    else:
        membership = lab_service.institution_membership(db, user.id)
        conditions = [
            ResearchLab.visibility == "public",
            ResearchLab.id.in_(_member_lab_ids(user.id)),
        ]
        if membership is not None:
            conditions.append(
                ResearchLab.institution_id == membership.institution_id
            )
        query = query.filter(or_(*conditions))

    if institution_id is not None:
        query = query.filter(ResearchLab.institution_id == institution_id)
    if q:
        pattern = _like_pattern(q.strip())
        query = query.filter(
            or_(
                ResearchLab.name.ilike(pattern, escape="\\"),
                ResearchLab.description.ilike(pattern, escape="\\"),
                ResearchLab.research_areas.ilike(pattern, escape="\\"),
            )
        )

    total = query.order_by(None).count()
    rows = (
        query.order_by(ResearchLab.name.asc(), ResearchLab.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "labs": lab_service.lab_summaries(db, rows, user),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/labs", status_code=201)
def create_lab(
    payload: ResearchLabCreate,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    institution = lab_service.require_institution(db, user)
    timestamp = lab_service.now()
    lab = ResearchLab(
        institution_id=institution.id,
        owner_user_id=user.id,
        name=payload.name,
        description=payload.description,
        research_areas=payload.research_areas,
        visibility=payload.visibility,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(lab)
    try:
        db.flush()
        db.add(
            ResearchLabMember(
                lab_id=lab.id, user_id=user.id, created_at=timestamp
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Your institution already has a lab with that name",
        ) from exc
    db.refresh(lab)
    return lab_service.lab_detail(db, lab, user)


@router.get("/labs/{lab_id}")
def get_lab(
    lab_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    lab = lab_service.require_visible_lab(db, lab_id, user)
    return lab_service.lab_detail(db, lab, user)


@router.put("/labs/{lab_id}")
def update_lab(
    lab_id: int,
    payload: ResearchLabUpdate,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    lab = _lab_or_404(db, lab_id)
    if not lab_service.lab_visible_to(db, lab, user):
        raise HTTPException(status_code=404, detail=LAB_NOT_FOUND)
    lab_service.require_lab_owner(db, lab, user)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return lab_service.lab_detail(db, lab, user)
    for field, value in changes.items():
        setattr(lab, field, value)
    lab.updated_at = lab_service.now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Your institution already has a lab with that name",
        ) from exc
    db.refresh(lab)
    return lab_service.lab_detail(db, lab, user)


@router.delete("/labs/{lab_id}")
def delete_lab(
    lab_id: int,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    lab = _lab_or_404(db, lab_id)
    if not lab_service.lab_visible_to(db, lab, user):
        raise HTTPException(status_code=404, detail=LAB_NOT_FOUND)
    lab_service.require_lab_owner(db, lab, user)

    blocking_collaborations = (
        db.query(InterUniversityCollaboration)
        .filter(
            InterUniversityCollaboration.status.in_(
                lab_service.OPEN_COLLABORATION_STATUSES + ("completed",)
            ),
            or_(
                InterUniversityCollaboration.requester_lab_id == lab.id,
                InterUniversityCollaboration.partner_lab_id == lab.id,
            ),
        )
        .count()
    )
    if blocking_collaborations:
        raise HTTPException(
            status_code=409,
            detail=(
                "Lab deletion is blocked while proposed, active or "
                "completed collaborations exist"
            ),
        )

    removed_collaborations = db.query(InterUniversityCollaboration).filter(
        or_(
            InterUniversityCollaboration.requester_lab_id == lab.id,
            InterUniversityCollaboration.partner_lab_id == lab.id,
        )
    ).delete(synchronize_session=False)
    db.query(ResearchLabMember).filter(
        ResearchLabMember.lab_id == lab.id
    ).delete(synchronize_session=False)
    record_event(
        db,
        actor=user,
        action="lab.delete",
        target_type="lab",
        target_id=lab.id,
        detail={
            "name": lab.name,
            "removed_collaborations": removed_collaborations,
        },
    )
    db.delete(lab)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# LAB MEMBERSHIP
# --------------------------------------------------


@router.get("/labs/{lab_id}/members")
def list_lab_members(
    lab_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    lab = lab_service.require_visible_lab(db, lab_id, user)
    is_member = user is not None and (
        lab.owner_user_id == user.id
        or lab_service.lab_membership(db, lab.id, user.id) is not None
    )
    if not is_member:
        raise HTTPException(
            status_code=403,
            detail="Only lab members can view the roster",
        )
    query = (
        db.query(ResearchLabMember, User)
        .join(User, ResearchLabMember.user_id == User.id)
        .filter(ResearchLabMember.lab_id == lab.id)
    )
    total = query.order_by(None).count()
    rows = (
        query.order_by(ResearchLabMember.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "members": [
            lab_service.lab_member_payload(
                member, member_user, member.user_id == lab.owner_user_id
            )
            for member, member_user in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/labs/{lab_id}/members", status_code=201)
def add_lab_member(
    lab_id: int,
    payload: ResearchLabMemberCreate,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    lab = _lab_or_404(db, lab_id)
    if not lab_service.lab_visible_to(db, lab, user):
        raise HTTPException(status_code=404, detail=LAB_NOT_FOUND)
    lab_service.require_lab_owner(db, lab, user)

    target = db.get(User, payload.user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == lab.owner_user_id:
        raise HTTPException(
            status_code=422, detail="The lab owner is always a member"
        )
    if target.role not in {"student", "faculty"}:
        raise HTTPException(
            status_code=422,
            detail="Only student or faculty accounts can join a lab",
        )
    target_membership = lab_service.institution_membership(db, target.id)
    if (
        target_membership is None
        or target_membership.institution_id != lab.institution_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Lab members must belong to the lab's institution",
        )
    if lab_service.lab_membership(db, lab.id, target.id) is not None:
        raise HTTPException(
            status_code=409, detail="This user is already a lab member"
        )

    member = ResearchLabMember(
        lab_id=lab.id,
        user_id=target.id,
        created_at=lab_service.now(),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return lab_service.lab_member_payload(member, target, False)


@router.delete("/labs/{lab_id}/members/{user_id}")
def remove_lab_member(
    lab_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lab = _lab_or_404(db, lab_id)
    if not lab_service.lab_visible_to(db, lab, user):
        raise HTTPException(status_code=404, detail=LAB_NOT_FOUND)
    if user_id == lab.owner_user_id:
        raise HTTPException(
            status_code=422, detail="The lab owner cannot be removed"
        )

    member = lab_service.lab_membership(db, lab.id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Lab member not found")
    is_self = user.id == user_id
    is_active_owner = user.id == lab.owner_user_id and user.role == "faculty"
    if not is_self and not is_active_owner:
        raise HTTPException(
            status_code=403,
            detail="Only the lab owner can remove other members",
        )
    db.delete(member)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# INTER-UNIVERSITY COLLABORATION
# --------------------------------------------------


@router.get("/interuniversity-collaborations")
def list_collaborations(
    status: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if status is not None and status not in lab_service.INTERUNIVERSITY_STATUS_TRANSITIONS:
        raise HTTPException(status_code=422, detail="Unknown collaboration status")

    lab_ids = _member_lab_ids(user.id)
    query = db.query(InterUniversityCollaboration).filter(
        or_(
            InterUniversityCollaboration.requester_lab_id.in_(lab_ids),
            InterUniversityCollaboration.partner_lab_id.in_(lab_ids),
        )
    )
    if status is not None:
        query = query.filter(InterUniversityCollaboration.status == status)

    total = query.order_by(None).count()
    rows = (
        query.order_by(
            InterUniversityCollaboration.updated_at.desc(),
            InterUniversityCollaboration.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "collaborations": lab_service.collaboration_payloads(db, rows, user),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/interuniversity-collaborations", status_code=201)
def propose_collaboration(
    payload: InterUniversityCollaborationCreate,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    requester_lab = _lab_or_404(db, payload.requester_lab_id)
    if not lab_service.lab_visible_to(db, requester_lab, user):
        raise HTTPException(status_code=404, detail=LAB_NOT_FOUND)
    lab_service.require_lab_owner(db, requester_lab, user)
    if not lab_service.owner_is_affiliated(db, requester_lab, user):
        raise HTTPException(
            status_code=403,
            detail="Your account is no longer affiliated with this lab's institution",
        )

    partner_lab = db.get(ResearchLab, payload.partner_lab_id)
    if partner_lab is None or not lab_service.lab_visible_to(
        db, partner_lab, user
    ):
        raise HTTPException(status_code=404, detail="Partner lab not found")
    if partner_lab.institution_id == requester_lab.institution_id:
        raise HTTPException(
            status_code=422,
            detail="Inter-university collaboration requires a partner lab at another institution",
        )

    duplicate = (
        db.query(InterUniversityCollaboration)
        .filter(
            InterUniversityCollaboration.status.in_(
                lab_service.OPEN_COLLABORATION_STATUSES
            ),
            or_(
                and_(
                    InterUniversityCollaboration.requester_lab_id
                    == requester_lab.id,
                    InterUniversityCollaboration.partner_lab_id
                    == partner_lab.id,
                ),
                and_(
                    InterUniversityCollaboration.requester_lab_id
                    == partner_lab.id,
                    InterUniversityCollaboration.partner_lab_id
                    == requester_lab.id,
                ),
            ),
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="An open collaboration already exists between these labs",
        )

    timestamp = lab_service.now()
    collaboration = InterUniversityCollaboration(
        requester_lab_id=requester_lab.id,
        partner_lab_id=partner_lab.id,
        initiated_by_user_id=user.id,
        decided_by_user_id=None,
        title=payload.title,
        description=payload.description,
        status="proposed",
        resolution_note="",
        responded_at=None,
        pair_key=f"{min(requester_lab.id, partner_lab.id)}:"
        f"{max(requester_lab.id, partner_lab.id)}",
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(collaboration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An open collaboration already exists between these labs",
        )
    db.refresh(collaboration)
    return lab_service.collaboration_payload(db, collaboration, "requester")


@router.get("/interuniversity-collaborations/{collaboration_id}")
def get_collaboration(
    collaboration_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    collaboration = db.get(InterUniversityCollaboration, collaboration_id)
    if collaboration is None:
        raise HTTPException(status_code=404, detail=COLLABORATION_NOT_FOUND)
    role = lab_service.collaboration_access_role(db, collaboration, user)
    if role is None:
        raise HTTPException(status_code=404, detail=COLLABORATION_NOT_FOUND)
    return lab_service.collaboration_payload(db, collaboration, role)


@router.post("/interuniversity-collaborations/{collaboration_id}/status")
def update_collaboration_status(
    collaboration_id: int,
    payload: InterUniversityCollaborationStatusUpdate,
    user: User = Depends(require_faculty),
    db: Session = Depends(get_db),
):
    collaboration = db.get(InterUniversityCollaboration, collaboration_id)
    if collaboration is None:
        raise HTTPException(status_code=404, detail=COLLABORATION_NOT_FOUND)
    role = lab_service.collaboration_access_role(db, collaboration, user)
    if role is None:
        raise HTTPException(status_code=404, detail=COLLABORATION_NOT_FOUND)

    current = collaboration.status
    target = payload.status
    allowed = lab_service.INTERUNIVERSITY_STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a collaboration from {current} to {target}",
        )

    requester_lab = db.get(ResearchLab, collaboration.requester_lab_id)
    partner_lab = db.get(ResearchLab, collaboration.partner_lab_id)
    if target in {"active", "declined"}:
        acting_lab = partner_lab
    elif current == "proposed":
        acting_lab = requester_lab
    else:
        acting_lab = requester_lab if role == "requester" else partner_lab

    is_owner = (
        acting_lab is not None and acting_lab.owner_user_id == user.id
    )
    if not is_owner:
        raise HTTPException(
            status_code=403,
            detail="Only the relevant lab owner can change this collaboration",
        )
    if not lab_service.owner_is_affiliated(db, acting_lab, user):
        raise HTTPException(
            status_code=403,
            detail="Your account is no longer affiliated with this lab's institution",
        )

    timestamp = lab_service.now()
    values = {
        "status": target,
        "resolution_note": payload.note,
        "updated_at": timestamp,
    }
    if target in {"active", "declined"}:
        values["responded_at"] = timestamp
        values["decided_by_user_id"] = user.id

    result = db.execute(
        update(InterUniversityCollaboration)
        .where(
            InterUniversityCollaboration.id == collaboration.id,
            InterUniversityCollaboration.status == current,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The collaboration status changed; refresh and retry",
        )

    db.commit()
    db.refresh(collaboration)
    return lab_service.collaboration_payload(db, collaboration, role)
