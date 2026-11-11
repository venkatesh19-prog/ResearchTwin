"""Batch 4B: list endpoints must not issue per-row summary queries."""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import (
    Institution,
    InstitutionMembership,
    InterUniversityCollaboration,
    PublicationRevision,
    PublicationStatusEvent,
    PublicationSubmission,
    ResearchLab,
    ResearchLabMember,
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
            session.query(PublicationStatusEvent).delete()
            session.query(PublicationRevision).delete()
            session.query(PublicationSubmission).delete()
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


def _lab(client, headers):
    response = client.post(
        "/labs",
        json={
            "name": f"Batch Lab {uuid.uuid4().hex[:8]}",
            "visibility": "public",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_institution_list_summaries_use_grouped_counts(client, admin_headers):
    for _ in range(3):
        _institution(client, admin_headers)

    with captured_sql() as statements:
        response = client.get("/admin/institutions", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert len(response.json()["institutions"]) >= 3

    membership_counts = [
        statement
        for statement in statements
        if "count(institution_memberships.id)" in statement.lower()
    ]
    lab_counts = [
        statement
        for statement in statements
        if "count(research_labs.id)" in statement.lower()
    ]
    assert len(membership_counts) == 1
    assert len(lab_counts) == 1


def test_lab_list_summaries_avoid_per_row_queries(client, admin_headers):
    institution = _institution(client, admin_headers)
    owner, _ = _affiliate(client, admin_headers, institution["id"])
    for _ in range(3):
        _lab(client, owner)

    with captured_sql() as statements:
        response = client.get("/labs", params={"mine": "true"}, headers=owner)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 3

    member_counts = [
        statement
        for statement in statements
        if "count(research_lab_members.id)" in statement.lower()
    ]
    institution_queries = [
        statement for statement in statements if "FROM institutions" in statement
    ]
    assert len(member_counts) == 1
    assert len(institution_queries) == 1


def test_collaboration_list_reuses_labs_and_institutions(client, admin_headers):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    institution_c = _institution(client, admin_headers)
    owner_a, _ = _affiliate(client, admin_headers, institution_a["id"])
    owner_b, _ = _affiliate(client, admin_headers, institution_b["id"])
    owner_c, _ = _affiliate(client, admin_headers, institution_c["id"])

    lab_a = _lab(client, owner_a)
    lab_b = _lab(client, owner_b)
    lab_c = _lab(client, owner_c)

    for partner_lab in (lab_b, lab_c):
        created = client.post(
            "/interuniversity-collaborations",
            json={
                "requester_lab_id": lab_a["id"],
                "partner_lab_id": partner_lab["id"],
                "title": "Batch partnership",
                "description": "Reuse preloaded references.",
            },
            headers=owner_a,
        )
        assert created.status_code == 201, created.text

    with captured_sql() as statements:
        response = client.get(
            "/interuniversity-collaborations", headers=owner_a
        )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2

    lab_queries = [
        statement for statement in statements if "FROM research_labs" in statement
    ]
    institution_queries = [
        statement for statement in statements if "FROM institutions" in statement
    ]
    assert len(lab_queries) == 1
    assert len(institution_queries) == 1


def test_publication_list_latest_revision_is_grouped(client):
    headers, _ = register_test_account(client)
    for index in range(3):
        created = client.post(
            "/publication-submissions",
            json={
                "title": f"Grouped revision paper {index}",
                "venue": "Batch Journal",
                "venue_type": "journal",
                "doi": "",
                "url": "",
                "notes": "",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text

    with captured_sql() as statements:
        response = client.get("/publication-submissions", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 3

    revision_queries = [
        statement
        for statement in statements
        if "max(publication_revisions.revision_number)" in statement.lower()
    ]
    assert len(revision_queries) == 1
