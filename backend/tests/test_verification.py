"""Verified researcher profile workflow: submission, review, expiry, privacy."""

import json
import time

import pytest

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    CollaborationRequest,
    FacultyResearcherLink,
    ResearcherVerification,
)
from conftest import register_test_account

PUBLIC = "/researchers/{researcher_id}/verification"
SUMMARY = "/researchers/verification-summary"
SUBMIT = "/faculty/me/researcher-link/verification"
OWNER = "/faculty/me/researcher-link/verification"
ADMIN_LIST = "/admin/verifications"
ADMIN_DECISION = "/admin/verifications/{verification_id}"
ADMIN_HISTORY = "/admin/researchers/{researcher_id}/verifications"
ADMIN_LINK = "/admin/faculty/{faculty_user_id}/researcher-link"

EVIDENCE = "https://example.edu/directory/ada-lovelace"


@pytest.fixture(autouse=True)
def clean_verification_tables():
    def cleanup():
        session = SessionLocal()
        try:
            session.query(ResearcherVerification).delete()
            session.query(CollaborationRequest).delete()
            session.query(FacultyResearcherLink).delete()
            session.commit()
        finally:
            session.close()

    cleanup()
    yield cleanup()


def _first_researcher_id(client) -> int:
    return client.get("/researchers/").json()[0]["id"]


