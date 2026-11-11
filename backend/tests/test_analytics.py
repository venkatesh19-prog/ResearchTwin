"""University and department research analytics."""

import time

import pytest
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import (
    CollaborationRequest,
    FacultyResearcherLink,
    Researcher,
    ResearcherVerification,
)
from conftest import register_test_account

UNIVERSITY = "/analytics/university"
DEPARTMENTS = "/analytics/departments"


@pytest.fixture(autouse=True)
def clean_analytics_tables():
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


def _researcher(db, name):
    return db.query(Researcher).filter_by(name=name).one()


def test_analytics_requires_authentication(client, seeded_db):
    assert client.get(UNIVERSITY).status_code == 401
    assert client.get(DEPARTMENTS).status_code == 401


def test_every_authenticated_role_can_read_analytics(client, seeded_db, admin_headers):
    student_headers, _ = register_test_account(client, role="student")
    faculty_headers, _ = register_test_account(client, role="faculty")

    for headers in (student_headers, faculty_headers, admin_headers):
        assert client.get(UNIVERSITY, headers=headers).status_code == 200
        assert client.get(DEPARTMENTS, headers=headers).status_code == 200


def test_university_summary_uses_actual_directory_data(
    client, seeded_db, admin_headers
):
    body = client.get(UNIVERSITY, headers=admin_headers).json()

    assert body["researchers"] == {
        "total": 3,
        "departments": 2,
        "verified": 0,
        "pending_verification": 0,
        "expired_verification": 0,
        "with_publications": 3,
        "with_projects": 3,
        "average_experience_years": 12.0,
    }
    assert body["collaboration"] == {
        "total": 0,
        "pending": 0,
        "accepted": 0,
        "rejected": 0,
        "acceptance_rate": None,
    }
    assert body["research_areas"]["distinct"] == 6
    assert body["research_areas"]["top"][0] == {
        "area": "machine learning",
        "researcher_count": 2,
    }
    assert set(body["accounts"]) == {
        "students",
        "faculty",
        "admins",
        "active_faculty_links",
    }
    assert all(isinstance(value, int) for value in body["accounts"].values())


def test_university_summary_is_honest_for_an_empty_directory(
    client, empty_db, admin_headers
):
    body = client.get(UNIVERSITY, headers=admin_headers).json()

    assert body["researchers"]["total"] == 0
    assert body["researchers"]["departments"] == 0
    assert body["researchers"]["average_experience_years"] is None
    assert body["researchers"]["verified"] == 0
    assert body["collaboration"]["total"] == 0
    assert body["collaboration"]["acceptance_rate"] is None
    assert body["research_areas"] == {"distinct": 0, "top": []}


def test_department_analytics_matches_researcher_records(
    client, seeded_db, admin_headers
):
    body = client.get(DEPARTMENTS, headers=admin_headers).json()

    assert body["total"] == 2
    assert [row["department"] for row in body["departments"]] == [
        "Computer Science and Engineering",
        "Information Technology",
    ]

    cse, it = body["departments"]
    assert cse["researcher_count"] == 2
    assert cse["average_experience_years"] == 13.5
    assert cse["verified_researcher_count"] == 0
    assert cse["pending_verification_count"] == 0
    assert cse["researchers_with_publications"] == 2
    assert cse["researchers_with_projects"] == 2
    assert cse["faculty_account_count"] == 0
    assert cse["designations"] == [{"designation": "Professor", "count": 2}]
    assert cse["top_research_areas"][0] == {
        "area": "machine learning",
        "researcher_count": 2,
    }
    assert cse["collaboration"] == {"total": 0, "accepted": 0}

    assert it["researcher_count"] == 1
    assert it["average_experience_years"] == 9.0
    assert it["designations"] == [
        {"designation": "Associate Professor", "count": 1}
    ]


