"""Institution directory and administrator provisioning."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Institution,
    InstitutionMembership,
    ResearchLab,
    ResearchLabMember,
    User,
)
from ..schemas import InstitutionCreate, InstitutionUpdate
from ..services import labs as lab_service
from .deps import get_current_user, require_admin

router = APIRouter(tags=["Institutions"])


def _institution_or_404(db: Session, institution_id: int) -> Institution:
    institution = db.get(Institution, institution_id)
    if institution is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return institution


def _member_rows(db: Session, institution_id: int):
    return (
        db.query(InstitutionMembership, User)
        .join(User, InstitutionMembership.user_id == User.id)
        .filter(InstitutionMembership.institution_id == institution_id)
        .order_by(InstitutionMembership.id.asc())
        .all()
    )


def _member_payload(membership: InstitutionMembership, user: User) -> dict:
    return {
        "user_id": membership.user_id,
        "full_name": user.full_name,
        "institution_id": membership.institution_id,
        "created_at": membership.created_at,
    }


@router.get("/institutions")
def list_institutions(db: Session = Depends(get_db)):
    rows = db.query(Institution).order_by(Institution.name.asc()).all()
    return {
        "institutions": lab_service.institution_summaries(db, rows),
        "total": len(rows),
    }


@router.get("/institutions/me")
def my_institution(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = lab_service.institution_membership(db, user.id)
    if membership is None:
        return {"institution": None}
    institution = db.get(Institution, membership.institution_id)
    return {
        "institution": lab_service.institution_summary(db, institution)
        if institution
        else None
    }


@router.get("/admin/institutions")
def admin_list_institutions(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(Institution).order_by(Institution.name.asc()).all()
    return {
        "institutions": lab_service.institution_summaries(db, rows),
        "total": len(rows),
    }


@router.post("/admin/institutions", status_code=201)
def create_institution(
    payload: InstitutionCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    institution = Institution(
        name=payload.name, created_at=lab_service.now()
    )
    db.add(institution)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="That institution name already exists"
        ) from exc
    db.refresh(institution)
    return lab_service.institution_summary(db, institution)


@router.put("/admin/institutions/{institution_id}")
def rename_institution(
    institution_id: int,
    payload: InstitutionUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    institution = _institution_or_404(db, institution_id)
    institution.name = payload.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="That institution name already exists"
        ) from exc
    db.refresh(institution)
    return lab_service.institution_summary(db, institution)


@router.get("/admin/institutions/{institution_id}/members")
def admin_list_members(
    institution_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _institution_or_404(db, institution_id)
    rows = _member_rows(db, institution_id)
    return {
        "members": [
            _member_payload(membership, user) for membership, user in rows
        ],
        "total": len(rows),
    }


@router.put("/admin/institutions/{institution_id}/members/{user_id}")
def assign_member(
    institution_id: int,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _institution_or_404(db, institution_id)
    target = db.get(User, user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role not in {"student", "faculty"}:
        raise HTTPException(
            status_code=422,
            detail="Only student or faculty accounts can be affiliated",
        )

    existing = lab_service.institution_membership(db, user_id)
    if existing is not None:
        if existing.institution_id != institution_id:
            raise HTTPException(
                status_code=409,
                detail="This user already belongs to another institution",
            )
        return _member_payload(existing, target)

    membership = InstitutionMembership(
        institution_id=institution_id,
        user_id=user_id,
        created_at=lab_service.now(),
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return _member_payload(membership, target)


@router.delete("/admin/institutions/{institution_id}/members/{user_id}")
def remove_member(
    institution_id: int,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _institution_or_404(db, institution_id)
    membership = (
        db.query(InstitutionMembership)
        .filter(
            InstitutionMembership.institution_id == institution_id,
            InstitutionMembership.user_id == user_id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=404, detail="Institution member not found"
        )

    owned_lab = (
        db.query(ResearchLab.id)
        .filter(
            ResearchLab.institution_id == institution_id,
            ResearchLab.owner_user_id == user_id,
        )
        .first()
    )
    if owned_lab is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Transfer or delete this user's labs before removing "
                "institution access"
            ),
        )

    institution_labs = db.query(ResearchLab.id).filter(
        ResearchLab.institution_id == institution_id
    )
    db.query(ResearchLabMember).filter(
        ResearchLabMember.user_id == user_id,
        ResearchLabMember.lab_id.in_(institution_labs.scalar_subquery()),
    ).delete(synchronize_session=False)
    db.delete(membership)
    db.commit()
    return {"deleted": True}
