"""Collaboration workspaces: creation, membership, and item permissions."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    CollaborationRequest,
    CollaborationWorkspace,
    FacultyResearcherLink,
    WorkspaceComment,
    WorkspaceMember,
    WorkspaceMilestone,
    WorkspaceTask,
)
from conftest import register_test_account

STUDENT_REQUESTS = "/students/me/collaboration-requests"
FACULTY_REQUESTS = "/faculty/me/collaboration-requests"
ADMIN_LINK = "/admin/faculty/{faculty_user_id}/researcher-link"
PROFILE_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
    "courses",
    "academic_details",
)


@pytest.fixture(autouse=True)
def clean_workspace_tables():
    session = SessionLocal()
    try:
        session.query(WorkspaceComment).delete()
        session.query(WorkspaceTask).delete()
        session.query(WorkspaceMilestone).delete()
        session.query(WorkspaceMember).delete()
        session.query(CollaborationWorkspace).delete()
        session.query(CollaborationRequest).delete()
        session.query(FacultyResearcherLink).delete()
        session.commit()
    finally:
        session.close()
    yield


def _student(client, areas="Machine Learning", skills="Python, PyTorch"):
    headers, user = register_test_account(client, role="student")
    saved = client.put(
        "/students/me/profile",
        json={
            **{field: "" for field in PROFILE_FIELDS},
            "research_areas": areas,
            "skills": skills,
            "academic_details": "Final-year B.Tech CSE",
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    return headers, user


def _linked_faculty(client, admin_headers, researcher_id=None):
    headers, user = register_test_account(client, role="faculty")
    researcher_id = researcher_id or client.get("/researchers/").json()[0]["id"]
    linked = client.put(
        ADMIN_LINK.format(faculty_user_id=user["id"]),
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    )
    assert linked.status_code == 200, linked.text
    return headers, user, researcher_id


def _accept(client, student_headers, faculty_headers, researcher_id):
    created = client.post(
        STUDENT_REQUESTS,
        json={"researcher_id": researcher_id, "message": "Let us build an ML project."},
        headers=student_headers,
    )
    assert created.status_code == 201, created.text
    decision = client.put(
        f"{FACULTY_REQUESTS}/{created.json()['id']}/decision",
        json={"decision": "accept", "response": "Welcome aboard."},
        headers=faculty_headers,
    )
    assert decision.status_code == 200, decision.text
    return created.json(), decision.json()


def _workspace_fixture(client, admin_headers, researcher_index=0):
    student_headers, student = _student(client)
    researcher_id = client.get("/researchers/").json()[researcher_index]["id"]
    faculty_headers, faculty, researcher_id = _linked_faculty(
        client, admin_headers, researcher_id
    )
    _, decision = _accept(
        client, student_headers, faculty_headers, researcher_id
    )
    workspace_id = decision["workspace_id"]
    assert workspace_id
    return {
        "student_headers": student_headers,
        "student": student,
        "faculty_headers": faculty_headers,
        "faculty": faculty,
        "researcher_id": researcher_id,
        "workspace_id": workspace_id,
        "url": f"/workspaces/{workspace_id}",
    }


def test_accepting_a_request_creates_a_workspace_for_both_participants(
    client, seeded_db, admin_headers
):
    student_headers, student = _student(client)
    faculty_headers, faculty, researcher_id = _linked_faculty(
        client, admin_headers
    )

    created_request, decision = _accept(
        client, student_headers, faculty_headers, researcher_id
    )

    assert decision["status"] == "accepted"
    assert decision["workspace_id"]
    workspace_id = decision["workspace_id"]

    detail = client.get(f"/workspaces/{workspace_id}", headers=student_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["id"] == workspace_id
    assert body["collaboration_request_id"] == created_request["id"]
    assert body["researcher"]["id"] == researcher_id
    assert "Dr. Ada Lovelace" in body["title"]
    members = {member["user_id"]: member for member in body["members"]}
    assert members[student["id"]]["role"] == "owner"
    assert members[faculty["id"]]["role"] == "member"

    for headers in (student_headers, faculty_headers):
        listing = client.get("/workspaces/me", headers=headers)
        assert listing.status_code == 200, listing.text
        assert [item["id"] for item in listing.json()["workspaces"]] == [
            workspace_id
        ]


def test_rejecting_a_request_creates_no_workspace(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    created = client.post(
        STUDENT_REQUESTS,
        json={
            "researcher_id": client.get("/researchers/").json()[0]["id"],
            "message": "I would like to collaborate.",
        },
        headers=student_headers,
    )
    faculty_headers, _, _ = _linked_faculty(client, admin_headers)

    decision = client.put(
        f"{FACULTY_REQUESTS}/{created.json()['id']}/decision",
        json={"decision": "reject"},
        headers=faculty_headers,
    )

    assert decision.status_code == 200, decision.text
    assert decision.json()["workspace_id"] is None
    assert client.get("/workspaces/me", headers=student_headers).json() == {
        "workspaces": []
    }
    assert client.get("/workspaces/me", headers=faculty_headers).json() == {
        "workspaces": []
    }


def test_reviewing_the_same_request_twice_creates_one_workspace(
    client, seeded_db, admin_headers, db
):
    student_headers, _ = _student(client)
    faculty_headers, _, researcher_id = _linked_faculty(client, admin_headers)
    created, decision = _accept(
        client, student_headers, faculty_headers, researcher_id
    )

    repeated = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "accept"},
        headers=faculty_headers,
    )

    assert repeated.status_code == 409, repeated.text
    assert db.query(CollaborationWorkspace).count() == 1
    assert db.query(WorkspaceMember).count() == 2
    assert client.get(
        f"/workspaces/{decision['workspace_id']}", headers=student_headers
    ).status_code == 200


def test_workspace_access_requires_membership(client, seeded_db, admin_headers):
    workspace = _workspace_fixture(client, admin_headers)
    outsider_headers, _ = _student(client)
    unrelated_faculty_headers, _ = register_test_account(client, role="faculty")

    assert client.get(workspace["url"]).status_code == 401
    assert client.get(
        "/workspaces/me", headers=outsider_headers
    ).json() == {"workspaces": []}
    for headers in (outsider_headers, unrelated_faculty_headers, admin_headers):
        denied = client.get(workspace["url"], headers=headers)
        assert denied.status_code == 404, denied.text
        assert denied.json()["detail"] == "Workspace not found"

    missing = client.get("/workspaces/987654", headers=workspace["student_headers"])
    assert missing.status_code == 404
    assert client.get("/workspaces/not-a-number", headers=workspace["student_headers"]).status_code == 422


def test_task_lifecycle_enforces_membership_and_assignee_rules(
    client, seeded_db, admin_headers
):
    workspace = _workspace_fixture(client, admin_headers)
    url = f"{workspace['url']}/tasks"
    outsider_headers, outsider = _student(client)

    created = client.post(
        url,
        json={
            "title": "Build the dataset",
            "description": "Collect and clean the training data.",
            "assignee_user_id": workspace["faculty"]["id"],
        },
        headers=workspace["student_headers"],
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "todo"
    assert task["assignee_user_id"] == workspace["faculty"]["id"]

    updated = client.put(
        f"{url}/{task['id']}",
        json={"status": "in_progress", "description": "Cleaning in progress."},
        headers=workspace["faculty_headers"],
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["title"] == "Build the dataset"

    cleared = client.put(
        f"{url}/{task['id']}",
        json={"assignee_user_id": None},
        headers=workspace["student_headers"],
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["assignee_user_id"] is None

    listing = client.get(url, headers=workspace["faculty_headers"])
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["tasks"]] == [task["id"]]

    assert client.post(
        url,
        json={"title": "Invalid", "assignee_user_id": outsider["id"]},
        headers=workspace["student_headers"],
    ).status_code == 422
    assert client.post(
        url, json={"title": "Bad status", "status": "blocked"},
        headers=workspace["student_headers"],
    ).status_code == 422
    assert client.post(
        url, json={"title": "   "}, headers=workspace["student_headers"]
    ).status_code == 422
    assert client.post(
        url, json={"title": "Intruder"}, headers=outsider_headers
    ).status_code == 404
    assert client.put(
        f"{url}/987654", json={"status": "done"},
        headers=workspace["student_headers"],
    ).status_code == 404
    assert client.put(
        f"{url}/{task['id']}", json={"status": "blocked"},
        headers=workspace["student_headers"],
    ).status_code == 422


def test_task_and_milestone_deletion_is_owner_or_creator_only(
    client, seeded_db, admin_headers
):
    workspace = _workspace_fixture(client, admin_headers)
    tasks_url = f"{workspace['url']}/tasks"

    student_task = client.post(
        tasks_url, json={"title": "Student task"},
        headers=workspace["student_headers"],
    ).json()
    faculty_task = client.post(
        tasks_url, json={"title": "Faculty task"},
        headers=workspace["faculty_headers"],
    ).json()

    denied = client.delete(
        f"{tasks_url}/{student_task['id']}", headers=workspace["faculty_headers"]
    )
    assert denied.status_code == 403, denied.text
    assert client.delete(
        f"{tasks_url}/{faculty_task['id']}", headers=workspace["faculty_headers"]
    ).status_code == 200
    assert client.delete(
        f"{tasks_url}/{student_task['id']}", headers=workspace["student_headers"]
    ).status_code == 200

    milestones_url = f"{workspace['url']}/milestones"
    faculty_milestone = client.post(
        milestones_url, json={"title": "Faculty milestone"},
        headers=workspace["faculty_headers"],
    ).json()
    assert client.delete(
        f"{milestones_url}/{faculty_milestone['id']}",
        headers=workspace["faculty_headers"],
    ).status_code == 200


def test_comments_are_scoped_to_the_workspace_and_task(client, seeded_db, admin_headers):
    workspace = _workspace_fixture(client, admin_headers)
    comments_url = f"{workspace['url']}/comments"
    task = client.post(
        f"{workspace['url']}/tasks", json={"title": "Discuss design"},
        headers=workspace["student_headers"],
    ).json()
    outsider_headers, _ = _student(client)

    created = client.post(
        comments_url,
        json={"body": "I will draft the design.", "task_id": task["id"]},
        headers=workspace["faculty_headers"],
    )
    assert created.status_code == 201, created.text
    comment = created.json()
    assert comment["task_id"] == task["id"]

    general = client.post(
        comments_url, json={"body": "General note."},
        headers=workspace["student_headers"],
    )
    assert general.status_code == 201
    assert general.json()["task_id"] is None

    filtered = client.get(
        comments_url, params={"task_id": task["id"]},
        headers=workspace["student_headers"],
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["comments"]] == [comment["id"]]

    assert client.post(
        comments_url, json={"body": "Intruder"},
        headers=outsider_headers,
    ).status_code == 404
    assert client.post(
        comments_url, json={"body": " ", "task_id": task["id"]},
        headers=workspace["student_headers"],
    ).status_code == 422

    # Another workspace's task is not addressable from here.
    other = _workspace_fixture(client, admin_headers, researcher_index=1)
    other_task = client.post(
        f"{other['url']}/tasks", json={"title": "Other"},
        headers=other["student_headers"],
    ).json()
    assert client.post(
        comments_url,
        json={"body": "Cross-workspace", "task_id": other_task["id"]},
        headers=workspace["student_headers"],
    ).status_code == 404

    assert client.delete(
        f"{comments_url}/{comment['id']}", headers=workspace["student_headers"]
    ).status_code == 200
    general_id = general.json()["id"]
    assert client.delete(
        f"{comments_url}/{general_id}", headers=workspace["faculty_headers"]
    ).status_code == 403


def test_milestones_lifecycle_and_validation(client, seeded_db, admin_headers):
    workspace = _workspace_fixture(client, admin_headers)
    url = f"{workspace['url']}/milestones"

    created = client.post(
        url, json={"title": "First prototype", "due_at": 1_800_000_000},
        headers=workspace["student_headers"],
    )
    assert created.status_code == 201, created.text
    milestone = created.json()
    assert milestone["status"] == "pending"
    assert milestone["completed_at"] is None

    completed = client.put(
        f"{url}/{milestone['id']}", json={"status": "completed"},
        headers=workspace["faculty_headers"],
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"]

    listing = client.get(url, headers=workspace["faculty_headers"])
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["milestones"]] == [
        milestone["id"]
    ]

    assert client.post(
        url, json={"title": ""}, headers=workspace["student_headers"]
    ).status_code == 422
    assert client.put(
        f"{url}/{milestone['id']}", json={"status": "blocked"},
        headers=workspace["student_headers"],
    ).status_code == 422
    assert client.put(
        f"{url}/987654", json={"status": "completed"},
        headers=workspace["student_headers"],
    ).status_code == 404


def test_task_listing_is_paginated(client, seeded_db, admin_headers):
    workspace = _workspace_fixture(client, admin_headers)
    for title in ("One", "Two", "Three"):
        assert client.post(
            f"{workspace['url']}/tasks", json={"title": title},
            headers=workspace["student_headers"],
        ).status_code == 201

    page = client.get(
        f"{workspace['url']}/tasks", params={"limit": 2, "offset": 1},
        headers=workspace["student_headers"],
    )

    assert page.status_code == 200
    assert len(page.json()["tasks"]) == 2


def test_workspace_database_constraints(client, seeded_db, admin_headers, db):
    workspace = _workspace_fixture(client, admin_headers)
    record = db.get(CollaborationWorkspace, workspace["workspace_id"])

    duplicate_member = WorkspaceMember(
        workspace_id=record.id,
        user_id=workspace["faculty"]["id"],
        role="member",
        created_at=1,
    )
    db.add(duplicate_member)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    duplicate_workspace = CollaborationWorkspace(
        collaboration_request_id=record.collaboration_request_id,
        researcher_id=record.researcher_id,
        student_user_id=record.student_user_id,
        faculty_user_id=record.faculty_user_id,
        title="Duplicate",
        status="active",
        created_at=1,
        updated_at=1,
    )
    db.add(duplicate_workspace)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_workspace_items_are_inaccessible_after_leaving(
    client, seeded_db, admin_headers, db
):
    workspace = _workspace_fixture(client, admin_headers)
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace["workspace_id"],
            WorkspaceMember.user_id == workspace["faculty"]["id"],
        )
        .one()
    )
    db.delete(membership)
    db.commit()

    denied = client.get(workspace["url"], headers=workspace["faculty_headers"])
    assert denied.status_code == 404
