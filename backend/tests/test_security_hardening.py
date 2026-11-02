"""Regression tests for API authorization, abuse limits, and import safety."""

import uuid

import pytest
from fastapi import Request

from app.researcher_import import import_researchers as compatibility_import
from app.models import Researcher
from app.services import rate_limit
from app.services.researcher_import import (
    MAX_IMPORT_BYTES,
    ResearcherImportError,
    import_researchers,
)
from conftest import register_test_account


RESEARCHER = {
    "name": "Dr. Security Test",
    "department": "Computer Science",
    "designation": "Professor",
    "experience": 5,
    "research_areas": "Security Engineering",
    "expertise": "API Security",
    "skills": "Python",
    "publications": "Secure APIs",
    "projects": "ResearchTwin",
    "profile_url": "https://example.test/profile",
}


def _mutation_responses(client, headers=None):
    options = {"headers": headers} if headers else {}
    return [
        client.post("/researchers/", json=RESEARCHER, **options),
        client.put("/researchers/987654", json=RESEARCHER, **options),
        client.delete("/researchers/987654", **options),
        client.post("/researchers/import", **options),
    ]


def _register(client, role="student"):
    return register_test_account(
        client,
        role=role,
        email=f"{role}-{uuid.uuid4().hex}@example.test",
    )


