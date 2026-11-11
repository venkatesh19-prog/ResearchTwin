"""Team membership checks. Research teams are independent of auth role groups."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import ResearchTeam, ResearchTeamMember, User


def require_membership(
    db: Session, team_id: int, user: User
) -> tuple[ResearchTeam, ResearchTeamMember]:
    team = db.get(ResearchTeam, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    membership = (
        db.query(ResearchTeamMember)
        .filter(
            ResearchTeamMember.team_id == team_id,
            ResearchTeamMember.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        # Non-membership is indistinguishable from a missing team.
        raise HTTPException(status_code=404, detail="Team not found")

    return team, membership
