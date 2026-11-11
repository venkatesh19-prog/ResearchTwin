"""Institution, lab and inter-university access helpers."""

import time

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Institution,
    InstitutionMembership,
    ResearchLab,
    ResearchLabMember,
    User,
)

INTERUNIVERSITY_STATUS_TRANSITIONS = {
    "proposed": {"active", "declined", "withdrawn"},
    "active": {"completed", "withdrawn"},
    "declined": set(),
    "completed": set(),
    "withdrawn": set(),
}

OPEN_COLLABORATION_STATUSES = ("proposed", "active")


def now() -> int:
    return int(time.time())


def institution_membership(
    db: Session, user_id: int
) -> InstitutionMembership | None:
    return (
        db.query(InstitutionMembership)
        .filter(InstitutionMembership.user_id == user_id)
        .first()
    )


def require_institution(db: Session, user: User) -> Institution:
    membership = institution_membership(db, user.id)
    if membership is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ask an administrator to affiliate your account with an "
                "institution before creating a lab"
            ),
        )
    institution = db.get(Institution, membership.institution_id)
    if institution is None:
        raise HTTPException(status_code=400, detail="Institution not found")
    return institution


def lab_membership(
    db: Session, lab_id: int, user_id: int
) -> ResearchLabMember | None:
    return (
        db.query(ResearchLabMember)
        .filter(
            ResearchLabMember.lab_id == lab_id,
            ResearchLabMember.user_id == user_id,
        )
        .first()
    )


def lab_visible_to(
    db: Session, lab: ResearchLab, user: User | None
) -> bool:
    if lab.visibility == "public":
        return True
    if user is None:
        return False
    if lab.owner_user_id == user.id:
        return True
    if lab_membership(db, lab.id, user.id) is not None:
        return True
    membership = institution_membership(db, user.id)
    return (
        membership is not None
        and membership.institution_id == lab.institution_id
    )


def require_visible_lab(
    db: Session, lab_id: int, user: User | None
) -> ResearchLab:
    lab = db.get(ResearchLab, lab_id)
    if lab is None or not lab_visible_to(db, lab, user):
        raise HTTPException(status_code=404, detail="Lab not found")
    return lab


def require_lab_owner(db: Session, lab: ResearchLab, user: User) -> None:
    if lab.owner_user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the lab owner can perform this action"
        )


def owner_is_affiliated(db: Session, lab: ResearchLab, user: User) -> bool:
    membership = institution_membership(db, user.id)
    return (
        membership is not None
        and membership.institution_id == lab.institution_id
    )


def institution_summary(db: Session, institution: Institution) -> dict:
    return institution_summaries(db, [institution])[0]


def institution_summaries(
    db: Session, institutions: list[Institution]
) -> list[dict]:
    if not institutions:
        return []
    institution_ids = [institution.id for institution in institutions]
    member_counts = dict(
        db.query(
            InstitutionMembership.institution_id,
            func.count(InstitutionMembership.id),
        )
        .filter(InstitutionMembership.institution_id.in_(institution_ids))
        .group_by(InstitutionMembership.institution_id)
        .all()
    )
    lab_counts = dict(
        db.query(ResearchLab.institution_id, func.count(ResearchLab.id))
        .filter(ResearchLab.institution_id.in_(institution_ids))
        .group_by(ResearchLab.institution_id)
        .all()
    )
    return [
        {
            "id": institution.id,
            "name": institution.name,
            "member_count": int(member_counts.get(institution.id, 0)),
            "lab_count": int(lab_counts.get(institution.id, 0)),
            "created_at": institution.created_at,
        }
        for institution in institutions
    ]


def lab_summary(
    db: Session, lab: ResearchLab, user: User | None
) -> dict:
    return lab_summaries(db, [lab], user)[0]


def lab_summaries(
    db: Session, labs: list[ResearchLab], user: User | None
) -> list[dict]:
    if not labs:
        return []
    lab_ids = [lab.id for lab in labs]
    member_counts = dict(
        db.query(ResearchLabMember.lab_id, func.count(ResearchLabMember.id))
        .filter(ResearchLabMember.lab_id.in_(lab_ids))
        .group_by(ResearchLabMember.lab_id)
        .all()
    )
    member_lab_ids: set[int] = set()
    if user is not None:
        member_lab_ids = {
            lab_id
            for (lab_id,) in db.query(ResearchLabMember.lab_id)
            .filter(
                ResearchLabMember.user_id == user.id,
                ResearchLabMember.lab_id.in_(lab_ids),
            )
            .all()
        }
    institution_ids = {lab.institution_id for lab in labs}
    institutions = {
        institution.id: {"id": institution.id, "name": institution.name}
        for institution in db.query(Institution)
        .filter(Institution.id.in_(institution_ids))
        .all()
    }
    payloads = []
    for lab in labs:
        is_owner = user is not None and lab.owner_user_id == user.id
        payloads.append(
            {
                "id": lab.id,
                "name": lab.name,
                "description": lab.description,
                "research_areas": lab.research_areas,
                "visibility": lab.visibility,
                "institution": institutions.get(lab.institution_id),
                "owner_user_id": lab.owner_user_id,
                "member_count": int(member_counts.get(lab.id, 0)),
                "is_member": bool(is_owner or lab.id in member_lab_ids),
                "is_owner": is_owner,
                "created_at": lab.created_at,
                "updated_at": lab.updated_at,
            }
        )
    return payloads