def _linked_faculty(client, admin_headers):
    headers, user = register_test_account(client, role="faculty")
    researcher_id = _first_researcher_id(client)
    response = client.put(
        ADMIN_LINK.format(faculty_user_id=user["id"]),
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    return headers, user, researcher_id


def _submit(client, headers, evidence=EVIDENCE, note="Directory record owner"):
    return client.post(
        SUBMIT,
        json={"evidence_reference": evidence, "note": note},
        headers=headers,
    )


def _approve(client, admin_headers, verification_id, **extra):
    payload = {"decision": "verify", "review_note": "Evidence checked", **extra}
    return client.put(
        ADMIN_DECISION.format(verification_id=verification_id),
        json=payload,
        headers=admin_headers,
    )


def test_public_status_defaults_to_unverified(client, seeded_db):
    researcher_id = _first_researcher_id(client)

    response = client.get(PUBLIC.format(researcher_id=researcher_id))

    assert response.status_code == 200
    assert response.json() == {
        "researcher_id": researcher_id,
        "status": "unverified",
        "verified_at": None,
        "expires_at": None,
    }


def test_unknown_researcher_public_status_is_404(client, seeded_db):
    assert client.get(PUBLIC.format(researcher_id=987654)).status_code == 404


def test_linked_faculty_can_submit_and_evidence_stays_private(
    client, seeded_db, admin_headers
):
    headers, user, researcher_id = _linked_faculty(client, admin_headers)

    submitted = _submit(client, headers)
    assert submitted.status_code == 201, submitted.text
    body = submitted.json()
    assert body["status"] == "pending"
    assert body["researcher_id"] == researcher_id
    assert body["evidence_reference"] == EVIDENCE
    assert body["note"] == "Directory record owner"
    assert body["submitted_at"]
    assert body["reviewed_at"] is None

    public = client.get(PUBLIC.format(researcher_id=researcher_id))
    assert public.status_code == 200
    assert public.json() == {
        "researcher_id": researcher_id,
        "status": "pending",
        "verified_at": None,
        "expires_at": None,
    }
    assert "evidence" not in json.dumps(public.json()).lower()

    owner = client.get(OWNER, headers=headers)
    assert owner.status_code == 200
    assert owner.json()["evidence_reference"] == EVIDENCE

    queue = client.get(ADMIN_LIST, params={"status": "pending"}, headers=admin_headers)
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["verifications"][0]["evidence_reference"] == EVIDENCE
    assert queue.json()["verifications"][0]["submitted_by_user_id"] == user["id"]


def test_unlinked_faculty_and_students_cannot_submit_or_review(
    client, seeded_db, admin_headers
):
    faculty_headers, _ = register_test_account(client, role="faculty")
    student_headers, _ = register_test_account(client, role="student")

    assert _submit(client, faculty_headers).status_code == 400
    assert _submit(client, student_headers).status_code == 403
    assert client.get(ADMIN_LIST, headers=faculty_headers).status_code == 403
    assert client.get(ADMIN_LIST, headers=student_headers).status_code == 403


def test_duplicate_pending_submission_is_rejected(client, seeded_db, admin_headers):
    headers, _, _ = _linked_faculty(client, admin_headers)

    assert _submit(client, headers).status_code == 201
    duplicate = _submit(client, headers, evidence="https://example.edu/other")

    assert duplicate.status_code == 409


def test_admin_approval_publishes_verification_and_records_audit(
    client, seeded_db, admin_headers, db
):
    headers, _, researcher_id = _linked_faculty(client, admin_headers)
    verification_id = _submit(client, headers).json()["id"]

    approved = _approve(
        client, admin_headers, verification_id, expires_in_days=365
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    assert approved_body["status"] == "verified"
    assert approved_body["review_note"] == "Evidence checked"
    assert approved_body["reviewed_at"]
    assert approved_body["expires_at"] > int(time.time())

    public = client.get(PUBLIC.format(researcher_id=researcher_id)).json()
    assert public["status"] == "verified"
    assert public["verified_at"] == approved_body["reviewed_at"]
    assert public["expires_at"] == approved_body["expires_at"]
    assert "evidence" not in json.dumps(public).lower()

    second_decision = _approve(client, admin_headers, verification_id)
    assert second_decision.status_code == 409

    actions = {
        event.action
        for event in db.query(AuditEvent)
        .filter(AuditEvent.target_type == "researcher", AuditEvent.target_id == researcher_id)
        .all()
    }
    assert "researcher_verification.submit" in actions
    assert "researcher_verification.approve" in actions


def test_rejection_allows_a_new_request_and_keeps_history(
    client, seeded_db, admin_headers
):
    headers, _, researcher_id = _linked_faculty(client, admin_headers)
    verification_id = _submit(client, headers).json()["id"]

    rejected = client.put(
        ADMIN_DECISION.format(verification_id=verification_id),
        json={"decision": "reject", "review_note": "Evidence could not be confirmed"},
        headers=admin_headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    public = client.get(PUBLIC.format(researcher_id=researcher_id)).json()
    assert public["status"] == "rejected"
    assert public["verified_at"] is None

    resubmitted = _submit(client, headers, evidence="https://example.edu/new-evidence")
    assert resubmitted.status_code == 201
    assert resubmitted.json()["status"] == "pending"


def test_expired_verification_is_reported_and_can_be_resubmitted(
    client, seeded_db, admin_headers, db
):
    headers, _, researcher_id = _linked_faculty(client, admin_headers)
    verification_id = _submit(client, headers).json()["id"]
    approved = _approve(client, admin_headers, verification_id, expires_in_days=1)
    assert approved.status_code == 200, approved.text

    record = db.query(ResearcherVerification).filter_by(id=verification_id).one()
    record.expires_at = int(time.time()) - 60
    db.commit()
    db.expire_all()

    public = client.get(PUBLIC.format(researcher_id=researcher_id)).json()
    assert public["status"] == "expired"
    assert public["verified_at"] is not None

    owner = client.get(OWNER, headers=headers).json()
    assert owner["status"] == "expired"

    resubmitted = _submit(client, headers, evidence="https://example.edu/renewal")
    assert resubmitted.status_code == 201
    assert resubmitted.json()["status"] == "pending"

    history = client.get(
        ADMIN_HISTORY.format(researcher_id=researcher_id), headers=admin_headers
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert [row["status"] for row in history.json()["verifications"]] == [
        "pending",
        "expired",
    ]


def test_summary_lists_every_researcher_and_filters_by_status(
    client, seeded_db, admin_headers
):
    headers, _, researcher_id = _linked_faculty(client, admin_headers)
    verification_id = _submit(client, headers).json()["id"]
    assert _approve(client, admin_headers, verification_id).status_code == 200

    summary = client.get(SUMMARY)
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] == 3
    assert len(body["researchers"]) == 3
    by_id = {row["researcher_id"]: row["status"] for row in body["researchers"]}
    assert by_id[researcher_id] == "verified"
    assert sum(1 for status in by_id.values() if status == "unverified") == 2
    assert "evidence" not in json.dumps(body).lower()

    verified_only = client.get(SUMMARY, params={"status": "verified"})
    assert verified_only.status_code == 200
    assert verified_only.json()["total"] == 1
    assert verified_only.json()["researchers"][0]["researcher_id"] == researcher_id


def test_admin_queue_supports_pagination(client, seeded_db, admin_headers):
    first_headers, _, _ = _linked_faculty(client, admin_headers)

    second_headers, second_user = register_test_account(client, role="faculty")
    second_researcher = client.get("/researchers/").json()[1]["id"]
    linked = client.put(
        ADMIN_LINK.format(faculty_user_id=second_user["id"]),
        json={"researcher_id": second_researcher},
        headers=admin_headers,
    )
    assert linked.status_code == 200, linked.text

    assert _submit(client, first_headers).status_code == 201
    assert _submit(client, second_headers).status_code == 201

    first_page = client.get(
        ADMIN_LIST, params={"status": "pending", "limit": 1, "offset": 0},
        headers=admin_headers,
    )
    second_page = client.get(
        ADMIN_LIST, params={"status": "pending", "limit": 1, "offset": 1},
        headers=admin_headers,
    )

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert len(first_page.json()["verifications"]) == 1
    assert len(second_page.json()["verifications"]) == 1
    assert (
        first_page.json()["verifications"][0]["id"]
        != second_page.json()["verifications"][0]["id"]
    )


def test_validation_and_missing_resources(client, seeded_db, admin_headers):
    headers, _, researcher_id = _linked_faculty(client, admin_headers)

    assert _submit(client, headers, evidence="").status_code == 422
    assert _submit(client, headers, evidence="x").status_code == 422
    verification_id = _submit(client, headers).json()["id"]

    assert (
        client.put(
            ADMIN_DECISION.format(verification_id=verification_id),
            json={"decision": "maybe"},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert (
        client.put(
            ADMIN_DECISION.format(verification_id=999999),
            json={"decision": "verify"},
            headers=admin_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            ADMIN_HISTORY.format(researcher_id=987654), headers=admin_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            SUMMARY, params={"limit": 0}
        ).status_code
        == 422
    )
