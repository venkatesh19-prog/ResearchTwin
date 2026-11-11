import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    CollaborationWorkspace,
    Researcher,
    User,
    WorkspaceComment,
    WorkspaceMember,
    WorkspaceMilestone,
    WorkspaceTask,
)
from ..schemas import (
    WorkspaceCommentCreate,
    WorkspaceMilestoneCreate,
    WorkspaceMilestoneUpdate,
    WorkspaceTaskCreate,
    WorkspaceTaskUpdate,
)
from ..services.workspaces import (
    OWNER_ROLE,
    member_user_ids,
    require_member,
)
from .deps import get_current_user

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


def _researcher_brief(researcher: Researcher | None) -> dict:
    if researcher is None:
        return {"id": None, "name": None, "department": None}
    return {
        "id": researcher.id,
        "name": researcher.name,
        "department": researcher.department,
    }


def _workspace_payload(
    db: Session, workspace, membership: WorkspaceMember
) -> dict:
    members = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace.id)
        .order_by(WorkspaceMember.id)
        .all()
    )
    users = {
        user.id: user
        for user in db.query(User)
        .filter(User.id.in_({member.user_id for member in members}))
        .all()
    }
    researcher = db.get(Researcher, workspace.researcher_id)

    return {
        "id": workspace.id,
        "title": workspace.title,
        "status": workspace.status,
        "collaboration_request_id": workspace.collaboration_request_id,
        "researcher": _researcher_brief(researcher),
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
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
    }


