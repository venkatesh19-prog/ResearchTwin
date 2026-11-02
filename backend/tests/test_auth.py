"""Authentication: registration, login, session lifecycle, role identity."""

import json
import time
import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    AuthSession,
    FacultyProfile,
    StudentProfile,
    User,
)
from app.services.auth import hash_token, verify_password

PASSWORD = "CorrectHorseBattery9"
AUTH_HEADER = "Authorization"


def unique_email(prefix: str = "student") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.edu"


@pytest.fixture(autouse=True)
def clean_account_tables():
    def cleanup():
        db = SessionLocal()
        try:
            db.query(AuditEvent).delete()
            db.query(AuthSession).delete()
            db.query(StudentProfile).delete()
            db.query(FacultyProfile).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    cleanup()
    yield cleanup()


def audit_rows(action: str) -> list[dict]:
    db = SessionLocal()
    try:
        return [
            {
                "id": event.id,
                "actor_user_id": event.actor_user_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "detail": json.loads(event.detail or "{}"),
            }
            for event in db.query(AuditEvent)
            .filter(AuditEvent.action == action)
            .order_by(AuditEvent.id)
        ]
    finally:
        db.close()


def register(client, role: str = "student", email: str | None = None):
    email = email or unique_email(role)
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": f"Test {role.title()}",
            "role": role,
        },
    )
    return response, email


def auth_header(token: str) -> dict:
    return {AUTH_HEADER: f"Bearer {token}"}


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------

def test_register_student_returns_token_and_public_user(client):
    response, email = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_at"] > int(time.time())
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "student"
    assert "password" not in response.text.lower()
    assert "password_hash" not in response.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        assert user.password_hash != PASSWORD
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert verify_password(PASSWORD, user.password_hash)
    finally:
        db.close()


def test_register_normalizes_email_and_rejects_case_insensitive_duplicate(
    client,
):
    first, email = register(client, email="Mixed.Case@Example.EDU")
    assert first.status_code == 201
    assert first.json()["user"]["email"] == "mixed.case@example.edu"

    duplicate, _ = register(client, email=email.lower())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Email already registered"


@pytest.mark.parametrize("password", ["short", "        "])
def test_register_rejects_weak_or_blank_password(client, password):
    response = client.post(
        "/auth/register",
        json={
            "email": unique_email(),
            "password": password,
            "full_name": "Weak Password",
            "role": "student",
        },
    )
    assert response.status_code == 422


def test_register_rejects_unknown_role(client):
    response = client.post(
        "/auth/register",
        json={
            "email": unique_email(),
            "password": PASSWORD,
            "full_name": "Unknown Role",
            "role": "admin",
        },
    )
    assert response.status_code == 422


def test_register_faculty_role_is_supported(client):
    response, email = register(client, role="faculty")

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "faculty"
    assert response.json()["user"]["email"] == email


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------