def _save_student_profile(client, headers, research_areas="Saved profile area"):
    response = client.put(
        "/students/me/profile",
        json={
            "research_areas": research_areas,
            "expertise": "Saved expertise",
            "skills": "Python",
            "projects": "Saved project",
            "publications": "Saved publication",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


def test_legacy_import_module_uses_validated_importer():
    assert compatibility_import is import_researchers


def test_researcher_mutations_reject_anonymous_requests(client):
    responses = _mutation_responses(client)
    assert [response.status_code for response in responses] == [401] * 4


@pytest.mark.parametrize("role", ["student", "faculty"])
def test_researcher_mutations_reject_non_admin_roles(client, role):
    headers, _ = _register(client, role)
    responses = _mutation_responses(client, headers)
    assert [response.status_code for response in responses] == [403] * 4


def test_out_of_band_admin_can_manage_and_import_researchers(
    client, empty_db, admin_headers
):
    created = client.post("/researchers/", json=RESEARCHER, headers=admin_headers)
    assert created.status_code == 200, created.text
    researcher_id = created.json()["id"]

    updated = client.put(
        f"/researchers/{researcher_id}",
        json={**RESEARCHER, "designation": "Senior Professor"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["designation"] == "Senior Professor"

    deleted = client.delete(f"/researchers/{researcher_id}", headers=admin_headers)
    assert deleted.status_code == 200

    imported = client.post("/researchers/import", headers=admin_headers)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_count"] > 0


def test_public_registration_cannot_create_an_admin(client):
    response = client.post(
        "/auth/register",
        json={
            "email": f"admin-{uuid.uuid4().hex}@example.test",
            "password": "TestPassword123!",
            "full_name": "Unauthorized Administrator",
            "role": "admin",
        },
    )
    assert response.status_code == 422


def test_legacy_recommendations_require_student_and_use_saved_profile(
    client, seeded_db, patch_semantic, monkeypatch
):
    body = {
        "research_areas": "Forged client profile",
        "expertise": "Forged expertise",
        "skills": "Forged skills",
        "projects": "Forged project",
        "publications": "Forged publication",
        "top_k": 2,
    }
    assert client.post("/recommendations/researchers", json=body).status_code == 401

    faculty_headers, _ = _register(client, "faculty")
    assert (
        client.post(
            "/recommendations/researchers", json=body, headers=faculty_headers
        ).status_code
        == 403
    )

    student_headers, _ = _register(client)
    _save_student_profile(client, student_headers, "Actual private saved profile")
    observed = {}

    def fake_recommendations(*, student_profile, db, top_k):
        observed.update(student_profile=student_profile, top_k=top_k)
        return []

    monkeypatch.setattr(
        "app.api.students.generate_recommendations", fake_recommendations
    )
    response = client.post(
        "/recommendations/researchers", json=body, headers=student_headers
    )

    assert response.status_code == 200, response.text
    assert set(response.json()) == {"student_profile", "recommendations"}
    assert response.json()["student_profile"]["research_areas"] == (
        "Actual private saved profile"
    )
    assert observed["student_profile"]["research_areas"] == (
        "Actual private saved profile"
    )
    assert observed["top_k"] == 2
    assert response.headers.get("deprecation") == "true"
    assert "/students/me/recommendations" in response.headers.get("link", "")


def test_legacy_recommendations_require_a_saved_profile(client):
    headers, _ = _register(client)
    response = client.post(
        "/recommendations/researchers",
        json={"research_areas": "client provided", "top_k": 5},
        headers=headers,
    )
    assert response.status_code == 400


def test_registration_rate_limit_returns_retry_after(client, monkeypatch):
    monkeypatch.setattr("app.api.auth.REGISTER_MAX", 1)
    first = client.post(
        "/auth/register",
        json={
            "email": f"first-{uuid.uuid4().hex}@example.test",
            "password": "TestPassword123!",
            "full_name": "First Account",
            "role": "student",
        },
    )
    second = client.post(
        "/auth/register",
        json={
            "email": f"second-{uuid.uuid4().hex}@example.test",
            "password": "TestPassword123!",
            "full_name": "Second Account",
            "role": "student",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert "password" not in second.text.lower()


def test_login_rate_limit_returns_retry_after(client, monkeypatch):
    _, user = _register(client)
    monkeypatch.setattr("app.api.auth.LOGIN_MAX", 1)
    payload = {"email": user["email"], "password": "TestPassword123!"}

    assert client.post("/auth/login", json=payload).status_code == 200
    limited = client.post("/auth/login", json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_recommendation_rate_limit_returns_retry_after(
    client, seeded_db, monkeypatch
):
    headers, _ = _register(client)
    _save_student_profile(client, headers)
    monkeypatch.setattr("app.api.profiles.RECOMMENDATION_MAX", 1)
    monkeypatch.setattr("app.api.profiles.generate_recommendations", lambda **_: [])

    first = client.post(
        "/students/me/recommendations", json={"top_k": 5}, headers=headers
    )
    second = client.post(
        "/students/me/recommendations", json={"top_k": 5}, headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0


def test_request_body_limit_rejects_oversized_payload(raw_client):
    response = raw_client.post(
        "/auth/register",
        content=b"x" * (65_536 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large"}


def test_rate_limit_secret_is_required_for_auth_and_readiness(client, monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_HASH_SECRET", raising=False)
    response = client.post(
        "/auth/register",
        json={
            "email": f"unprotected-{uuid.uuid4().hex}@example.test",
            "password": "TestPassword123!",
            "full_name": "Unprotected Account",
            "role": "student",
        },
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Request protection is not configured"}
    assert client.get("/ready").status_code == 503


def test_rate_limit_secret_minimum_is_32_bytes(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_HASH_SECRET", "a" * 31)
    assert rate_limit.is_rate_limit_configured() is False

    monkeypatch.setenv("RATE_LIMIT_HASH_SECRET", "a" * 32)
    assert rate_limit.is_rate_limit_configured() is True


def test_shared_database_requirement_fails_closed_on_sqlite(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUIRE_SHARED_DATABASE", "true")
    assert client.get("/ready").status_code == 503
    response = client.post(
        "/auth/register",
        json={
            "email": f"sqlite-limiter-{uuid.uuid4().hex}@example.test",
            "password": "TestPassword123!",
            "full_name": "SQLite Limiter Student",
            "role": "student",
        },
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Shared request protection is unavailable"
    }


def _request_scope(header=b"203.0.113.7", peer="198.51.100.8"):
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [
            (b"cf-connecting-ip", header),
            (b"x-forwarded-for", b"192.0.2.99"),
        ],
        "client": (peer, 1234),
        "server": ("testserver", 80),
    }


def test_forwarded_ip_requires_an_explicit_trusted_proxy(monkeypatch):
    scope = _request_scope()
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", raising=False)

    monkeypatch.setenv("RATE_LIMIT_TRUST_CF_CONNECTING_IP", "false")
    assert rate_limit.client_ip_identity(Request(scope)) == "198.51.100.8"

    # Enabling the flag alone must not trust a header from any peer.
    monkeypatch.setenv("RATE_LIMIT_TRUST_CF_CONNECTING_IP", "true")
    assert rate_limit.client_ip_identity(Request(scope)) == "198.51.100.8"

    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert rate_limit.client_ip_identity(Request(scope)) == "198.51.100.8"

    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "198.51.100.0/24")
    assert rate_limit.client_ip_identity(Request(scope)) == "203.0.113.7"

    malformed = _request_scope(header=b"not-an-address")
    assert rate_limit.client_ip_identity(Request(malformed)) == "198.51.100.8"


@pytest.mark.parametrize("trust_enabled", ["false", "true"])
def test_spoofed_forwarding_header_cannot_bypass_ip_rate_limit(
    client, monkeypatch, trust_enabled
):
    monkeypatch.setattr("app.api.auth.REGISTER_MAX", 1)
    monkeypatch.setenv("RATE_LIMIT_TRUST_CF_CONNECTING_IP", trust_enabled)
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", raising=False)

    def register(spoofed_ip):
        return client.post(
            "/auth/register",
            json={
                "email": f"spoof-{uuid.uuid4().hex}@example.test",
                "password": "TestPassword123!",
                "full_name": "Spoof Attempt",
                "role": "student",
            },
            headers={"CF-Connecting-IP": spoofed_ip},
        )

    assert register("203.0.113.10").status_code == 201
    limited = register("203.0.113.11")
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


@pytest.mark.parametrize(
    "filename,content",
    [
        ("unknown.csv", "name,unexpected\nResearcher,x\n"),
        ("bad-row.csv", "name,experience\nValid Researcher,4\nBad Researcher,old\n"),
        ("bad-url.csv", "name,profile_url\nResearcher,javascript:alert(1)\n"),
        ("wrong-type.txt", "name\nResearcher\n"),
    ],
)
def test_invalid_import_is_atomic_and_preserves_existing_rows(
    tmp_path, db, filename, content
):
    marker = f"Existing row {uuid.uuid4().hex}"
    db.add(Researcher(name=marker))
    db.commit()
    before = db.query(Researcher).count()
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ResearcherImportError):
        import_researchers(str(path), db)

    db.expire_all()
    assert db.query(Researcher).count() == before
    assert db.query(Researcher).filter_by(name=marker).count() == 1


def test_oversized_import_is_rejected(tmp_path, db):
    path = tmp_path / "oversized.csv"
    path.write_bytes(b"x" * (MAX_IMPORT_BYTES + 1))
    before = db.query(Researcher).count()
    with pytest.raises(ResearcherImportError, match="size limit"):
        import_researchers(str(path), db)
    assert db.query(Researcher).count() == before


def test_researcher_csv_import_is_idempotent_and_preserves_existing_values(
    tmp_path, db, empty_db
):
    path = tmp_path / "repeat-import.csv"
    path.write_text(
        "name,department,skills\n"
        '"Dr. Idempotent","Computer Science","Python"\n'
        '"dr. idempotent","computer science","Injected Skill"\n'
        '"Dr. Idempotent","Physics","Rust"\n',
        encoding="utf-8",
    )

    assert import_researchers(str(path), db) == 2
    assert import_researchers(str(path), db) == 0
    assert db.query(Researcher).count() == 2

    original = (
        db.query(Researcher)
        .filter_by(name="Dr. Idempotent", department="Computer Science")
        .one()
    )
    assert original.skills == "Python"


def test_profile_bodies_cannot_override_ownership_or_roles(client):
    student_headers, _ = _register(client)
    student_response = client.put(
        "/students/me/profile",
        json={"research_areas": "AI", "user_id": 999, "role": "admin"},
        headers=student_headers,
    )
    assert student_response.status_code == 422

    faculty_headers, _ = _register(client, "faculty")
    faculty_response = client.put(
        "/faculty/me/profile",
        json={"department": "CS", "user_id": 999, "role": "admin"},
        headers=faculty_headers,
    )
    assert faculty_response.status_code == 422


def test_faculty_profiles_are_isolated_between_accounts(client):
    first_headers, _ = _register(client, "faculty")
    second_headers, _ = _register(client, "faculty")

    saved = client.put(
        "/faculty/me/profile",
        json={"department": "First Faculty Department"},
        headers=first_headers,
    )
    assert saved.status_code == 200

    first = client.get("/faculty/me/profile", headers=first_headers)
    second = client.get("/faculty/me/profile", headers=second_headers)
    assert first.json()["department"] == "First Faculty Department"
    assert second.json()["department"] == ""
    assert second.json()["profile_completion"] == 0


def test_read_and_search_remain_public(client, seeded_db):
    assert client.get("/researchers/").status_code == 200
    researcher_id = client.get("/researchers/").json()[0]["id"]
    assert client.get(f"/researchers/{researcher_id}").status_code == 200


def test_every_api_response_carries_security_headers(client):
    for response in (
        client.get("/"),
        client.get("/admin/users"),
        client.get("/does-not-exist"),
    ):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["permissions-policy"] == (
            "camera=(), microphone=(), geolocation=()"
        )
        assert response.headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )


def test_faculty_profile_save_is_not_a_researcher_mutation_bypass(
    client, seeded_db, admin_headers, db
):
    """The one faculty-writable route must not reach the admin-only directory rows."""
    from app.models import FacultyResearcherLink

    headers, faculty = _register(client, "faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]
    assigned = client.put(
        f"/admin/faculty/{faculty['id']}/researcher-link",
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    )
    assert assigned.status_code == 200, assigned.text
    directory_before = client.get("/researchers/").json()
    record_before = client.get(f"/researchers/{researcher_id}").json()

    saved = client.put(
        "/faculty/me/profile",
        json={
            "department": "Hijacked Department",
            "designation": "Hijacked Designation",
            "research_areas": "Hijacked Areas",
            "expertise": "Hijacked Expertise",
            "skills": "Hijacked Skills",
            "publications": "Hijacked Publications",
            "projects": "Hijacked Projects",
            "profile_url": "https://example.test/hijacked",
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text

    assert client.get(f"/researchers/{researcher_id}").json() == record_before
    assert client.get("/researchers/").json() == directory_before
    db.expire_all()
    link = db.query(FacultyResearcherLink).filter_by(faculty_user_id=faculty["id"]).one()
    assert link.researcher_id == researcher_id
    assert client.get("/faculty/me/profile", headers=headers).json()["department"] == (
        "Hijacked Department"
    )

