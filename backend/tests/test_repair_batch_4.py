"""Batch 4A: SQL-side filtering and pagination for list endpoints."""

import time
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import (
    CollaborationRequest,
    FacultyResearcherLink,
    Institution,
    InstitutionMembership,
    InterUniversityCollaboration,
    LiteratureEntry,
    Opportunity,
    OpportunityApplication,
    ResearchLab,
    ResearchLabMember,
    ResearcherVerification,
    ThesisMilestone,
    ThesisProgressEvent,
    ThesisRecord,
)
from conftest import register_test_account


@contextmanager
def captured_sql():
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", capture)


@pytest.fixture(autouse=True)
def clean_batch_tables():
    def cleanup():
        session = SessionLocal()
        try:
            session.query(InterUniversityCollaboration).delete()
            session.query(ResearchLabMember).delete()
            session.query(ResearchLab).delete()
            session.query(InstitutionMembership).delete()
            session.query(Institution).delete()
            session.query(ThesisProgressEvent).delete()
            session.query(ThesisMilestone).delete()
            session.query(ThesisRecord).delete()
            session.query(OpportunityApplication).delete()
            session.query(Opportunity).delete()
            session.query(CollaborationRequest).delete()
            session.query(FacultyResearcherLink).delete()
            session.query(LiteratureEntry).delete()
            session.query(ResearcherVerification).delete()
            session.commit()
        finally:
            session.close()

    cleanup()
    yield cleanup()