def test_login_returns_working_token(client):
    _, email = register(client)
    response = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )

    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_login_rejects_wrong_password_and_unknown_email_identically(client):
    _, email = register(client)

    wrong_password = client.post(
        "/auth/login", json={"email": email, "password": "WrongPassword1"}
    )
    unknown_email = client.post(
        "/auth/login",
        json={"email": unique_email("nobody"), "password": PASSWORD},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_unknown_email_login_still_performs_password_verification(client, monkeypatch):
    import app.api.auth as auth_module

    verified = []

    def spy(password, encoded):
        verified.append(True)
        return verify_password(password, encoded)

    monkeypatch.setattr(auth_module, "verify_password", spy)

    response = client.post(
        "/auth/login",
        json={"email": unique_email("nobody"), "password": PASSWORD},
    )

    assert response.status_code == 401
    assert verified, "unknown-email logins must not skip password hashing"


def test_inactive_user_cannot_login(client):
    _, email = register(client)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Account is inactive"


# ------------------------------------------------------------------
# Session lifecycle
# ------------------------------------------------------------------

def test_me_requires_a_valid_bearer_token(client):
    assert client.get("/auth/me").status_code == 401
    assert (
        client.get("/auth/me", headers=auth_header("not-a-real-token")).status_code
        == 401
    )


def test_tokens_are_stored_hashed_not_in_plaintext(client):
    response, _ = register(client)
    token = response.json()["access_token"]

    db = SessionLocal()
    try:
        session = db.query(AuthSession).one()
        assert session.token_hash == hash_token(token)
        assert session.token_hash != token
        assert len(session.token_hash) == 64
    finally:
        db.close()


def test_logout_revokes_the_current_session(client):
    response, _ = register(client)
    token = response.json()["access_token"]
    headers = auth_header(token)

    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401

    db = SessionLocal()
    try:
        session = db.query(AuthSession).one()
        assert session.revoked_at is not None
    finally:
        db.close()


def test_expired_session_is_rejected(client):
    response, _ = register(client)
    token = response.json()["access_token"]

    db = SessionLocal()
    try:
        session = db.query(AuthSession).one()
        session.expires_at = int(time.time()) - 1
        db.commit()
    finally:
        db.close()

    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


# ------------------------------------------------------------------
# Authentication audit trail
# ------------------------------------------------------------------

def test_successful_login_is_audited_with_the_internal_user_id(client):
    registered, email = register(client)
    user_id = registered.json()["user"]["id"]

    response = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200

    events = audit_rows("auth.login_succeeded")
    assert len(events) == 1
    assert events[0]["actor_user_id"] == user_id
    assert events[0]["target_type"] == "user"
    assert events[0]["target_id"] == user_id
    assert events[0]["detail"] == {}
    assert email not in json.dumps(events[0]["detail"])


def test_repeated_known_account_failures_are_audited_once_per_window(client):
    registered, email = register(client)
    user_id = registered.json()["user"]["id"]

    for _ in range(3):
        response = client.post(
            "/auth/login", json={"email": email, "password": "WrongPassword1"}
        )
        assert response.status_code == 401

    events = audit_rows("auth.login_failed")
    assert len(events) == 1
    assert events[0]["actor_user_id"] is None
    assert events[0]["target_type"] == "user"
    assert events[0]["target_id"] == user_id
    assert events[0]["detail"] == {"reason": "invalid_password"}
    assert email not in json.dumps(events[0]["detail"])


def test_unknown_identity_failure_is_audited_without_storing_the_email(client):
    email = unique_email("nobody")

    for _ in range(2):
        response = client.post(
            "/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 401

    events = audit_rows("auth.login_failed")
    assert len(events) == 1
    assert events[0]["actor_user_id"] is None
    assert events[0]["target_type"] == "login_identity"
    assert events[0]["target_id"] is None
    assert events[0]["detail"] == {"reason": "unknown_account"}
    assert email not in json.dumps(events[0]["detail"])


def test_inactive_account_failure_is_audited(client):
    registered, email = register(client)
    user_id = registered.json()["user"]["id"]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 403

    events = audit_rows("auth.login_failed")
    assert len(events) == 1
    assert events[0]["target_id"] == user_id
    assert events[0]["detail"] == {"reason": "inactive_account"}


def test_logout_is_audited_against_the_session(client):
    registered, _ = register(client)
    token = registered.json()["access_token"]
    user_id = registered.json()["user"]["id"]

    db = SessionLocal()
    try:
        session_id = db.query(AuthSession).one().id
    finally:
        db.close()

    response = client.post("/auth/logout", headers=auth_header(token))
    assert response.status_code == 200

    events = audit_rows("auth.logout")
    assert len(events) == 1
    assert events[0]["actor_user_id"] == user_id
    assert events[0]["target_type"] == "auth_session"
    assert events[0]["target_id"] == session_id
    assert events[0]["detail"] == {}


def test_auth_audit_rows_never_store_credentials_or_tokens(client):
    registered, email = register(client)
    token = registered.json()["access_token"]

    client.post(
        "/auth/login", json={"email": email, "password": "WrongPassword1"}
    )
    client.post("/auth/login", json={"email": email, "password": PASSWORD})
    client.post("/auth/logout", headers=auth_header(token))

    db = SessionLocal()
    try:
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.action.like("auth.%"))
            .all()
        )
        assert rows

        for row in rows:
            payload = " ".join(
                part
                for part in (row.action, row.target_type, row.detail or "")
                if part
            )
            assert PASSWORD not in payload
            assert "WrongPassword1" not in payload
            assert token not in payload
            assert "Bearer" not in payload
            assert "pbkdf2" not in payload
            assert email not in payload
    finally:
        db.close()


def test_login_success_audit_failure_fails_closed(client, monkeypatch):
    _, email = register(client)

    db = SessionLocal()
    try:
        sessions_before = db.query(AuthSession).count()
    finally:
        db.close()

    def broken(*args, **kwargs):
        raise SQLAlchemyError("audit store unavailable")

    monkeypatch.setattr("app.api.auth.record_event", broken)

    response = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )

    assert response.status_code == 503
    assert audit_rows("auth.login_succeeded") == []

    db = SessionLocal()
    try:
        assert db.query(AuthSession).count() == sessions_before
    finally:
        db.close()


def test_failed_login_audit_failure_still_returns_the_auth_error(
    client, monkeypatch
):
    _, email = register(client)

    def broken(*args, **kwargs):
        raise SQLAlchemyError("audit store unavailable")

    monkeypatch.setattr("app.api.auth.record_event", broken)

    response = client.post(
        "/auth/login", json={"email": email, "password": "WrongPassword1"}
    )

    assert response.status_code == 401
    assert audit_rows("auth.login_failed") == []


def test_logout_audit_failure_does_not_report_success(client, monkeypatch):
    registered, _ = register(client)
    token = registered.json()["access_token"]

    def broken(*args, **kwargs):
        raise SQLAlchemyError("audit store unavailable")

    monkeypatch.setattr("app.api.auth.record_event", broken)

    response = client.post("/auth/logout", headers=auth_header(token))
    assert response.status_code == 503

    assert client.get("/auth/me", headers=auth_header(token)).status_code == 200