def lab_member_payload(member: ResearchLabMember, user: User, is_owner: bool) -> dict:
    return {
        "user_id": member.user_id,
        "full_name": user.full_name,
        "is_owner": is_owner,
        "joined_at": member.created_at,
    }


def lab_detail(db: Session, lab: ResearchLab, user: User | None) -> dict:
    payload = lab_summary(db, lab, user)
    if not payload["is_member"]:
        return payload
    rows = (
        db.query(ResearchLabMember, User)
        .join(User, ResearchLabMember.user_id == User.id)
        .filter(ResearchLabMember.lab_id == lab.id)
        .order_by(ResearchLabMember.id.asc())
        .all()
    )
    payload["members"] = [
        lab_member_payload(
            member, member_user, member.user_id == lab.owner_user_id
        )
        for member, member_user in rows
    ]
    return payload


def collaboration_access_role(
    db: Session, collaboration, user: User
) -> str | None:
    requester_lab = db.get(ResearchLab, collaboration.requester_lab_id)
    partner_lab = db.get(ResearchLab, collaboration.partner_lab_id)
    if requester_lab is not None and (
        requester_lab.owner_user_id == user.id
        or lab_membership(db, requester_lab.id, user.id) is not None
    ):
        return "requester"
    if partner_lab is not None and (
        partner_lab.owner_user_id == user.id
        or lab_membership(db, partner_lab.id, user.id) is not None
    ):
        return "partner"
    return None


def collaboration_payload(db: Session, collaboration, access_role: str) -> dict:
    labs = {
        lab.id: lab
        for lab in db.query(ResearchLab)
        .filter(
            ResearchLab.id.in_(
                {collaboration.requester_lab_id, collaboration.partner_lab_id}
            )
        )
        .all()
    }
    institutions = {
        institution.id: {"id": institution.id, "name": institution.name}
        for institution in db.query(Institution)
        .filter(
            Institution.id.in_(
                {lab.institution_id for lab in labs.values()}
            )
        )
        .all()
    }
    return _collaboration_payload(collaboration, access_role, labs, institutions)


def collaboration_payloads(
    db: Session, collaborations: list, user: User
) -> list[dict]:
    if not collaborations:
        return []
    lab_ids = {collaboration.requester_lab_id for collaboration in collaborations}
    lab_ids |= {collaboration.partner_lab_id for collaboration in collaborations}
    labs = {
        lab.id: lab
        for lab in db.query(ResearchLab)
        .filter(ResearchLab.id.in_(lab_ids))
        .all()
    }
    institution_ids = {lab.institution_id for lab in labs.values()}
    institutions = {
        institution.id: {"id": institution.id, "name": institution.name}
        for institution in db.query(Institution)
        .filter(Institution.id.in_(institution_ids))
        .all()
    }
    member_lab_ids = {
        lab_id
        for (lab_id,) in db.query(ResearchLabMember.lab_id)
        .filter(
            ResearchLabMember.user_id == user.id,
            ResearchLabMember.lab_id.in_(lab_ids),
        )
        .all()
    }

    def access_role(collaboration) -> str | None:
        for role, lab_id in (
            ("requester", collaboration.requester_lab_id),
            ("partner", collaboration.partner_lab_id),
        ):
            lab = labs.get(lab_id)
            if lab is not None and (
                lab.owner_user_id == user.id or lab_id in member_lab_ids
            ):
                return role
        return None

    return [
        _collaboration_payload(
            collaboration,
            access_role(collaboration),
            labs,
            institutions,
        )
        for collaboration in collaborations
    ]


def _collaboration_payload(
    collaboration, access_role: str | None, labs: dict, institutions: dict
) -> dict:
    def reference(lab: ResearchLab | None) -> dict | None:
        if lab is None:
            return None
        return {
            "id": lab.id,
            "name": lab.name,
            "institution": institutions.get(lab.institution_id),
        }

    return {
        "id": collaboration.id,
        "title": collaboration.title,
        "description": collaboration.description,
        "status": collaboration.status,
        "requester_lab": reference(labs.get(collaboration.requester_lab_id)),
        "partner_lab": reference(labs.get(collaboration.partner_lab_id)),
        "initiated_by_user_id": collaboration.initiated_by_user_id,
        "decided_by_user_id": collaboration.decided_by_user_id,
        "resolution_note": collaboration.resolution_note,
        "access_role": access_role,
        "responded_at": collaboration.responded_at,
        "created_at": collaboration.created_at,
        "updated_at": collaboration.updated_at,
    }