def _institution(client, admin_headers):
    response = client.post(
        "/admin/institutions",
        json={"name": f"Batch University {uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _affiliate(client, admin_headers, institution_id, role="faculty"):
    headers, user = register_test_account(client, role=role)
    assigned = client.put(
        f"/admin/institutions/{institution_id}/members/{user['id']}",
        headers=admin_headers,
    )
    assert assigned.status_code == 200, assigned.text
    return headers, user


def _link_faculty(client, admin_headers, researcher_id):
    headers, user = register_test_account(client, role="faculty")
    response = client.put(
        f"/admin/faculty/{user['id']}/researcher-link",
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    return headers, user


def test_literature_tag_filter_and_page_are_applied_in_sql(client):
    headers, _ = register_test_account(client)

    for title, tags in (
        ("Exact match", ["ml"]),
        ("Prefix only", ["mlops"]),
        ("Multiple tags", ["ml", "nlp"]),
    ):
        created = client.post(
            "/literature", json={"title": title, "tags": tags}, headers=headers
        )
        assert created.status_code == 201, created.text

    with captured_sql() as statements:
        response = client.get(
            "/literature", params={"tag": "ml", "limit": 1}, headers=headers
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert len(body["entries"]) == 1

    literature_statements = [
        statement
        for statement in statements
        if "FROM literature_entries" in statement
    ]
    assert literature_statements
    assert any(
        "LIMIT" in statement.upper() for statement in literature_statements
    )
    assert any("tags" in statement for statement in literature_statements)


def test_thesis_history_is_paginated(client):
    headers, _ = register_test_account(client)
    created = client.post(
        "/theses", json={"title": "Paginated history thesis"}, headers=headers
    )
    assert created.status_code == 201, created.text
    thesis_id = created.json()["id"]

    for index in range(3):
        milestone = client.post(
            f"/theses/{thesis_id}/milestones",
            json={"title": f"Milestone {index}", "due_at": None},
            headers=headers,
        )
        assert milestone.status_code == 201, milestone.text

    response = client.get(
        f"/theses/{thesis_id}/history",
        params={"offset": 1, "limit": 2},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 4
    assert body["offset"] == 1
    assert body["limit"] == 2
    assert len(body["events"]) == 2


def test_lab_member_roster_is_paginated(client, admin_headers):
    institution = _institution(client, admin_headers)
    owner, _ = _affiliate(client, admin_headers, institution["id"])
    first, first_user = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )
    _, second_user = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )

    lab = client.post(
        "/labs",
        json={"name": f"Batch Lab {uuid.uuid4().hex[:8]}"},
        headers=owner,
    )
    assert lab.status_code == 201, lab.text
    lab_id = lab.json()["id"]

    for user in (first_user, second_user):
        added = client.post(
            f"/labs/{lab_id}/members",
            json={"user_id": user["id"]},
            headers=owner,
        )
        assert added.status_code == 201, added.text

    response = client.get(
        f"/labs/{lab_id}/members",
        params={"offset": 1, "limit": 1},
        headers=owner,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert len(body["members"]) == 1


def test_student_collaboration_requests_are_paginated(client, seeded_db):
    headers, _ = register_test_account(client, role="student")
    researcher_ids = [
        researcher["id"] for researcher in client.get("/researchers/").json()[:2]
    ]
    assert len(researcher_ids) == 2

    for researcher_id in researcher_ids:
        created = client.post(
            "/students/me/collaboration-requests",
            json={"researcher_id": researcher_id, "message": "Please collaborate."},
            headers=headers,
        )
        assert created.status_code == 201, created.text

    response = client.get(
        "/students/me/collaboration-requests",
        params={"offset": 1, "limit": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert len(body["requests"]) == 1


def test_faculty_collaboration_inbox_is_paginated(
    client, seeded_db, admin_headers
):
    researcher_id = client.get("/researchers/").json()[0]["id"]
    faculty_headers, _ = _link_faculty(client, admin_headers, researcher_id)

    for _ in range(2):
        student_headers, _ = register_test_account(client, role="student")
        created = client.post(
            "/students/me/collaboration-requests",
            json={"researcher_id": researcher_id, "message": "Please collaborate."},
            headers=student_headers,
        )
        assert created.status_code == 201, created.text

    response = client.get(
        "/faculty/me/collaboration-requests",
        params={"limit": 1},
        headers=faculty_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["offset"] == 0
    assert body["limit"] == 1
    assert len(body["requests"]) == 1


def _create_opportunity(client, admin_headers, title):
    response = client.post(
        "/opportunities",
        json={
            "category": "research",
            "title": title,
            "description": "Batch pagination check.",
            "organization": "Batch Lab",
            "status": "open",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_opportunity_application_lists_are_paginated(client, admin_headers):
    student_a, _ = register_test_account(client, role="student")
    student_b, _ = register_test_account(client, role="student")

    opportunity_ids = [
        _create_opportunity(client, admin_headers, f"Paginated role {index}")
        for index in range(3)
    ]
    for opportunity_id in opportunity_ids:
        for headers in (student_a, student_b):
            applied = client.post(
                f"/opportunities/{opportunity_id}/applications",
                json={"message": "I would like to contribute."},
                headers=headers,
            )
            assert applied.status_code == 201, applied.text

    mine = client.get(
        "/students/me/opportunity-applications",
        params={"offset": 1, "limit": 1},
        headers=student_a,
    )
    assert mine.status_code == 200, mine.text
    mine_body = mine.json()
    assert mine_body["total"] == 3
    assert mine_body["offset"] == 1
    assert mine_body["limit"] == 1
    assert len(mine_body["applications"]) == 1

    managed = client.get(
        f"/opportunities/{opportunity_ids[0]}/applications",
        params={"limit": 1},
        headers=admin_headers,
    )
    assert managed.status_code == 200, managed.text
    managed_body = managed.json()
    assert managed_body["total"] == 2
    assert managed_body["offset"] == 0
    assert managed_body["limit"] == 1
    assert len(managed_body["applications"]) == 1


def test_admin_verification_filter_and_page_are_applied_in_sql(
    client, seeded_db, admin_headers
):
    researcher_ids = [
        researcher["id"] for researcher in client.get("/researchers/").json()[:3]
    ]
    assert len(researcher_ids) == 3

    for researcher_id in researcher_ids:
        headers, _ = _link_faculty(client, admin_headers, researcher_id)
        submitted = client.post(
            "/faculty/me/researcher-link/verification",
            json={
                "evidence_reference": f"https://example.edu/{researcher_id}",
                "note": "Batch pagination check.",
            },
            headers=headers,
        )
        assert submitted.status_code == 201, submitted.text

    with captured_sql() as statements:
        response = client.get(
            "/admin/verifications",
            params={"status": "pending", "offset": 1, "limit": 1},
            headers=admin_headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert len(body["verifications"]) == 1

    verification_statements = [
        statement
        for statement in statements
        if "FROM researcher_verifications" in statement
    ]
    assert verification_statements
    assert any(
        "LIMIT" in statement.upper() for statement in verification_statements
    )


def test_verification_summary_pages_researchers_in_sql(client, seeded_db):
    with captured_sql() as statements:
        response = client.get(
            "/researchers/verification-summary",
            params={"offset": 1, "limit": 1},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert len(body["researchers"]) == 1

    researcher_statements = [
        statement for statement in statements if "FROM researchers" in statement
    ]
    assert researcher_statements
    assert any(
        "LIMIT" in statement.upper() for statement in researcher_statements
    )

    verification_statements = [
        statement
        for statement in statements
        if "FROM researcher_verifications" in statement
    ]
    assert verification_statements
    assert any(
        "max(researcher_verifications.id)" in statement.lower()
        for statement in verification_statements
    )
