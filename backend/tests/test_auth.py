"""Authentication: registration, login, session lifecycle, role identity."""

import time
import uuid

import pytest

from app.database import SessionLocal
from app.models import (
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
            db.query(AuthSession).delete()
            db.query(StudentProfile).delete()
            db.query(FacultyProfile).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    cleanup()
    yield cleanup()


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