def _task_payload(task: WorkspaceTask) -> dict:
    return {
        "id": task.id,
        "workspace_id": task.workspace_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assignee_user_id": task.assignee_user_id,
        "created_by_user_id": task.created_by_user_id,
        "due_at": task.due_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _comment_payload(comment: WorkspaceComment) -> dict:
    return {
        "id": comment.id,
        "workspace_id": comment.workspace_id,
        "task_id": comment.task_id,
        "author_user_id": comment.author_user_id,
        "body": comment.body,
        "created_at": comment.created_at,
    }


def _milestone_payload(milestone: WorkspaceMilestone) -> dict:
    return {
        "id": milestone.id,
        "workspace_id": milestone.workspace_id,
        "title": milestone.title,
        "status": milestone.status,
        "due_at": milestone.due_at,
        "completed_at": milestone.completed_at,
        "created_by_user_id": milestone.created_by_user_id,
        "created_at": milestone.created_at,
        "updated_at": milestone.updated_at,
    }


def _task_in_workspace(
    db: Session, workspace_id: int, task_id: int
) -> WorkspaceTask:
    task = (
        db.query(WorkspaceTask)
        .filter(
            WorkspaceTask.id == task_id,
            WorkspaceTask.workspace_id == workspace_id,
        )
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _milestone_in_workspace(
    db: Session, workspace_id: int, milestone_id: int
) -> WorkspaceMilestone:
    milestone = (
        db.query(WorkspaceMilestone)
        .filter(
            WorkspaceMilestone.id == milestone_id,
            WorkspaceMilestone.workspace_id == workspace_id,
        )
        .first()
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone


@router.get("/me")
def list_my_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == user.id)
        .order_by(WorkspaceMember.id.desc())
        .all()
    )
    if not memberships:
        return {"workspaces": []}

    workspace_ids = {membership.workspace_id for membership in memberships}
    workspaces = {
        workspace.id: workspace
        for workspace in db.query(CollaborationWorkspace)
        .filter(CollaborationWorkspace.id.in_(workspace_ids))
        .all()
    }
    researchers = {
        researcher.id: researcher
        for researcher in db.query(Researcher)
        .filter(
            Researcher.id.in_(
                {workspace.researcher_id for workspace in workspaces.values()}
            )
        )
        .all()
    }
    counts = dict(
        db.query(WorkspaceMember.workspace_id, func.count(WorkspaceMember.id))
        .filter(WorkspaceMember.workspace_id.in_(workspace_ids))
        .group_by(WorkspaceMember.workspace_id)
        .all()
    )

    items = []
    for membership in memberships:
        workspace = workspaces.get(membership.workspace_id)
        if workspace is None:
            continue
        items.append(
            {
                "id": workspace.id,
                "title": workspace.title,
                "status": workspace.status,
                "collaboration_request_id": workspace.collaboration_request_id,
                "researcher": _researcher_brief(
                    researchers.get(workspace.researcher_id)
                ),
                "role": membership.role,
                "member_count": counts.get(workspace.id, 0),
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at,
            }
        )

    return {"workspaces": items}


@router.get("/{workspace_id}")
def get_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace, membership = require_member(db, workspace_id, user)
    return _workspace_payload(db, workspace, membership)


@router.get("/{workspace_id}/tasks")
def list_tasks(
    workspace_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    tasks = (
        db.query(WorkspaceTask)
        .filter(WorkspaceTask.workspace_id == workspace_id)
        .order_by(WorkspaceTask.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"tasks": [_task_payload(task) for task in tasks]}


@router.post("/{workspace_id}/tasks", status_code=201)
def create_task(
    workspace_id: int,
    payload: WorkspaceTaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    if (
        payload.assignee_user_id is not None
        and payload.assignee_user_id not in member_user_ids(db, workspace_id)
    ):
        raise HTTPException(
            status_code=422,
            detail="The assignee must be a member of this workspace",
        )

    now = int(time.time())
    task = WorkspaceTask(
        workspace_id=workspace_id,
        title=payload.title,
        description=payload.description,
        status="todo",
        assignee_user_id=payload.assignee_user_id,
        created_by_user_id=user.id,
        due_at=payload.due_at,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_payload(task)


@router.put("/{workspace_id}/tasks/{task_id}")
def update_task(
    workspace_id: int,
    task_id: int,
    payload: WorkspaceTaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    task = _task_in_workspace(db, workspace_id, task_id)
    fields = payload.model_fields_set

    if "title" in fields:
        task.title = payload.title
    if "description" in fields:
        task.description = payload.description
    if "status" in fields:
        task.status = payload.status
    if "assignee_user_id" in fields:
        if (
            payload.assignee_user_id is not None
            and payload.assignee_user_id not in member_user_ids(db, workspace_id)
        ):
            raise HTTPException(
                status_code=422,
                detail="The assignee must be a member of this workspace",
            )
        task.assignee_user_id = payload.assignee_user_id
    if "due_at" in fields:
        task.due_at = payload.due_at

    task.updated_at = int(time.time())
    db.commit()
    db.refresh(task)
    return _task_payload(task)


@router.delete("/{workspace_id}/tasks/{task_id}")
def delete_task(
    workspace_id: int,
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, membership = require_member(db, workspace_id, user)
    task = _task_in_workspace(db, workspace_id, task_id)

    if membership.role != OWNER_ROLE and task.created_by_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the workspace owner or the task creator can delete this task",
        )

    db.query(WorkspaceComment).filter(
        WorkspaceComment.task_id == task.id
    ).update({WorkspaceComment.task_id: None}, synchronize_session=False)
    db.delete(task)
    db.commit()
    return {"deleted": True}


@router.get("/{workspace_id}/comments")
def list_comments(
    workspace_id: int,
    task_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    query = db.query(WorkspaceComment).filter(
        WorkspaceComment.workspace_id == workspace_id
    )
    if task_id is not None:
        _task_in_workspace(db, workspace_id, task_id)
        query = query.filter(WorkspaceComment.task_id == task_id)

    comments = query.order_by(WorkspaceComment.id).offset(offset).limit(limit).all()
    return {"comments": [_comment_payload(comment) for comment in comments]}


@router.post("/{workspace_id}/comments", status_code=201)
def create_comment(
    workspace_id: int,
    payload: WorkspaceCommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    if payload.task_id is not None:
        _task_in_workspace(db, workspace_id, payload.task_id)

    comment = WorkspaceComment(
        workspace_id=workspace_id,
        task_id=payload.task_id,
        author_user_id=user.id,
        body=payload.body,
        created_at=int(time.time()),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _comment_payload(comment)


@router.delete("/{workspace_id}/comments/{comment_id}")
def delete_comment(
    workspace_id: int,
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, membership = require_member(db, workspace_id, user)
    comment = (
        db.query(WorkspaceComment)
        .filter(
            WorkspaceComment.id == comment_id,
            WorkspaceComment.workspace_id == workspace_id,
        )
        .first()
    )
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    if membership.role != OWNER_ROLE and comment.author_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the workspace owner or the comment author can delete this comment",
        )

    db.delete(comment)
    db.commit()
    return {"deleted": True}


@router.get("/{workspace_id}/milestones")
def list_milestones(
    workspace_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    milestones = (
        db.query(WorkspaceMilestone)
        .filter(WorkspaceMilestone.workspace_id == workspace_id)
        .order_by(WorkspaceMilestone.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"milestones": [_milestone_payload(item) for item in milestones]}


@router.post("/{workspace_id}/milestones", status_code=201)
def create_milestone(
    workspace_id: int,
    payload: WorkspaceMilestoneCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    now = int(time.time())
    milestone = WorkspaceMilestone(
        workspace_id=workspace_id,
        title=payload.title,
        status="pending",
        due_at=payload.due_at,
        completed_at=None,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return _milestone_payload(milestone)


@router.put("/{workspace_id}/milestones/{milestone_id}")
def update_milestone(
    workspace_id: int,
    milestone_id: int,
    payload: WorkspaceMilestoneUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_member(db, workspace_id, user)
    milestone = _milestone_in_workspace(db, workspace_id, milestone_id)
    fields = payload.model_fields_set
    now = int(time.time())

    if "title" in fields:
        milestone.title = payload.title
    if "status" in fields:
        milestone.status = payload.status
        milestone.completed_at = now if payload.status == "completed" else None
    if "due_at" in fields:
        milestone.due_at = payload.due_at

    milestone.updated_at = now
    db.commit()
    db.refresh(milestone)
    return _milestone_payload(milestone)


@router.delete("/{workspace_id}/milestones/{milestone_id}")
def delete_milestone(
    workspace_id: int,
    milestone_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, membership = require_member(db, workspace_id, user)
    milestone = _milestone_in_workspace(db, workspace_id, milestone_id)

    if membership.role != OWNER_ROLE and milestone.created_by_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the workspace owner or the milestone creator can delete this milestone",
        )

    db.delete(milestone)
    db.commit()
    return {"deleted": True}
