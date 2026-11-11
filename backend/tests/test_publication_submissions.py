"""Publication submission tracking: venues, transitions, revisions, history."""

import pytest

from app.database import SessionLocal
from app.models import (
    PublicationRevision,
    PublicationStatusEvent,
    PublicationSubmission,
)
from conftest import register_test_account

SUBMISSIONS = "/publication-submissions"


@pytest.fixture(autouse=True)
def clean_publication_tables():
    session = SessionLocal()
    try:
        session.query(PublicationStatusEvent).delete()
        session.query(PublicationRevision).delete()
        session.query(PublicationSubmission).delete()
        session.commit()
    finally:
        session.close()
    yield


def _account(client, role="student"):
    return register_test_account(client, role=role)


def _create(client, headers, **overrides):
    payload = {
        "title": "Retrieval-Augmented Research Discovery",
        "venue": "Journal of Research Systems",
        "venue_type": "journal",
        "doi": "",
        "url": "https://example.org/submission",
        "notes": "Initial submission notes.",
    }
    payload.update(overrides)
    return client.post(SUBMISSIONS, json=payload, headers=headers)


def _move(client, headers, submission_id, status, note=""):
    return client.post(
        f"{SUBMISSIONS}/{submission_id}/status",
        json={"status": status, "note": note},
        headers=headers,
    )


def test_publication_endpoints_require_authentication(client):
    assert client.get(SUBMISSIONS).status_code == 401
    assert (
        client.post(SUBMISSIONS, json={"title": "Paper"}).status_code == 401
    )


