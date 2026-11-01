"""Persistent student/faculty profiles and ownership enforcement."""

import uuid

import pytest

from app.database import SessionLocal
from app.models import (
    AuthSession,
    FacultyProfile,
    StudentProfile,
    User,
)

PASSWORD = "CorrectHorseBattery9"

STUDENT_PROFILE = {
    "research_areas": "Artificial Intelligence, Machine Learning",
    "expertise": "Deep Learning, NLP",
    "skills": "Python, PyTorch",
    "projects": "Semantic search engine",
    "publications": "Transformer models",
    "courses": "Machine Learning, Algorithms",
    "academic_details": "B.Tech CSE, 2026",
}


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


def register(client, role: str = "student"):
    email = f"{role}-{uuid.uuid4().hex}@example.edu"
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": f"Test {role.title()}",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }, email


def test_student_without_profile_gets_empty_completion(client):
    headers, _ = register(client)

    response = client.get("/students/me/profile", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["profile_completion"] == 0
    assert body["updated_at"] is None
    assert body["skills"] == ""


def test_student_profile_update_persists_and_reports_completion(client):
    headers, _ = register(client)

    updated = client.put(
        "/students/me/profile", json=STUDENT_PROFILE, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["profile_completion"] == 100
    assert updated.json()["updated_at"] is not None

    fetched = client.get("/students/me/profile", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["skills"] == "Python, PyTorch"
    assert fetched.json()["courses"] == "Machine Learning, Algorithms"


def test_profile_completion_counts_filled_fields(client):
    headers, _ = register(client)

    response = client.put(
        "/students/me/profile",
        json={
            "research_areas": "AI",
            "expertise": "",
            "skills": "Python",
            "projects": "",
            "publications": "",
            "courses": "",
            "academic_details": "",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["profile_completion"] == 29


def test_student_profiles_are_isolated_between_accounts(client):
    first_headers, first_email = register(client)
    second_headers, second_email = register(client)

    client.put(
        "/students/me/profile",
        json={**STUDENT_PROFILE, "skills": "Python"},
        headers=first_headers,
    )
    client.put(
        "/students/me/profile",
        json={**STUDENT_PROFILE, "skills": "Java"},
        headers=second_headers,
    )

    first = client.get("/students/me/profile", headers=first_headers).json()
    second = client.get("/students/me/profile", headers=second_headers).json()

    assert first["skills"] == "Python"
    assert second["skills"] == "Java"
    assert first_email != second_email


def test_profile_update_rejects_ownership_fields(client):
    headers, _ = register(client)

    response = client.put(
        "/students/me/profile",
        json={**STUDENT_PROFILE, "user_id": 999},
        headers=headers,
    )

    assert response.status_code == 422
    assert client.get("/students/me/profile", headers=headers).json()[
        "profile_completion"
    ] == 0


def test_student_endpoints_require_authentication(client):
    assert client.get("/students/me/profile").status_code == 401
    assert client.put("/students/me/profile", json={}).status_code == 401
    assert client.post("/students/me/recommendations", json={}).status_code == 401


def test_faculty_cannot_access_student_profile(client):
    headers, _ = register(client, role="faculty")

    assert client.get("/students/me/profile", headers=headers).status_code == 403
    assert (
        client.put("/students/me/profile", json={}, headers=headers).status_code
        == 403
    )
    assert (
        client.post("/students/me/recommendations", json={}, headers=headers).status_code
        == 403
    )


def test_student_cannot_access_faculty_profile(client):
    headers, _ = register(client)

    assert client.get("/faculty/me/profile", headers=headers).status_code == 403
    assert (
        client.put("/faculty/me/profile", json={}, headers=headers).status_code
        == 403
    )


def test_faculty_profile_persists(client):
    headers, _ = register(client, role="faculty")
    payload = {
        "department": "Computer Science and Engineering",
        "designation": "Associate Professor",
        "research_areas": "Machine Learning, Computer Vision",
        "expertise": "Deep Learning",
        "skills": "Python, PyTorch",
        "publications": "Vision Transformers for Detection",
        "projects": "Campus Vision Lab",
        "profile_url": "https://example.edu/faculty/test",
    }

    updated = client.put("/faculty/me/profile", json=payload, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["profile_completion"] == 100

    fetched = client.get("/faculty/me/profile", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["department"] == payload["department"]
    assert fetched.json()["profile_url"] == payload["profile_url"]


def test_recommendations_require_a_saved_profile(client):
    headers, _ = register(client)

    response = client.post(
        "/students/me/recommendations", json={"top_k": 3}, headers=headers
    )
    assert response.status_code == 400


def test_saved_profile_drives_recommendations(client, seeded_db, patch_semantic):
    patch_semantic()
    headers, _ = register(client)

    client.put(
        "/students/me/profile", json=STUDENT_PROFILE, headers=headers
    )
    response = client.post(
        "/students/me/recommendations", json={"top_k": 2}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["student_profile"]["skills"] == "Python, PyTorch"
    assert body["profile_completion"] == 100
    assert len(body["recommendations"]) == 2

    for item in body["recommendations"]:
        assert "python" in item["matched_skills"]


def test_profile_changes_affect_subsequent_recommendations(
    client, seeded_db, patch_semantic
):
    patch_semantic()
    headers, _ = register(client)
    client.put(
        "/students/me/profile", json=STUDENT_PROFILE, headers=headers
    )

    client.put(
        "/students/me/profile",
        json={**STUDENT_PROFILE, "skills": "Rust, Go"},
        headers=headers,
    )
    response = client.post(
        "/students/me/recommendations", json={"top_k": 2}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["student_profile"]["skills"] == "Rust, Go"
    for item in response.json()["recommendations"]:
        assert "python" not in item["matched_skills"]


def test_linked_faculty_profile_initializes_from_existing_researcher(client, seeded_db, db):
    from app.models import FacultyResearcherLink, Researcher

    headers, email = register(client, role="faculty")
    faculty = db.query(User).filter_by(email=email).one()
    researcher = db.query(Researcher).first()
    db.add(FacultyResearcherLink(faculty_user_id=faculty.id,
                               researcher_id=researcher.id, created_at=1))
    db.commit()
    response = client.get("/faculty/me/profile", headers=headers)
    assert response.status_code == 200
    assert response.json()["skills"] == researcher.skills
    assert response.json()["projects"] == researcher.projects
    assert db.query(FacultyProfile).filter_by(user_id=faculty.id).count() == 0


def test_faculty_save_never_mutates_shared_researcher_record(client, seeded_db, db):
    from app.models import FacultyResearcherLink, Researcher

    headers, email = register(client, role="faculty")
    faculty = db.query(User).filter_by(email=email).one()
    researchers = db.query(Researcher).order_by(Researcher.id).all()
    linked, other = researchers[:2]
    db.add(FacultyResearcherLink(faculty_user_id=faculty.id,
                               researcher_id=linked.id, created_at=1))
    db.commit()
    directory_before = client.get("/researchers/").json()
    linked_before = client.get(f"/researchers/{linked.id}").json()
    other_before = client.get(f"/researchers/{other.id}").json()

    response = client.put("/faculty/me/profile", json={
        "skills": "Rust, Python", "projects": "Distributed research tools",
        "expertise": "Systems", "profile_url": "https://example.edu/verified",
    }, headers=headers)
    assert response.status_code == 200, response.text

    # The faculty member's own profile is the only record the save may change.
    saved = client.get("/faculty/me/profile", headers=headers).json()
    assert saved["skills"] == "Rust, Python"
    assert saved["projects"] == "Distributed research tools"
    assert saved["expertise"] == "Systems"
    assert saved["profile_url"] == "https://example.edu/verified"

    assert client.get(f"/researchers/{linked.id}").json() == linked_before
    assert client.get(f"/researchers/{other.id}").json() == other_before
    assert client.get("/researchers/").json() == directory_before
    db.expire_all()
    assert db.query(Researcher).count() == len(researchers)
    link = db.query(FacultyResearcherLink).one()
    assert (link.faculty_user_id, link.researcher_id) == (faculty.id, linked.id)


def test_partial_faculty_save_does_not_blank_shared_record(client, seeded_db, db):
    from app.models import FacultyResearcherLink, Researcher

    headers, email = register(client, role="faculty")
    faculty = db.query(User).filter_by(email=email).one()
    linked = db.query(Researcher).order_by(Researcher.id).first()
    db.add(FacultyResearcherLink(faculty_user_id=faculty.id,
                               researcher_id=linked.id, created_at=1))
    db.commit()
    before = client.get(f"/researchers/{linked.id}").json()
    shared_fields = (
        "department", "designation", "research_areas", "expertise",
        "skills", "publications", "projects", "profile_url",
    )
    assert before["projects"], "seed fixture must give the shared record text to protect"

    # Unsent payload fields default to "" so a partial save must not reach the directory.
    saved = client.put("/faculty/me/profile", json={"skills": "Rust"}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["skills"] == "Rust"

    after = client.get(f"/researchers/{linked.id}").json()
    for field in shared_fields:
        assert after[field] == before[field]


def test_faculty_profile_save_never_creates_a_link(client, seeded_db, db):
    from app.models import FacultyResearcherLink

    headers, _ = register(client, role="faculty")
    directory_before = client.get("/researchers/").json()

    saved = client.put("/faculty/me/profile", json={"skills": "Private draft"}, headers=headers)

    assert saved.status_code == 200, saved.text
    assert db.query(FacultyResearcherLink).count() == 0
    assert client.get("/faculty/me/researcher-link", headers=headers).json() == {
        "linked": False, "researcher": None
    }
    assert client.get("/researchers/").json() == directory_before


def test_unlinked_faculty_profile_never_changes_directory(client, seeded_db):
    headers, _ = register(client, role="faculty")
    original = client.get("/researchers/").json()
    saved = client.put("/faculty/me/profile", json={"skills": "Private draft"}, headers=headers)
    assert saved.status_code == 200
    assert client.get("/researchers/").json() == original


def test_faculty_profile_rejects_unsafe_external_url(client):
    headers, _ = register(client, role="faculty")
    response = client.put("/faculty/me/profile", json={
        "profile_url": "javascript:alert(1)",
    }, headers=headers)
    assert response.status_code == 422
    assert client.get("/faculty/me/profile", headers=headers).json()["updated_at"] is None
