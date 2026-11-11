"""Thesis tracking with supervisors, milestones and progress history."""

import pytest

from app.database import SessionLocal
from app.models import (
    RoadmapProgress,
    ThesisMilestone,
    ThesisProgressEvent,
    ThesisRecord,
)
from conftest import register_test_account

THESES = "/theses"


@pytest.fixture(autouse=True)
def clean_thesis_tables():
    session = SessionLocal()
    try:
        session.query(ThesisProgressEvent).delete()
        session.query(ThesisMilestone).delete()
        session.query(ThesisRecord).delete()
        session.query(RoadmapProgress).delete()
        session.commit()
    finally:
        session.close()
    yield


def _student(client):
    return register_test_account(client, role="student")


def _faculty(client):
    return register_test_account(client, role="faculty")


def _create(client, headers, **overrides):
    payload = {
        "title": "Adaptive Retrieval for Research Discovery",
        "abstract": "A study of retrieval-augmented research workflows.",
        "supervisor_user_id": None,
    }
    payload.update(overrides)
    return client.post(THESES, json=payload, headers=headers)


def _milestone(client, headers, thesis_id, title="Proposal defence", due_at=None):
    response = client.post(
        f"{THESES}/{thesis_id}/milestones",
        json={"title": title, "due_at": due_at},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------
# OWNERSHIP AND SUPERVISION
# --------------------------------------------------


def test_thesis_endpoints_require_authentication(client):
    assert client.get(THESES).status_code == 401
    assert client.post(THESES, json={"title": "Thesis"}).status_code == 401


def test_only_students_create_theses(client):
    faculty_headers, _ = _faculty(client)
    response = _create(client, faculty_headers)
    assert response.status_code == 403


def test_student_creates_thesis_with_faculty_supervisor(client):
    student_headers, student = _student(client)
    supervisor_headers, supervisor = _faculty(client)
    outsider_headers, _ = _student(client)

    response = _create(
        client,
        student_headers,
        supervisor_user_id=supervisor["id"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    thesis_id = body["id"]
    assert body["status"] == "proposed"
    assert body["access_role"] == "owner"
    assert body["owner"] == {
        "user_id": student["id"],
        "full_name": student["full_name"],
    }
    assert body["supervisor"] == {
        "user_id": supervisor["id"],
        "full_name": supervisor["full_name"],
    }
    assert body["milestones"] == []

    supervisor_view = client.get(f"{THESES}/{thesis_id}", headers=supervisor_headers)
    assert supervisor_view.status_code == 200, supervisor_view.text
    assert supervisor_view.json()["access_role"] == "supervisor"

    assert client.get(f"{THESES}/{thesis_id}", headers=outsider_headers).status_code == 404

    history = client.get(f"{THESES}/{thesis_id}/history", headers=supervisor_headers)
    assert history.status_code == 200, history.text
    event_types = [event["event_type"] for event in history.json()["events"]]
    assert event_types == ["supervisor_assigned", "thesis_created"]

    listing = client.get(THESES, headers=supervisor_headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["theses"][0]["access_role"] == "supervisor"
    student_listing = client.get(THESES, headers=student_headers)
    assert student_listing.json()["theses"][0]["access_role"] == "owner"


def test_supervisor_must_be_an_active_faculty_account(client):
    student_headers, _ = _student(client)
    other_student_headers, other_student = _student(client)

    non_faculty = _create(
        client, student_headers, supervisor_user_id=other_student["id"]
    )
    assert non_faculty.status_code == 422

    missing = _create(client, student_headers, supervisor_user_id=999999)
    assert missing.status_code == 404


def test_owner_controls_thesis_metadata_and_supervisor(client):
    student_headers, _ = _student(client)
    first_supervisor_headers, first_supervisor = _faculty(client)
    second_supervisor_headers, second_supervisor = _faculty(client)

    thesis = _create(
        client, student_headers, supervisor_user_id=first_supervisor["id"]
    ).json()
    thesis_id = thesis["id"]

    forbidden = client.put(
        f"{THESES}/{thesis_id}",
        json={"title": "Supervisor cannot rename"},
        headers=first_supervisor_headers,
    )
    assert forbidden.status_code == 403
    assert (
        client.delete(f"{THESES}/{thesis_id}", headers=first_supervisor_headers).status_code
        == 403
    )

    updated = client.put(
        f"{THESES}/{thesis_id}",
        json={
            "title": "Refined Thesis Title",
            "abstract": "Revised abstract.",
            "supervisor_user_id": second_supervisor["id"],
        },
        headers=student_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Refined Thesis Title"
    assert updated.json()["supervisor"]["user_id"] == second_supervisor["id"]

    assert (
        client.get(f"{THESES}/{thesis_id}", headers=first_supervisor_headers).status_code
        == 404
    )
    assert (
        client.get(f"{THESES}/{thesis_id}", headers=second_supervisor_headers).status_code
        == 200
    )

    cleared = client.put(
        f"{THESES}/{thesis_id}",
        json={"supervisor_user_id": None},
        headers=student_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["supervisor"] is None


def test_thesis_status_transitions_are_recorded(client):
    student_headers, _ = _student(client)
    thesis_id = _create(client, student_headers).json()["id"]

    def move(status, note=""):
        return client.put(
            f"{THESES}/{thesis_id}",
            json={"status": status, "note": note},
            headers=student_headers,
        )

    assert move("in_progress", "Started the literature review.").status_code == 200
    invalid = move("completed")
    assert invalid.status_code == 409
    assert move("in_progress").status_code == 409
    assert move("submitted").status_code == 200
    assert move("defended").status_code == 200
    assert move("completed").status_code == 200

    terminal = move("in_progress")
    assert terminal.status_code == 409

    history = client.get(f"{THESES}/{thesis_id}/history", headers=student_headers)
    events = history.json()["events"]
    status_events = [
        event for event in events if event["event_type"] == "status_changed"
    ]
    assert [
        (event["from_status"], event["to_status"]) for event in status_events
    ] == [
        ("defended", "completed"),
        ("submitted", "defended"),
        ("in_progress", "submitted"),
        ("proposed", "in_progress"),
    ]
    assert any(
        event["note"] == "Started the literature review." for event in status_events
    )


# --------------------------------------------------
# MILESTONES AND PROGRESS HISTORY
# --------------------------------------------------


def test_supervisor_and_owner_manage_milestones_with_history(client):
    student_headers, _ = _student(client)
    supervisor_headers, supervisor = _faculty(client)
    thesis = _create(
        client, student_headers, supervisor_user_id=supervisor["id"]
    ).json()
    thesis_id = thesis["id"]

    first = _milestone(
        client, student_headers, thesis_id, "Proposal defence", 1_800_000_000
    )
    second = _milestone(client, supervisor_headers, thesis_id, "Final defence")
    assert (first["position"], second["position"]) == (0, 1)
    assert first["status"] == "pending"

    completed = client.put(
        f"{THESES}/{thesis_id}/milestones/{first['id']}",
        json={"status": "completed"},
        headers=supervisor_headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    reopened = client.put(
        f"{THESES}/{thesis_id}/milestones/{first['id']}",
        json={"status": "pending", "due_at": 1_810_000_000},
        headers=student_headers,
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["completed_at"] is None
    assert reopened.json()["due_at"] == 1_810_000_000

    edited = client.put(
        f"{THESES}/{thesis_id}/milestones/{second['id']}",
        json={"title": "Thesis defence"},
        headers=supervisor_headers,
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Thesis defence"

    assert (
        client.delete(
            f"{THESES}/{thesis_id}/milestones/{second['id']}",
            headers=supervisor_headers,
        ).status_code
        == 403
    )
    removed = client.delete(
        f"{THESES}/{thesis_id}/milestones/{second['id']}",
        headers=student_headers,
    )
    assert removed.status_code == 200, removed.text

    detail = client.get(f"{THESES}/{thesis_id}", headers=student_headers).json()
    assert len(detail["milestones"]) == 1
    assert detail["milestones"][0]["position"] == 0

    history = client.get(f"{THESES}/{thesis_id}/history", headers=student_headers)
    event_types = [event["event_type"] for event in history.json()["events"]]
    assert "milestone_added" in event_types
    assert "milestone_completed" in event_types
    assert "milestone_reopened" in event_types
    assert "milestone_updated" in event_types
    assert "milestone_deleted" in event_types


def test_thesis_progress_is_separate_from_skill_roadmap(client, seeded_db):
    student_headers, student = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    session = SessionLocal()
    try:
        session.add(
            RoadmapProgress(
                user_id=student["id"],
                researcher_id=researcher_id,
                skill="Python",
                milestone_index=0,
                is_completed=False,
                updated_at=1_700_000_000,
            )
        )
        session.commit()
    finally:
        session.close()

    thesis_id = _create(client, student_headers).json()["id"]
    milestone = _milestone(client, student_headers, thesis_id, "Chapter draft")
    client.put(
        f"{THESES}/{thesis_id}/milestones/{milestone['id']}",
        json={"status": "completed"},
        headers=student_headers,
    )

    session = SessionLocal()
    try:
        assert session.query(RoadmapProgress).count() == 1
        roadmap = session.query(RoadmapProgress).one()
        assert roadmap.skill == "Python"
        assert roadmap.milestone_index == 0
        assert roadmap.is_completed is False
    finally:
        session.close()


def test_thesis_validation_and_cascade_delete(client):
    student_headers, _ = _student(client)
    thesis = _create(client, student_headers).json()
    thesis_id = thesis["id"]
    milestone = _milestone(client, student_headers, thesis_id)

    assert (
        client.post(THESES, json={"title": "   "}, headers=student_headers).status_code
        == 422
    )
    assert (
        client.post(
            f"{THESES}/{thesis_id}/milestones",
            json={"title": "   "},
            headers=student_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{THESES}/{thesis_id}/milestones",
            json={"title": "Bad deadline", "due_at": -1},
            headers=student_headers,
        ).status_code
        == 422
    )

    deleted = client.delete(f"{THESES}/{thesis_id}", headers=student_headers)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"{THESES}/{thesis_id}", headers=student_headers).status_code == 404

    session = SessionLocal()
    try:
        assert session.query(ThesisRecord).count() == 0
        assert session.query(ThesisMilestone).count() == 0
        assert session.query(ThesisProgressEvent).count() == 0
    finally:
        session.close()
    assert milestone["id"]
