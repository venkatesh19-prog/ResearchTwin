"""Administrator account lifecycle, session revocation, and audit history."""

import json
import uuid

import pytest

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    CollaborationRequest,
    FacultyResearcherLink,
    User,
)
from conftest import register_test_account

ADMIN = "/admin"
USERS = ADMIN + "/users"
AUDIT = ADMIN + "/audit-events"
PASSWORD = "TestPassword123!"
NEW_PASSWORD = "InstitutionReset456!"
AUDIT_TABLES = (AuditEvent, CollaborationRequest, FacultyResearcherLink)


@pytest.fixture(autouse=True)
def clean_audit_tables():
    def cleanup():
        session = SessionLocal()
        try:
            for model in AUDIT_TABLES:
                session.query(model).delete()
            session.commit()
        finally:
            session.close()

    cleanup()
    yield
    cleanup()


def _admin_id(db) -> int:
    # The fixture provisions a fresh admin immediately before each test.
    return db.query(User).filter(User.role == "admin").order_by(User.id.desc()).first().id


def _login(client, email, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _events(client, admin_headers, **params):
    response = client.get(AUDIT, params=params, headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_endpoints_reject_anonymous_and_non_admin_callers(client):
    _, student = register_test_account(client, role="student")
    _, faculty = register_test_account(client, role="faculty")
    user_id = student["id"]
    calls = [
        ("get", USERS, None),
        ("put", f"{USERS}/{user_id}/active", {"active": False}),
        ("put", f"{USERS}/{user_id}/role", {"role": "faculty"}),
        ("post", f"{USERS}/{user_id}/sessions/revoke", None),
        ("post", f"{USERS}/{user_id}/password-reset", {"password": NEW_PASSWORD}),
        ("get", f"{USERS}/{user_id}/data-export", None),
        ("get", AUDIT, None),
    ]

    for method, url, body in calls:
        anonymous = getattr(client, method)(url, json=body) if body else getattr(client, method)(url)
        assert anonymous.status_code == 401, (url, anonymous.text)

    student_headers, _ = register_test_account(client, role="student")
    faculty_headers, _ = register_test_account(client, role="faculty")
    for headers in (student_headers, faculty_headers):
        for method, url, body in calls:
            denied = getattr(client, method)(url, json=body, headers=headers) if body else getattr(client, method)(url, headers=headers)
            assert denied.status_code == 403, (url, denied.text)


def test_admin_deactivates_and_reactivates_an_account(client, admin_headers):
    student_headers, student = register_test_account(client, role="student")
    other_headers, other = register_test_account(client, role="student")

    deactivated = client.put(
        f"{USERS}/{student['id']}/active",
        json={"active": False},
        headers=admin_headers,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False

    assert client.get("/auth/me", headers=student_headers).status_code == 401
    assert _login(client, student["email"]).status_code == 403
    assert _login(client, other["email"]).status_code == 200
    assert other_headers

    events = _events(client, admin_headers, action="account.deactivate", target_id=student["id"])
    assert len(events) == 1
    assert events[0]["target_type"] == "user"
    assert events[0]["actor_user_id"] is not None
    assert json.loads(events[0]["detail"])["revoked_sessions"] >= 1

    reactivated = client.put(
        f"{USERS}/{student['id']}/active",
        json={"active": True},
        headers=admin_headers,
    )
    assert reactivated.status_code == 200
    assert _login(client, student["email"]).status_code == 200
    assert _events(client, admin_headers, action="account.reactivate", target_id=student["id"])


def test_admin_cannot_change_own_status_or_role(client, admin_headers, db):
    admin_id = _admin_id(db)

    status = client.put(
        f"{USERS}/{admin_id}/active",
        json={"active": False},
        headers=admin_headers,
    )
    role = client.put(
        f"{USERS}/{admin_id}/role",
        json={"role": "student"},
        headers=admin_headers,
    )

    assert status.status_code == 403, status.text
    assert role.status_code == 403, role.text
    assert db.get(User, admin_id).role == "admin"
    assert db.get(User, admin_id).is_active is True


def test_role_change_revokes_sessions_and_is_audited(client, admin_headers, db):
    student_headers, student = register_test_account(client, role="student")

    changed = client.put(
        f"{USERS}/{student['id']}/role",
        json={"role": "faculty"},
        headers=admin_headers,
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "faculty"
    assert client.get("/auth/me", headers=student_headers).status_code == 401

    logged_in = _login(client, student["email"])
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "faculty"

    events = _events(client, admin_headers, action="account.role_change", target_id=student["id"])
    assert len(events) == 1
    detail = json.loads(events[0]["detail"])
    assert detail["from"] == "student"
    assert detail["to"] == "faculty"
    assert db.get(User, student["id"]).role == "faculty"


def test_password_reset_revokes_sessions_and_never_stores_the_password(client, admin_headers):
    student_headers, student = register_test_account(client, role="student")

    reset = client.post(
        f"{USERS}/{student['id']}/password-reset",
        json={"password": NEW_PASSWORD},
        headers=admin_headers,
    )

    assert reset.status_code == 200, reset.text
    assert client.get("/auth/me", headers=student_headers).status_code == 401
    assert _login(client, student["email"], PASSWORD).status_code == 401
    assert _login(client, student["email"], NEW_PASSWORD).status_code == 200

    events = _events(client, admin_headers, action="account.password_reset", target_id=student["id"])
    assert len(events) == 1
    assert NEW_PASSWORD not in events[0]["detail"]


def test_revoke_all_sessions_invalidates_every_token(client, admin_headers):
    registered_headers, student = register_test_account(client, role="student")
    logged_in = _login(client, student["email"])
    second_headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
    assert client.get("/auth/me", headers=registered_headers).status_code == 200
    assert client.get("/auth/me", headers=second_headers).status_code == 200

    revoked = client.post(
        f"{USERS}/{student['id']}/sessions/revoke",
        headers=admin_headers,
    )

    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] >= 2
    assert client.get("/auth/me", headers=registered_headers).status_code == 401
    assert client.get("/auth/me", headers=second_headers).status_code == 401


def test_account_listing_supports_role_and_active_filters(client, admin_headers):
    _, student = register_test_account(client, role="student")
    _, faculty = register_test_account(client, role="faculty")

    students = client.get(USERS, params={"role": "student", "active": "true"}, headers=admin_headers)
    assert students.status_code == 200, students.text
    rows = students.json()
    assert {row["role"] for row in rows} == {"student"}
    assert student["id"] in {row["id"] for row in rows}
    assert faculty["id"] not in {row["id"] for row in rows}
    assert all("password" not in row for row in rows)

    assert client.get(USERS, params={"role": "superuser"}, headers=admin_headers).status_code == 422


def test_unlink_researcher_is_audited_and_disables_faculty_inbox(
    client, seeded_db, admin_headers, db
):
    faculty_headers, faculty = register_test_account(client, role="faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]
    linked = client.put(
        f"{ADMIN}/faculty/{faculty['id']}/researcher-link",
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    )
    assert linked.status_code == 200, linked.text

    removed = client.delete(
        f"{ADMIN}/faculty/{faculty['id']}/researcher-link",
        headers=admin_headers,
    )

    assert removed.status_code == 200, removed.text
    assert removed.json() == {"linked": False}
    assert db.query(FacultyResearcherLink).count() == 0
    assert client.get("/faculty/me/researcher-link", headers=faculty_headers).json()["linked"] is False
    assert client.get("/faculty/me/collaboration-requests", headers=faculty_headers).status_code == 400

    events = _events(
        client, admin_headers, action="faculty_link.remove", target_id=faculty["id"]
    )
    assert len(events) == 1
    assert json.loads(events[0]["detail"])["researcher_id"] == researcher_id
    assert client.delete(
        f"{ADMIN}/faculty/{faculty['id']}/researcher-link",
        headers=admin_headers,
    ).status_code == 404


def test_collaboration_decision_is_audited(client, seeded_db, admin_headers):
    student_headers, _ = register_test_account(client, role="student")
    faculty_headers, faculty = register_test_account(client, role="faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]
    assert client.put(
        f"{ADMIN}/faculty/{faculty['id']}/researcher-link",
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    ).status_code == 200
    created = client.post(
        "/students/me/collaboration-requests",
        json={"researcher_id": researcher_id, "message": "Interested in your ML work."},
        headers=student_headers,
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    decided = client.put(
        f"/faculty/me/collaboration-requests/{request_id}/decision",
        json={"decision": "accept", "response": "Happy to supervise."},
        headers=faculty_headers,
    )
    assert decided.status_code == 200, decided.text

    events = _events(
        client,
        admin_headers,
        action="collaboration.decision",
        target_id=request_id,
    )
    assert len(events) == 1
    assert events[0]["actor_user_id"] == faculty["id"]
    assert json.loads(events[0]["detail"])["decision"] == "accept"


def test_account_data_export_contains_personal_data_but_no_secrets(
    client, seeded_db, admin_headers
):
    student_headers, student = register_test_account(client, role="student")
    saved = client.put(
        "/students/me/profile",
        json={
            "research_areas": "Machine Learning",
            "expertise": "Computer vision",
            "skills": "Python",
            "projects": "",
            "publications": "",
            "courses": "",
            "academic_details": "Final year",
        },
        headers=student_headers,
    )
    assert saved.status_code == 200, saved.text
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = client.post(
        "/students/me/collaboration-requests",
        json={"researcher_id": researcher_id, "message": "Please consider my request."},
        headers=student_headers,
    )
    assert created.status_code == 201, created.text

    response = client.get(f"{USERS}/{student['id']}/data-export", headers=admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account"]["email"] == student["email"]
    assert body["student_profile"]["research_areas"] == "Machine Learning"
    assert body["collaboration_requests"][0]["researcher_id"] == researcher_id
    assert body["sessions"]["active"] >= 1
    assert "password_hash" not in response.text
    assert "token_hash" not in response.text
    assert PASSWORD not in response.text

    events = _events(
        client, admin_headers, action="account.data_export", target_id=student["id"]
    )
    assert len(events) == 1
    assert client.get(f"{USERS}/999999/data-export", headers=admin_headers).status_code == 404


def test_account_export_minimizes_other_students_private_messages(
    client, seeded_db, admin_headers
):
    faculty_headers, faculty = register_test_account(client, role="faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]
    assert client.put(
        f"{ADMIN}/faculty/{faculty['id']}/researcher-link",
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    ).status_code == 200

    owner_headers, owner = register_test_account(client, role="student")
    other_headers, other = register_test_account(client, role="student")
    owner_message = f"Owner private note {uuid.uuid4().hex}"
    other_message = f"Third-party private note {uuid.uuid4().hex}"
    owner_request = client.post(
        "/students/me/collaboration-requests",
        json={"researcher_id": researcher_id, "message": owner_message},
        headers=owner_headers,
    )
    other_request = client.post(
        "/students/me/collaboration-requests",
        json={"researcher_id": researcher_id, "message": other_message},
        headers=other_headers,
    )
    assert owner_request.status_code == 201, owner_request.text
    assert other_request.status_code == 201, other_request.text

    response = client.get(f"{USERS}/{faculty['id']}/data-export", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["collaboration_requests"] == []
    inbox_rows = {row["id"]: row for row in body["faculty_inbox"]}
    assert set(inbox_rows) == {owner_request.json()["id"], other_request.json()["id"]}
    for row in inbox_rows.values():
        assert "message" not in row
        assert "student_user_id" not in row
        assert row["researcher_id"] == researcher_id
        assert row["status"] == "pending"

    assert owner_message not in response.text
    assert other_message not in response.text
    assert other["email"] not in response.text

    events = _events(
        client, admin_headers, action="account.data_export", target_id=faculty["id"]
    )
    assert len(events) == 1

    owner_export = client.get(
        f"{USERS}/{owner['id']}/data-export", headers=admin_headers
    )
    assert owner_export.status_code == 200, owner_export.text
    assert [row["message"] for row in owner_export.json()["collaboration_requests"]] == [
        owner_message
    ]
    assert other_message not in owner_export.text


def test_invalid_account_operations_are_rejected(client, admin_headers):
    assert client.put(
        f"{USERS}/987654/active",
        json={"active": False},
        headers=admin_headers,
    ).status_code == 404
    assert client.put(
        f"{USERS}/987654/role",
        json={"role": "faculty"},
        headers=admin_headers,
    ).status_code == 404
    assert client.post(
        f"{USERS}/987654/password-reset",
        json={"password": NEW_PASSWORD},
        headers=admin_headers,
    ).status_code == 404
    assert client.put(
        f"{USERS}/987654/role",
        json={"role": "superuser"},
        headers=admin_headers,
    ).status_code == 422
    _, student = register_test_account(client, role="student")
    assert client.post(
        f"{USERS}/{student['id']}/password-reset",
        json={"password": "short"},
        headers=admin_headers,
    ).status_code == 422
    assert client.put(
        f"{USERS}/{student['id']}/active",
        json={"active": False, "extra": 1},
        headers=admin_headers,
    ).status_code == 422


def test_audit_listing_is_newest_first_and_limited(client, admin_headers):
    _, student = register_test_account(client, role="student")
    client.put(
        f"{USERS}/{student['id']}/active",
        json={"active": False},
        headers=admin_headers,
    )
    client.put(
        f"{USERS}/{student['id']}/active",
        json={"active": True},
        headers=admin_headers,
    )
    student_headers, _ = register_test_account(client, role="student")
    assert client.get(AUDIT, headers=student_headers).status_code == 403

    events = _events(client, admin_headers, target_id=student["id"])
    ids = [event["id"] for event in events]
    assert ids == sorted(ids, reverse=True)
    assert client.get(
        AUDIT, params={"limit": 201}, headers=admin_headers
    ).status_code == 422
