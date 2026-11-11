"""Consolidated expertise gap analysis and gap-covering researcher recommendations."""

import time

import pytest

from app.database import SessionLocal
from app.models import ResearcherVerification
from conftest import register_test_account

GAPS = "/students/me/expertise-gaps"
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
def clean_verification_rows():
    def cleanup():
        session = SessionLocal()
        try:
            session.query(ResearcherVerification).delete()
            session.commit()
        finally:
            session.close()

    cleanup()
    yield cleanup()


def _profile(**values):
    return {field: "" for field in PROFILE_FIELDS} | values


def _student(client, **values):
    headers, _ = register_test_account(client)
    saved = client.put(
        "/students/me/profile", json=_profile(**values), headers=headers
    )
    assert saved.status_code == 200, saved.text
    return headers


def test_expertise_gaps_require_a_student_session_and_saved_profile(client, seeded_db):
    assert client.get(GAPS).status_code == 401

    faculty_headers, _ = register_test_account(client, role="faculty")
    assert client.get(GAPS, headers=faculty_headers).status_code == 403

    student_headers, _ = register_test_account(client)
    response = client.get(GAPS, headers=student_headers)
    assert response.status_code == 400
    assert "profile" in response.json()["detail"].lower()


def test_blank_student_terms_do_not_produce_gaps(client, seeded_db):
    headers = _student(client)

    body = client.get(GAPS, headers=headers).json()

    assert body["student_skills_provided"] is False
    assert body["gaps"] == []
    assert body["total_gaps"] == 0
    assert body["recommended_researchers"] == []
    assert body["student_terms"] == {
        "skills": [],
        "expertise": [],
        "research_areas": [],
    }


def test_gaps_cover_skills_expertise_and_research_areas(client, seeded_db):
    headers = _student(client, skills="Python, SQL")

    body = client.get(GAPS, headers=headers).json()

    assert body["student_skills_provided"] is True
    assert body["student_terms"]["skills"] == ["python", "sql"]
    assert body["total_gaps"] == 17
    assert body["limit"] == 25
    assert body["verified_only"] is False

    gaps = {(row["kind"], row["term"]): row for row in body["gaps"]}
    assert ("skill", "pytorch") in gaps
    assert ("expertise", "deep learning") in gaps
    assert ("research_area", "machine learning") in gaps
    assert ("skill", "python") not in gaps
    assert ("skill", "sql") not in gaps

    machine_learning = gaps[("research_area", "machine learning")]
    assert machine_learning["researcher_count"] == 2
    assert {row["name"] for row in machine_learning["researchers"]} == {
        "Dr. Ada Lovelace",
        "Dr. Alan Turing",
    }
    assert body["gaps"][0]["term"] == "machine learning"

    pytorch = gaps[("skill", "pytorch")]
    assert pytorch["researcher_count"] == 1
    assert pytorch["researchers"][0]["name"] == "Dr. Ada Lovelace"
    assert pytorch["researchers"][0]["verification_status"] == "unverified"


def test_student_expertise_and_research_areas_are_not_reported_as_gaps(
    client, seeded_db
):
    headers = _student(
        client,
        skills="Python",
        expertise="Deep Learning",
        research_areas="Machine Learning",
    )

    body = client.get(GAPS, headers=headers).json()

    terms = {(row["kind"], row["term"]) for row in body["gaps"]}
    assert ("expertise", "deep learning") not in terms
    assert ("research_area", "machine learning") not in terms
    assert ("skill", "pytorch") in terms


def test_recommended_researchers_are_ranked_by_gap_coverage(client, seeded_db):
    headers = _student(client, skills="Python, SQL")

    body = client.get(GAPS, headers=headers).json()
    recommended = body["recommended_researchers"]

    assert len(recommended) == 3
    grace = next(row for row in recommended if row["name"] == "Dr. Grace Hopper")
    assert grace["gap_coverage"] == 6
    assert set(grace["addressed_gaps"]) >= {
        "cybersecurity",
        "network security",
        "linux",
        "wireshark",
    }
    # The seeded researchers each cover six of the seventeen gaps.
    assert all(row["gap_coverage"] == 6 for row in recommended)
    assert [row["gap_coverage"] for row in recommended] == sorted(
        (row["gap_coverage"] for row in recommended), reverse=True
    )


def test_limit_and_verified_only_filter(client, seeded_db, db):
    from app.models import Researcher, ResearcherVerification

    headers = _student(client, skills="Python")
    limited = client.get(GAPS, params={"limit": 2}, headers=headers).json()

    assert len(limited["gaps"]) == 2
    assert limited["total_gaps"] == 17

    ada = db.query(Researcher).filter_by(name="Dr. Ada Lovelace").one()
    db.add(
        ResearcherVerification(
            researcher_id=ada.id,
            status="verified",
            evidence_reference="out-of-band",
            note="",
            review_note="",
            submitted_by_user_id=None,
            reviewed_by_user_id=None,
            submitted_at=int(time.time()),
            reviewed_at=int(time.time()),
            expires_at=None,
            created_at=int(time.time()),
        )
    )
    db.commit()

    filtered = client.get(
        GAPS, params={"verified_only": "true"}, headers=headers
    ).json()

    assert {row["researcher_count"] for row in filtered["gaps"]} == {1}
    assert all(
        researcher["name"] == "Dr. Ada Lovelace"
        for row in filtered["gaps"]
        for researcher in row["researchers"]
    )
    assert [row["name"] for row in filtered["recommended_researchers"]] == [
        "Dr. Ada Lovelace"
    ]


def test_empty_directory_returns_no_gaps(client, empty_db):
    headers = _student(client, skills="Python")

    body = client.get(GAPS, headers=headers).json()

    assert body["student_skills_provided"] is True
    assert body["gaps"] == []
    assert body["total_gaps"] == 0
    assert body["recommended_researchers"] == []


@pytest.mark.parametrize("limit", [0, 101])
def test_invalid_limit_is_rejected(client, seeded_db, limit):
    headers = _student(client, skills="Python")

    assert client.get(GAPS, params={"limit": limit}, headers=headers).status_code == 422
