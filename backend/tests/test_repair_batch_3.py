"""Regression tests for Repair Batch 3 (atomic registration, apply limit, history paging)."""

import uuid

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import User
from conftest import register_test_account


def _email(prefix):
    return f"{prefix}-{uuid.uuid4().hex}@example.test"


def test_registration_rolls_back_account_when_session_creation_fails(
    client, monkeypatch
):
    email = _email("atomic")
    payload = {
        "email": email,
        "password": "TestPassword123!",
        "full_name": "Atomic Student",
        "role": "student",
    }

    def fail_session(db, user, *, commit=True):
        raise SQLAlchemyError("session storage unavailable")

    monkeypatch.setattr("app.api.auth.create_session", fail_session)
    response = client.post("/auth/register", json=payload)
    assert response.status_code >= 500, response.text

    session = SessionLocal()
    try:
        assert session.query(User).filter(User.email == email).count() == 0
    finally:
        session.close()

    monkeypatch.undo()
    retry = client.post("/auth/register", json=payload)
    assert retry.status_code == 201, retry.text


def test_opportunity_application_is_rate_limited(client, admin_headers, monkeypatch):
    created = []
    for index in range(2):
        response = client.post(
            "/opportunities",
            json={
                "category": "research",
                "title": f"Rate Limited Call {index} {uuid.uuid4().hex[:6]}",
                "description": "Open research call.",
                "status": "open",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        created.append(response.json()["id"])

    headers, _ = register_test_account(client, role="student")
    monkeypatch.setattr("app.api.opportunities.OPPORTUNITY_APPLY_MAX", 1)

    first = client.post(
        f"/opportunities/{created[0]}/applications",
        json={"message": "First application."},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    limited = client.post(
        f"/opportunities/{created[1]}/applications",
        json={"message": "Second application."},
        headers=headers,
    )
    assert limited.status_code == 429, limited.text
    assert int(limited.headers["retry-after"]) > 0


def test_proposal_versions_are_paginated(client):
    headers, _ = register_test_account(client, role="student")
    proposal = client.post(
        "/proposals",
        json={"title": f"Paged Proposal {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert proposal.status_code == 201, proposal.text
    proposal_id = proposal.json()["id"]

    for index in range(3):
        section = client.post(
            f"/proposals/{proposal_id}/sections",
            json={"heading": f"Section {index}", "body": "Draft text."},
            headers=headers,
        )
        assert section.status_code == 201, section.text

    first_page = client.get(
        f"/proposals/{proposal_id}/versions",
        params={"limit": 2, "offset": 0},
        headers=headers,
    )
    assert first_page.status_code == 200, first_page.text
    body = first_page.json()
    assert body["total"] == 4
    assert [item["version"] for item in body["versions"]] == [4, 3]

    second_page = client.get(
        f"/proposals/{proposal_id}/versions",
        params={"limit": 2, "offset": 2},
        headers=headers,
    )
    assert second_page.status_code == 200, second_page.text
    assert [item["version"] for item in second_page.json()["versions"]] == [2, 1]


def test_publication_detail_history_and_revisions_are_paginated(client):
    headers, _ = register_test_account(client, role="student")
    created = client.post(
        "/publication-submissions",
        json={
            "title": f"Paged Submission {uuid.uuid4().hex[:6]}",
            "venue": "Journal of Research Systems",
            "venue_type": "journal",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    for status in ("submitted", "under_review", "revision_requested"):
        moved = client.post(
            f"/publication-submissions/{submission_id}/status",
            json={"status": status, "note": f"Moved to {status}."},
            headers=headers,
        )
        assert moved.status_code == 200, moved.text

    for index in range(3):
        revision = client.post(
            f"/publication-submissions/{submission_id}/revisions",
            json={"notes": f"Revision {index}"},
            headers=headers,
        )
        assert revision.status_code == 201, revision.text

    detail = client.get(
        f"/publication-submissions/{submission_id}",
        params={
            "revision_limit": 2,
            "revision_offset": 0,
            "history_limit": 2,
            "history_offset": 0,
        },
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["revisions_total"] == 3
    assert len(body["revisions"]) == 2
    assert [item["revision_number"] for item in body["revisions"]] == [1, 2]
    assert body["history_total"] == 3
    assert [event["to_status"] for event in body["history"]] == [
        "revision_requested",
        "under_review",
    ]

    tail = client.get(
        f"/publication-submissions/{submission_id}",
        params={
            "revision_limit": 2,
            "revision_offset": 2,
            "history_limit": 2,
            "history_offset": 2,
        },
        headers=headers,
    )
    assert tail.status_code == 200, tail.text
    assert [item["revision_number"] for item in tail.json()["revisions"]] == [3]
    assert [event["to_status"] for event in tail.json()["history"]] == ["submitted"]
