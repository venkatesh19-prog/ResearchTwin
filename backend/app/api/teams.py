import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    ResearchTeam,
    ResearchTeamInvitation,
    ResearchTeamMember,
    User,
)
from ..schemas import (
    ResearchTeamCreate,
    ResearchTeamInvitationCreate,
    ResearchTeamInvitationDecision,
    TeamRecommendationRequest,
)
from ..services.audit import record_event
from ..services.rate_limit import (
    RECOMMENDATION_MAX,
    RECOMMENDATION_WINDOW_SECONDS,
    enforce_rate_limit,
)
from ..services.recommendation import (
    RecommendationError,
    generate_recommendations,
)
from ..services.semantic_matching import SemanticMatchingError
from ..services.teams import require_membership
from .deps import get_current_user, require_role

router = APIRouter(prefix="/teams", tags=["Research Teams"])

FOCUS_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
)


def _focus(team: ResearchTeam) -> dict:
    return {field: getattr(team, field) for field in FOCUS_FIELDS}


def _invitation_payload(invitation: ResearchTeamInvitation) -> dict:
    return {
        "id": invitation.id,
        "team_id": invitation.team_id,
        "invited_user_id": invitation.invited_user_id,
        "invited_by_user_id": invitation.invited_by_user_id,
        "status": invitation.status,
        "created_at": invitation.created_at,
        "responded_at": invitation.responded_at,
    }


def _team_payload(
    db: Session, team: ResearchTeam, membership: ResearchTeamMember
) -> dict:
    members = (
        db.query(ResearchTeamMember)
        .filter(ResearchTeamMember.team_id == team.id)
        .order_by(ResearchTeamMember.id)
        .all()
    )
    users = {
        user.id: user
        for user in db.query(User)
        .filter(User.id.in_({member.user_id for member in members}))
        .all()
    }
    invitations = []
    if membership.role == "owner":
        invitations = [
            _invitation_payload(invitation)
            for invitation in db.query(ResearchTeamInvitation)
            .filter(
                ResearchTeamInvitation.team_id == team.id,
                ResearchTeamInvitation.status == "pending",
            )
            .order_by(ResearchTeamInvitation.id)
            .all()
        ]

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "focus": _focus(team),
        "owner_user_id": team.owner_user_id,
        "role": membership.role,
        "members": [
            {
                "user_id": member.user_id,
                "full_name": users[member.user_id].full_name
                if member.user_id in users
                else "Unknown member",
                "role": member.role,
                "joined_at": member.created_at,
            }
            for member in members
        ],
        "invitations": invitations,
        "created_at": team.created_at,
        "updated_at": team.updated_at,
    }


@router.post("", status_code=201)
def create_team(
    payload: ResearchTeamCreate,
    user: User = Depends(require_role("student", "faculty")),
    db: Session = Depends(get_db),
):
    now = int(time.time())
    team = ResearchTeam(
        owner_user_id=user.id,
        name=payload.name,
        description=payload.description,
        research_areas=payload.research_areas,
        expertise=payload.expertise,
        skills=payload.skills,
        projects=payload.projects,
        publications=payload.publications,
        created_at=now,
        updated_at=now,
    )
    db.add(team)
    db.flush()

    membership = ResearchTeamMember(
        team_id=team.id,
        user_id=user.id,
        role="owner",
        created_at=now,
    )
    db.add(membership)
    record_event(
        db,
        actor=user,
        action="team.create",
        target_type="research_team",
        target_id=team.id,
        detail={"name": team.name},
    )
    db.commit()
    db.refresh(team)
    db.refresh(membership)

    return _team_payload(db, team, membership)


@router.get("/me")
def list_my_teams(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(ResearchTeamMember)
        .filter(ResearchTeamMember.user_id == user.id)
        .order_by(ResearchTeamMember.id.desc())
        .all()
    )
    teams = {}
    counts = {}
    if memberships:
        team_ids = {membership.team_id for membership in memberships}
        teams = {
            team.id: team
            for team in db.query(ResearchTeam)
            .filter(ResearchTeam.id.in_(team_ids))
            .all()
        }
        counts = dict(
            db.query(ResearchTeamMember.team_id, func.count(ResearchTeamMember.id))
            .filter(ResearchTeamMember.team_id.in_(team_ids))
            .group_by(ResearchTeamMember.team_id)
            .all()
        )

    team_items = []
    for membership in memberships:
        team = teams.get(membership.team_id)
        if team is None:
            continue
        team_items.append(
            {
                "id": team.id,
                "name": team.name,
                "role": membership.role,
                "owner_user_id": team.owner_user_id,
                "member_count": counts.get(team.id, 0),
                "created_at": team.created_at,
                "updated_at": team.updated_at,
            }
        )

    pending = (
        db.query(ResearchTeamInvitation, ResearchTeam)
        .join(ResearchTeam, ResearchTeam.id == ResearchTeamInvitation.team_id)
        .filter(
            ResearchTeamInvitation.invited_user_id == user.id,
            ResearchTeamInvitation.status == "pending",
        )
        .order_by(ResearchTeamInvitation.id)
        .all()
    )
    invitations = [
        {
            "id": invitation.id,
            "team_id": invitation.team_id,
            "team_name": team.name,
            "invited_by_user_id": invitation.invited_by_user_id,
            "created_at": invitation.created_at,
        }
        for invitation, team in pending
    ]

    return {"teams": team_items, "invitations": invitations}