def test_create_draft_and_private_ownership(client):
    owner_headers, _ = _account(client)
    other_headers, _ = _account(client)
    response = _create(client, owner_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    submission_id = body["id"]
    assert body["status"] == "draft"
    assert body["venue_type"] == "journal"
    assert body["submitted_at"] is None
    assert body["decision_at"] is None
    assert body["published_at"] is None
    assert body["revisions"] == []
    assert body["history"] == []

    assert (
        client.get(f"{SUBMISSIONS}/{submission_id}", headers=other_headers).status_code
        == 404
    )
    assert (
        client.put(
            f"{SUBMISSIONS}/{submission_id}",
            json={"title": "Hijacked"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert client.get(SUBMISSIONS, headers=other_headers).json()["submissions"] == []
    assert client.get(SUBMISSIONS, headers=owner_headers).json()["total"] == 1


def test_full_status_lifecycle_with_revision_and_history(client):
    headers, _ = _account(client)
    submission_id = _create(client, headers).json()["id"]

    submitted = _move(client, headers, submission_id, "submitted", "Submitted to journal.")
    assert submitted.status_code == 200, submitted.text
    first_submitted_at = submitted.json()["submitted_at"]
    assert first_submitted_at is not None

    assert _move(client, headers, submission_id, "under_review").status_code == 200
    requested = _move(
        client, headers, submission_id, "revision_requested", "Minor revisions."
    )
    assert requested.status_code == 200, requested.text
    assert requested.json()["status"] == "revision_requested"

    revision = client.post(
        f"{SUBMISSIONS}/{submission_id}/revisions",
        json={"notes": "Addressed reviewer comments on evaluation."},
        headers=headers,
    )
    assert revision.status_code == 201, revision.text
    assert revision.json()["revision_number"] == 1

    assert _move(client, headers, submission_id, "submitted").status_code == 200
    assert _move(client, headers, submission_id, "under_review").status_code == 200
    accepted = _move(client, headers, submission_id, "accepted", "Accepted.")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decision_at"] is not None
    published = _move(client, headers, submission_id, "published")
    assert published.status_code == 200, published.text
    assert published.json()["published_at"] is not None
    assert published.json()["submitted_at"] == first_submitted_at

    detail = client.get(f"{SUBMISSIONS}/{submission_id}", headers=headers).json()
    assert detail["status"] == "published"
    assert len(detail["revisions"]) == 1
    assert detail["revisions"][0]["notes"].startswith("Addressed reviewer")
    transitions = [
        (event["from_status"], event["to_status"]) for event in detail["history"]
    ]
    assert transitions == [
        ("accepted", "published"),
        ("under_review", "accepted"),
        ("submitted", "under_review"),
        ("revision_requested", "submitted"),
        ("under_review", "revision_requested"),
        ("submitted", "under_review"),
        ("draft", "submitted"),
    ]
    assert detail["history"][0]["note"] == ""
    assert detail["history"][-1]["note"] == "Submitted to journal."


def test_invalid_status_transitions_are_rejected(client):
    headers, _ = _account(client)
    submission_id = _create(client, headers).json()["id"]

    assert _move(client, headers, submission_id, "accepted").status_code == 409
    assert _move(client, headers, submission_id, "draft").status_code == 409
    assert _move(client, headers, submission_id, "unknown").status_code == 422
    assert _move(client, headers, submission_id, "submitted").status_code == 200
    assert _move(client, headers, submission_id, "submitted").status_code == 409
    assert _move(client, headers, submission_id, "under_review").status_code == 200
    assert _move(client, headers, submission_id, "published").status_code == 409


def test_revision_rules(client):
    headers, _ = _account(client)
    submission_id = _create(client, headers).json()["id"]

    assert (
        client.post(
            f"{SUBMISSIONS}/{submission_id}/revisions",
            json={"notes": "Cannot revise a draft."},
            headers=headers,
        ).status_code
        == 409
    )
    assert _move(client, headers, submission_id, "submitted").status_code == 200
    blank = client.post(
        f"{SUBMISSIONS}/{submission_id}/revisions",
        json={"notes": "   "},
        headers=headers,
    )
    assert blank.status_code == 422

    first = client.post(
        f"{SUBMISSIONS}/{submission_id}/revisions",
        json={"notes": "Revision one.", "submitted_at": 1_800_000_000},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    assert first.json()["submitted_at"] == 1_800_000_000
    second = client.post(
        f"{SUBMISSIONS}/{submission_id}/revisions",
        json={"notes": "Revision two."},
        headers=headers,
    )
    assert second.status_code == 201
    assert second.json()["revision_number"] == 2

    assert _move(client, headers, submission_id, "under_review").status_code == 200
    assert _move(client, headers, submission_id, "accepted").status_code == 200
    assert _move(client, headers, submission_id, "published").status_code == 200
    terminal = client.post(
        f"{SUBMISSIONS}/{submission_id}/revisions",
        json={"notes": "Too late."},
        headers=headers,
    )
    assert terminal.status_code == 409


def test_metadata_update_validation_and_list_filtering(client):
    headers, _ = _account(client, role="faculty")
    first = _create(client, headers).json()
    second = _create(client, headers, title="Second Paper", venue_type="conference").json()

    updated = client.put(
        f"{SUBMISSIONS}/{first['id']}",
        json={
            "title": "Refined Submission",
            "venue": "International Conference on Retrieval",
            "venue_type": "conference",
            "doi": "10.1000/refined",
            "notes": "Updated notes.",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["venue_type"] == "conference"
    assert updated.json()["doi"] == "10.1000/refined"

    assert (
        client.put(
            f"{SUBMISSIONS}/{first['id']}",
            json={"venue_type": "blog"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{SUBMISSIONS}/{first['id']}",
            json={"url": "javascript:alert(1)"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{SUBMISSIONS}/{first['id']}",
            json={"status": "submitted"},
            headers=headers,
        ).status_code
        == 422
    )

    assert _move(client, headers, second["id"], "submitted").status_code == 200
    submitted_only = client.get(
        f"{SUBMISSIONS}?status=submitted", headers=headers
    ).json()
    assert submitted_only["total"] == 1
    assert submitted_only["submissions"][0]["id"] == second["id"]

    page = client.get(f"{SUBMISSIONS}?limit=1", headers=headers).json()
    assert page["total"] == 2
    assert len(page["submissions"]) == 1
    assert page["submissions"][0]["latest_revision"] == 0


def test_delete_cascades_revisions_and_history(client):
    headers, _ = _account(client)
    submission_id = _create(client, headers).json()["id"]
    assert _move(client, headers, submission_id, "submitted").status_code == 200
    assert (
        client.post(
            f"{SUBMISSIONS}/{submission_id}/revisions",
            json={"notes": "Revision."},
            headers=headers,
        ).status_code
        == 201
    )

    deleted = client.delete(f"{SUBMISSIONS}/{submission_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert (
        client.get(f"{SUBMISSIONS}/{submission_id}", headers=headers).status_code == 404
    )

    session = SessionLocal()
    try:
        assert session.query(PublicationSubmission).count() == 0
        assert session.query(PublicationRevision).count() == 0
        assert session.query(PublicationStatusEvent).count() == 0
    finally:
        session.close()


def test_publication_validation(client):
    headers, _ = _account(client)
    assert (
        client.post(SUBMISSIONS, json={"title": "   "}, headers=headers).status_code
        == 422
    )
    assert (
        client.post(
            SUBMISSIONS,
            json={"title": "Paper", "venue_type": "blog"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            SUBMISSIONS,
            json={"title": "Paper", "url": "not-a-url"},
            headers=headers,
        ).status_code
        == 422
    )
