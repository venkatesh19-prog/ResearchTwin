"""Administrator-only account lifecycle and audit endpoints."""

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AuditEvent,
    AuthSession,
    CollaborationRequest,
    FacultyProfile,
    FacultyResearcherLink,
    Group,
    GroupMembership,
    Researcher,
    RoadmapProgress,
    StudentProfile,
    User,
)
from ..schemas import (
    AccountDataExport,
    AccountRoleUpdate,
    AccountStatusUpdate,
    AdminPasswordReset,
    AdminUserResponse,
    AuditEventResponse,
    GroupMemberResponse,
    GroupMembershipCreate,
    GroupResponse,
)
from ..services.audit import record_event
from ..services.auth import hash_password
from ..services.groups import group_name_for_role
from .deps import require_admin

router = APIRouter(prefix="/admin", tags=["Administration"])


def _get_account(db: Session, user_id: int) -> User:
    account = db.get(User, user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


def _revoke_sessions(db: Session, user_id: int) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=int(time.time()))
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


@router.get("/users", response_model=list[AdminUserResponse])
def list_accounts(
    role: Literal["student", "faculty", "admin"] | None = None,
    active: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if role is not None:
        query = query.filter(User.role == role)
    if active is not None:
        query = query.filter(User.is_active.is_(active))

    return query.order_by(User.id).offset(offset).limit(limit).all()


@router.put("/users/{user_id}/active", response_model=AdminUserResponse)
def set_account_active(
    user_id: int,
    payload: AccountStatusUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    account = _get_account(db, user_id)

    if account.id == admin.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot change your own account status",
        )

    if account.is_active == payload.active:
        return account

    account.is_active = payload.active
    revoked = 0
    if payload.active:
        record_event(
            db,
            actor=admin,
            action="account.reactivate",
            target_type="user",
            target_id=account.id,
        )
    else:
        revoked = _revoke_sessions(db, account.id)
        record_event(
            db,
            actor=admin,
            action="account.deactivate",
            target_type="user",
            target_id=account.id,
            detail={"revoked_sessions": revoked},
        )

    db.commit()
    db.refresh(account)
    return account


@router.put("/users/{user_id}/role", response_model=AdminUserResponse)
def set_account_role(
    user_id: int,
    payload: AccountRoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    account = _get_account(db, user_id)

    if account.id == admin.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot change your own role",
        )

    if account.role == payload.role:
        return account

    previous_role = account.role
    account.role = payload.role
    revoked = _revoke_sessions(db, account.id)
    record_event(
        db,
        actor=admin,
        action="account.role_change",
        target_type="user",
        target_id=account.id,
        detail={
            "from": previous_role,
            "to": payload.role,
            "revoked_sessions": revoked,
        },
    )

    db.commit()
    db.refresh(account)
    return account


@router.post("/users/{user_id}/sessions/revoke")
def revoke_account_sessions(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    account = _get_account(db, user_id)
    revoked = _revoke_sessions(db, account.id)
    record_event(
        db,
        actor=admin,
        action="account.sessions_revoked",
        target_type="user",
        target_id=account.id,
        detail={"revoked": revoked},
    )
    db.commit()

    return {"revoked": revoked}


@router.post("/users/{user_id}/password-reset")
def reset_account_password(
    user_id: int,
    payload: AdminPasswordReset,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    account = _get_account(db, user_id)
    account.password_hash = hash_password(payload.password)
    revoked = _revoke_sessions(db, account.id)
    record_event(
        db,
        actor=admin,
        action="account.password_reset",
        target_type="user",
        target_id=account.id,
        detail={"revoked_sessions": revoked},
    )
    db.commit()

    return {"message": "Password updated"}


@router.get("/users/{user_id}/data-export", response_model=AccountDataExport)
def export_account_data(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return one account's personal data for an institutional access request.

    Password hashes and session token hashes are never included. The export is
    itself audited, which is why the event list is built before recording it.
    """
    account = _get_account(db, user_id)

    student_profile = (
        db.query(StudentProfile).filter(StudentProfile.user_id == account.id).first()
    )
    faculty_profile = (
        db.query(FacultyProfile).filter(FacultyProfile.user_id == account.id).first()
    )
    link = (
        db.query(FacultyResearcherLink)
        .filter(FacultyResearcherLink.faculty_user_id == account.id)
        .first()
    )

    requests = (
        db.query(CollaborationRequest)
        .filter(CollaborationRequest.student_user_id == account.id)
        .order_by(CollaborationRequest.id)
        .all()
    )
    inbox = []
    if link is not None:
        inbox = (
            db.query(CollaborationRequest)
            .filter(CollaborationRequest.researcher_id == link.researcher_id)
            .order_by(CollaborationRequest.id)
            .all()
        )

    researcher_ids = {record.researcher_id for record in requests + inbox}
    researchers = {}
    if researcher_ids:
        researchers = {
            researcher.id: researcher
            for researcher in db.query(Researcher)
            .filter(Researcher.id.in_(researcher_ids))
            .all()
        }

    def request_row(record: CollaborationRequest, include_message: bool = True) -> dict:
        researcher = researchers.get(record.researcher_id)
        row = {
            "id": record.id,
            "researcher_id": record.researcher_id,
            "researcher_name": researcher.name if researcher else None,
            "status": record.status,
            "faculty_response": record.faculty_response,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "reviewed_at": record.reviewed_at,
        }
        if include_message:
            row["message"] = record.message
        return row

    roadmap = (
        db.query(RoadmapProgress)
        .filter(RoadmapProgress.user_id == account.id)
        .order_by(RoadmapProgress.id)
        .all()
    )

    now = int(time.time())
    sessions = db.query(AuthSession).filter(AuthSession.user_id == account.id).all()
    audit_events = (
        db.query(AuditEvent)
        .filter(
            or_(
                AuditEvent.actor_user_id == account.id,
                and_(AuditEvent.target_type == "user", AuditEvent.target_id == account.id),
            )
        )
        .order_by(AuditEvent.id)
        .all()
    )

    record_event(
        db,
        actor=admin,
        action="account.data_export",
        target_type="user",
        target_id=account.id,
    )
    db.commit()

    return {
        "generated_at": now,
        "account": account,
        "student_profile": (
            {
                "research_areas": student_profile.research_areas,
                "expertise": student_profile.expertise,
                "skills": student_profile.skills,
                "projects": student_profile.projects,
                "publications": student_profile.publications,
                "courses": student_profile.courses,
                "academic_details": student_profile.academic_details,
                "updated_at": student_profile.updated_at,
            }
            if student_profile
            else None
        ),
        "faculty_profile": (
            {
                "department": faculty_profile.department,
                "designation": faculty_profile.designation,
                "research_areas": faculty_profile.research_areas,
                "expertise": faculty_profile.expertise,
                "skills": faculty_profile.skills,
                "publications": faculty_profile.publications,
                "projects": faculty_profile.projects,
                "profile_url": faculty_profile.profile_url,
                "updated_at": faculty_profile.updated_at,
            }
            if faculty_profile
            else None
        ),
        "faculty_link": (
            {"researcher_id": link.researcher_id, "created_at": link.created_at}
            if link
            else None
        ),
        "collaboration_requests": [request_row(record) for record in requests],
        # The account owner's inbox contains requests written by other data
        # subjects, so messages and student identifiers stay out of this export.
        "faculty_inbox": [
            request_row(record, include_message=False) for record in inbox
        ],
        "roadmap_progress": [
            {
                "researcher_id": progress.researcher_id,
                "skill": progress.skill,
                "milestone_index": progress.milestone_index,
                "is_completed": progress.is_completed,
                "updated_at": progress.updated_at,
            }
            for progress in roadmap
        ],
        "sessions": {
            "total": len(sessions),
            "active": sum(
                1 for item in sessions if item.revoked_at is None and item.expires_at > now
            ),
            "revoked": sum(1 for item in sessions if item.revoked_at is not None),
            "expired": sum(1 for item in sessions if item.expires_at <= now),
            "latest_created_at": max((item.created_at for item in sessions), default=None),
        },
        "audit_events": [
            {
                "id": event.id,
                "actor_user_id": event.actor_user_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "detail": event.detail,
                "created_at": event.created_at,
            }
            for event in audit_events
        ],
    }


def _get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.get("/groups", response_model=list[GroupResponse])
def list_groups(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Group, func.count(GroupMembership.id))
        .outerjoin(GroupMembership, GroupMembership.group_id == Group.id)
        .group_by(Group.id)
        .order_by(Group.id)
        .all()
    )
    return [
        GroupResponse(
            id=group.id,
            name=group.name,
            member_count=count,
            created_at=group.created_at,
        )
        for group, count in rows
    ]


@router.get("/groups/{group_id}/members", response_model=list[GroupMemberResponse])
def list_group_members(
    group_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = _get_group(db, group_id)
    rows = (
        db.query(GroupMembership, User.email, User.full_name, User.role)
        .join(User, User.id == GroupMembership.user_id)
        .filter(GroupMembership.group_id == group.id)
        .order_by(GroupMembership.id)
        .all()
    )
    return [
        GroupMemberResponse(
            membership_id=membership.id,
            user_id=membership.user_id,
            email=email,
            full_name=full_name,
            role=role,
            created_at=membership.created_at,
        )
        for membership, email, full_name, role in rows
    ]


@router.post(
    "/groups/{group_id}/members",
    response_model=GroupMemberResponse,
    status_code=201,
)
def add_group_member(
    group_id: int,
    payload: GroupMembershipCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = _get_group(db, group_id)
    account = db.get(User, payload.user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    expected_name = group_name_for_role(account.role)
    if expected_name != group.name:
        raise HTTPException(
            status_code=400,
            detail=f"Only {account.role} accounts can join the {group.name} group",
        )

    membership = GroupMembership(
        group_id=group.id,
        user_id=account.id,
        created_at=int(time.time()),
    )
    db.add(membership)
    record_event(
        db,
        actor=admin,
        action="group.member_added",
        target_type="group",
        target_id=group.id,
        detail={"user_id": account.id, "email": account.email},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Account is already a member of this group",
        ) from exc
    db.refresh(membership)

    return GroupMemberResponse(
        membership_id=membership.id,
        user_id=account.id,
        email=account.email,
        full_name=account.full_name,
        role=account.role,
        created_at=membership.created_at,
    )


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_group_member(
    group_id: int,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = _get_group(db, group_id)
    membership = (
        db.query(GroupMembership)
        .filter(GroupMembership.group_id == group.id, GroupMembership.user_id == user_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")

    db.delete(membership)
    record_event(
        db,
        actor=admin,
        action="group.member_removed",
        target_type="group",
        target_id=group.id,
        detail={"user_id": user_id},
    )
    db.commit()

    return {"message": "Membership removed"}


@router.get("/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(
    action: str | None = Query(default=None, max_length=64),
    target_type: str | None = Query(default=None, max_length=32),
    target_id: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = (
        db.query(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .order_by(AuditEvent.id.desc())
    )
    if action is not None:
        query = query.filter(AuditEvent.action == action)
    if target_type is not None:
        query = query.filter(AuditEvent.target_type == target_type)
    if target_id is not None:
        query = query.filter(AuditEvent.target_id == target_id)

    rows = query.offset(offset).limit(limit).all()

    return [
        AuditEventResponse(
            id=event.id,
            actor_user_id=event.actor_user_id,
            actor_email=actor_email,
            action=event.action,
            target_type=event.target_type,
            target_id=event.target_id,
            detail=event.detail,
            created_at=event.created_at,
        )
        for event, actor_email in rows
    ]