@router.get("/{team_id}")
def get_team(
    team_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team, membership = require_membership(db, team_id, user)
    return _team_payload(db, team, membership)


@router.delete("/{team_id}")
def delete_team(
    team_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team, membership = require_membership(db, team_id, user)
    if membership.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the team owner can delete this team",
        )

    record_event(
        db,
        actor=user,
        action="team.delete",
        target_type="research_team",
        target_id=team.id,
        detail={"name": team.name},
    )
    # Explicit child deletes keep SQLite (where foreign keys are optional)
    # consistent with PostgreSQL's cascading behavior.
    db.query(ResearchTeamInvitation).filter(
        ResearchTeamInvitation.team_id == team.id
    ).delete(synchronize_session=False)
    db.query(ResearchTeamMember).filter(
        ResearchTeamMember.team_id == team.id
    ).delete(synchronize_session=False)
    db.delete(team)
    db.commit()
    return {"deleted": True}


@router.post("/{team_id}/invitations", status_code=201)
def invite_member(
    team_id: int,
    payload: ResearchTeamInvitationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team, membership = require_membership(db, team_id, user)
    if membership.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the team owner can invite members",
        )

    if payload.user_id == user.id:
        raise HTTPException(status_code=422, detail="You cannot invite yourself")

    target = db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.role not in {"student", "faculty"} or not target.is_active:
        raise HTTPException(
            status_code=422,
            detail="Only active student or faculty accounts can join a research team",
        )

    already_member = (
        db.query(ResearchTeamMember)
        .filter(
            ResearchTeamMember.team_id == team.id,
            ResearchTeamMember.user_id == target.id,
        )
        .first()
    )
    if already_member is not None:
        raise HTTPException(
            status_code=409, detail="This account is already a team member"
        )

    pending = (
        db.query(ResearchTeamInvitation)
        .filter(
            ResearchTeamInvitation.team_id == team.id,
            ResearchTeamInvitation.invited_user_id == target.id,
            ResearchTeamInvitation.status == "pending",
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(
            status_code=409, detail="This account already has a pending invitation"
        )

    now = int(time.time())
    invitation = ResearchTeamInvitation(
        team_id=team.id,
        invited_user_id=target.id,
        invited_by_user_id=user.id,
        status="pending",
        created_at=now,
        responded_at=None,
    )
    db.add(invitation)
    record_event(
        db,
        actor=user,
        action="team.invite",
        target_type="research_team",
        target_id=team.id,
        detail={"invited_user_id": target.id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This account already has a pending invitation",
        ) from exc
    db.refresh(invitation)

    return _invitation_payload(invitation)


@router.put("/{team_id}/invitations/{invitation_id}")
def decide_invitation(
    team_id: int,
    invitation_id: int,
    payload: ResearchTeamInvitationDecision,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitation = (
        db.query(ResearchTeamInvitation)
        .filter(
            ResearchTeamInvitation.id == invitation_id,
            ResearchTeamInvitation.team_id == team_id,
        )
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.invited_user_id != user.id:
        raise HTTPException(status_code=404, detail="Invitation not found")

    now = int(time.time())
    result = db.execute(
        update(ResearchTeamInvitation)
        .where(
            ResearchTeamInvitation.id == invitation.id,
            ResearchTeamInvitation.status == "pending",
        )
        .values(
            status="accepted" if payload.decision == "accept" else "declined",
            responded_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This invitation has already been answered"
        )

    if payload.decision == "accept":
        team = db.get(ResearchTeam, team_id)
        if team is None:
            db.rollback()
            raise HTTPException(status_code=404, detail="Team not found")
        db.add(
            ResearchTeamMember(
                team_id=team_id,
                user_id=user.id,
                role="member",
                created_at=now,
            )
        )
        record_event(
            db,
            actor=user,
            action="team.join",
            target_type="research_team",
            target_id=team_id,
            detail={"team": team.name if team else None},
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This account is already a team member"
        ) from exc

    db.refresh(invitation)
    return _invitation_payload(invitation)


@router.delete("/{team_id}/members/{user_id}")
def remove_member(
    team_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team, membership = require_membership(db, team_id, user)

    if membership.role != "owner" and user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the team owner can remove other members",
        )
    if user_id == team.owner_user_id:
        raise HTTPException(
            status_code=409,
            detail="The team owner cannot leave; delete the team instead",
        )

    member = (
        db.query(ResearchTeamMember)
        .filter(
            ResearchTeamMember.team_id == team.id,
            ResearchTeamMember.user_id == user_id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")

    db.delete(member)
    record_event(
        db,
        actor=user,
        action="team.member_remove",
        target_type="research_team",
        target_id=team.id,
        detail={"removed_user_id": user_id},
    )
    db.commit()
    return {"removed": True}


@router.post("/{team_id}/recommendations")
def recommend_for_team(
    team_id: int,
    payload: TeamRecommendationRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team, _ = require_membership(db, team_id, user)

    profile = _focus(team)
    if not any(value.strip() for value in profile.values()):
        raise HTTPException(
            status_code=400,
            detail="Add a research focus to the team before requesting recommendations",
        )

    enforce_rate_limit(
        db,
        http_request,
        scope="team-recommendations",
        identities=(("user", str(user.id)),),
        limit=RECOMMENDATION_MAX,
        window_seconds=RECOMMENDATION_WINDOW_SECONDS,
    )

    try:
        recommendations = generate_recommendations(
            student_profile=profile,
            db=db,
            top_k=payload.top_k,
        )
    except (RecommendationError, SemanticMatchingError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Recommendation service unavailable",
        ) from exc

    return {
        "team": {"id": team.id, "name": team.name},
        "profile_used": profile,
        "recommendations": recommendations,
    }
