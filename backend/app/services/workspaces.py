"""Workspace creation and membership checks."""

import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    CollaborationRequest,
    CollaborationWorkspace,
    Researcher,
    User,
    WorkspaceMember,
)

OWNER_ROLE = "owner"
MEMBER_ROLE = "member"


def create_for_accepted_request(
    db: Session,
    *,
    request: CollaborationRequest,
    researcher: Researcher | None,
    faculty_user_id: int,
) -> CollaborationWorkspace:
    """Create the workspace and both memberships in the caller's transaction."""
    now = int(time.time())
    title = (
        f"Collaboration: {researcher.name}"
        if researcher is not None
        else "Collaboration workspace"
    )
    workspace = CollaborationWorkspace(
        collaboration_request_id=request.id,
        researcher_id=request.researcher_id,
        student_user_id=request.student_user_id,
        faculty_user_id=faculty_user_id,
        title=title[:200],
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(workspace)
    db.flush()

    db.add_all(
        [
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=request.student_user_id,
                role=OWNER_ROLE,
                created_at=now,
            ),
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=faculty_user_id,
                role=MEMBER_ROLE,
                created_at=now,
            ),
        ]
    )
    db.flush()
    return workspace


def require_member(
    db: Session, workspace_id: int, user: User
) -> tuple[CollaborationWorkspace, WorkspaceMember]:
    workspace = db.get(CollaborationWorkspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        # Non-membership is indistinguishable from a missing workspace.
        raise HTTPException(status_code=404, detail="Workspace not found")

    return workspace, membership


def member_user_ids(db: Session, workspace_id: int) -> set[int]:
    return {
        row[0]
        for row in db.query(WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    }