def test_department_filter_is_case_insensitive_and_paginated(
    client, seeded_db, admin_headers
):
    filtered = client.get(
        DEPARTMENTS,
        params={"department": "INFORMATION TECHNOLOGY"},
        headers=admin_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["departments"][0]["department"] == "Information Technology"

    second_page = client.get(
        DEPARTMENTS, params={"offset": 1, "limit": 1}, headers=admin_headers
    )
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert [row["department"] for row in second_page.json()["departments"]] == [
        "Information Technology"
    ]

    missing = client.get(
        DEPARTMENTS, params={"department": "Nonexistent"}, headers=admin_headers
    )
    assert missing.status_code == 200
    assert missing.json() == {
        "departments": [],
        "total": 0,
        "offset": 0,
        "limit": 100,
    }


def test_collaboration_and_verification_statistics(
    client, seeded_db, admin_headers, db
):
    now = int(time.time())
    ada = _researcher(db, "Dr. Ada Lovelace")
    grace = _researcher(db, "Dr. Grace Hopper")
    _, student = register_test_account(client, role="student")
    _, faculty = register_test_account(client, role="faculty")

    db.add_all(
        [
            CollaborationRequest(
                student_user_id=student["id"],
                researcher_id=ada.id,
                message="Pending",
                status="pending",
                faculty_response="",
                created_at=now,
                updated_at=now,
            ),
            CollaborationRequest(
                student_user_id=student["id"],
                researcher_id=ada.id,
                message="Accepted",
                status="accepted",
                faculty_response="Welcome",
                created_at=now,
                updated_at=now,
                reviewed_at=now,
            ),
            CollaborationRequest(
                student_user_id=student["id"],
                researcher_id=ada.id,
                message="Rejected",
                status="rejected",
                faculty_response="Not this term",
                created_at=now,
                updated_at=now,
                reviewed_at=now,
            ),
            ResearcherVerification(
                researcher_id=grace.id,
                status="pending",
                evidence_reference="private-evidence",
                note="",
                review_note="",
                submitted_by_user_id=faculty["id"],
                reviewed_by_user_id=None,
                submitted_at=now,
                reviewed_at=None,
                expires_at=None,
                created_at=now,
            ),
            FacultyResearcherLink(
                faculty_user_id=faculty["id"],
                researcher_id=ada.id,
                created_at=now,
            ),
        ]
    )
    db.commit()

    body = client.get(UNIVERSITY, headers=admin_headers).json()
    assert body["collaboration"] == {
        "total": 3,
        "pending": 1,
        "accepted": 1,
        "rejected": 1,
        "acceptance_rate": 0.5,
    }
    assert body["researchers"]["pending_verification"] == 1
    assert body["researchers"]["verified"] == 0
    assert body["accounts"]["active_faculty_links"] == 1

    departments = client.get(DEPARTMENTS, headers=admin_headers).json()["departments"]
    it = next(row for row in departments if row["department"] == "Information Technology")
    assert it["pending_verification_count"] == 1
    cse = next(
        row for row in departments if row["department"] == "Computer Science and Engineering"
    )
    assert cse["collaboration"] == {"total": 3, "accepted": 1}

    record = db.query(ResearcherVerification).filter_by(researcher_id=grace.id).one()
    record.status = "verified"
    record.reviewed_at = now
    db.commit()

    body = client.get(UNIVERSITY, headers=admin_headers).json()
    assert body["researchers"]["verified"] == 1
    assert body["researchers"]["pending_verification"] == 0

    departments = client.get(DEPARTMENTS, headers=admin_headers).json()["departments"]
    it = next(row for row in departments if row["department"] == "Information Technology")
    assert it["verified_researcher_count"] == 1
    assert it["pending_verification_count"] == 0


def test_department_page_is_bounded_in_the_database(
    client, seeded_db, admin_headers, db
):
    now = int(time.time())
    _, student = register_test_account(client, role="student")
    for index in range(4):
        db.add(
            Researcher(
                name=f"Dr. Aardvark {index}",
                department=f"Aardvark Department {index}",
                designation="Lecturer",
                experience=5 + index,
                research_areas="Formal Methods",
                expertise="",
                skills="",
                publications="",
                projects="",
                profile_url="",
            )
        )
    db.flush()

    page_department = db.query(Researcher).filter_by(
        name="Dr. Aardvark 0"
    ).one()
    other_department = _researcher(db, "Dr. Grace Hopper")
    db.add_all(
        [
            CollaborationRequest(
                student_user_id=student["id"],
                researcher_id=page_department.id,
                message="Accepted on the page",
                status="accepted",
                faculty_response="Welcome",
                created_at=now,
                updated_at=now,
                reviewed_at=now,
            ),
            CollaborationRequest(
                student_user_id=student["id"],
                researcher_id=other_department.id,
                message="Outside the page",
                status="pending",
                faculty_response="",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.commit()

    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.lower().split()))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            DEPARTMENTS, params={"offset": 0, "limit": 2}, headers=admin_headers
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 6
    assert [row["department"] for row in body["departments"]] == [
        "Aardvark Department 0",
        "Aardvark Department 1",
    ]
    assert body["departments"][0]["collaboration"] == {"total": 1, "accepted": 1}
    assert body["departments"][1]["collaboration"] == {"total": 0, "accepted": 0}

    unaggregated_requests = [
        statement
        for statement in statements
        if "from collaboration_requests" in statement and "group by" not in statement
    ]
    assert unaggregated_requests == []

    researcher_row_reads = [
        statement
        for statement in statements
        if statement.startswith("select researchers.") and " from researchers" in statement
    ]
    assert researcher_row_reads
    assert all(" where " in statement for statement in researcher_row_reads)
    assert any(" limit " in statement for statement in statements)
