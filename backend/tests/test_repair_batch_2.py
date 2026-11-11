"""Regression tests for Repair Batch 2 (duplicate requests, role sync, demotion, CAS)."""

import time
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    CollaborationRequest,
    Group,
    GroupMembership,
    Institution,
    InstitutionMembership,
    InterUniversityCollaboration,
    Opportunity,
    OpportunityApplication,
    PublicationRevision,
    PublicationStatusEvent,
    PublicationSubmission,
    ResearchLab,
    ResearchLabMember,
    Researcher,
)
from conftest import register_test_account

COLLABORATIONS = "/interuniversity-collaborations"


def _name(prefix):
    return f"{prefix} {uuid.uuid4().hex[:8]}"


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
            session.query(OpportunityApplication).delete()
            session.query(Opportunity).delete()
            session.query(CollaborationRequest).delete()
            session.query(Researcher).filter(
                Researcher.name.like("Dr. Repair Batch 2%")
            ).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()

    cleanup()
    yield cleanup()


def _institution(client, admin_headers):
    response = client.post(
        "/admin/institutions",
        json={"name": _name("University")},
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


def _lab(client, headers, visibility="public"):
    response = client.post(
        "/labs",
        json={
            "name": _name("Lab"),
            "description": "Collaborative systems research.",
            "research_areas": "Retrieval, Evaluation",
            "visibility": visibility,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup_labs(client, admin_headers):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    owner_a, owner_a_user = _affiliate(
        client, admin_headers, institution_a["id"]
    )
    owner_b, owner_b_user = _affiliate(
        client, admin_headers, institution_b["id"]
    )
    return {
        "institution_a": institution_a,
        "institution_b": institution_b,
        "owner_a": owner_a,
        "owner_a_user": owner_a_user,
        "owner_b": owner_b,
        "owner_b_user": owner_b_user,
        "lab_a": _lab(client, owner_a),
        "lab_b": _lab(client, owner_b),
    }


def _open_collaboration_row(requester_lab_id, partner_lab_id, status="proposed"):
    timestamp = int(time.time())
    pair_key = f"{min(requester_lab_id, partner_lab_id)}:" \
        f"{max(requester_lab_id, partner_lab_id)}"
    return InterUniversityCollaboration(
        requester_lab_id=requester_lab_id,
        partner_lab_id=partner_lab_id,
        title=_name("Joint study"),
        description="Shared benchmark.",
        status=status,
        resolution_note="",
        created_at=timestamp,
        updated_at=timestamp,
        pair_key=pair_key,
    )


def test_open_interuniversity_pair_is_unique_in_the_database(client, admin_headers):
    data = _setup_labs(client, admin_headers)
    lab_a = data["lab_a"]["id"]
    lab_b = data["lab_b"]["id"]

    first = SessionLocal()
    try:
        first.add(_open_collaboration_row(lab_a, lab_b))
        first.commit()
    finally:
        first.close()

    reverse = SessionLocal()
    try:
        reverse.add(_open_collaboration_row(lab_b, lab_a))
        with pytest.raises(IntegrityError):
            reverse.commit()
        reverse.rollback()
    finally:
        reverse.close()

    check = SessionLocal()
    try:
        rows = check.query(InterUniversityCollaboration).all()
        assert len(rows) == 1
    finally:
        check.close()


def test_closed_collaboration_releases_the_lab_pair(client, admin_headers):
    data = _setup_labs(client, admin_headers)
    lab_a = data["lab_a"]["id"]
    lab_b = data["lab_b"]["id"]

    closed = SessionLocal()
    try:
        closed.add(_open_collaboration_row(lab_a, lab_b, status="declined"))
        closed.commit()
    finally:
        closed.close()

    reopened = SessionLocal()
    try:
        reopened.add(_open_collaboration_row(lab_b, lab_a))
        reopened.commit()
    finally:
        reopened.close()

    check = SessionLocal()
    try:
        assert check.query(InterUniversityCollaboration).count() == 2
    finally:
        check.close()


def test_pending_collaboration_request_is_unique_in_the_database(client):
    _, student = register_test_account(client, role="student")
    session = SessionLocal()
    try:
        researcher = Researcher(
            name="Dr. Repair Batch 2 Unique",
            department="Computer Science",
            designation="Professor",
            experience=5,
            research_areas="Reliability",
            expertise="Databases",
            skills="SQL",
            publications="",
            projects="",
            profile_url="https://example.edu/repair-batch-2",
        )
        session.add(researcher)
        session.commit()
        researcher_id = researcher.id
        student_id = student["id"]
    finally:
        session.close()

    timestamp = int(time.time())

    def _request(status="pending"):
        return CollaborationRequest(
            student_user_id=student_id,
            researcher_id=researcher_id,
            message="",
            status=status,
            faculty_response="",
            created_at=timestamp,
            updated_at=timestamp,
        )

    first = SessionLocal()
    try:
        first.add(_request())
        first.commit()
    finally:
        first.close()

    duplicate = SessionLocal()
    try:
        duplicate.add(_request())
        with pytest.raises(IntegrityError):
            duplicate.commit()
        duplicate.rollback()
    finally:
        duplicate.close()

    historical = SessionLocal()
    try:
        historical.add(_request(status="declined"))
        historical.commit()
    finally:
        historical.close()

    check = SessionLocal()
    try:
        rows = (
            check.query(CollaborationRequest)
            .filter(CollaborationRequest.researcher_id == researcher_id)
            .all()
        )
        assert len(rows) == 2
    finally:
        check.close()


def _group_names(db, user_id):
    return {
        name
        for (name,) in (
            db.query(Group.name)
            .join(GroupMembership, GroupMembership.group_id == Group.id)
            .filter(GroupMembership.user_id == user_id)
            .all()
        )
    }


def test_role_change_moves_account_between_role_groups(client, admin_headers, db):
    _, student = register_test_account(client, role="student")
    assert _group_names(db, student["id"]) == {"students"}

    promoted = client.put(
        f"/admin/users/{student['id']}/role",
        json={"role": "faculty"},
        headers=admin_headers,
    )
    assert promoted.status_code == 200, promoted.text
    db.expire_all()
    assert _group_names(db, student["id"]) == {"faculty"}

    demoted = client.put(
        f"/admin/users/{student['id']}/role",
        json={"role": "student"},
        headers=admin_headers,
    )
    assert demoted.status_code == 200, demoted.text
    db.expire_all()
    assert _group_names(db, student["id"]) == {"students"}


def test_admin_role_has_no_role_group(client, admin_headers, db):
    _, student = register_test_account(client, role="student")

    changed = client.put(
        f"/admin/users/{student['id']}/role",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert changed.status_code == 200, changed.text
    db.expire_all()
    assert _group_names(db, student["id"]) == set()


def test_demoted_faculty_cannot_administer_owned_lab(client, admin_headers):
    institution = _institution(client, admin_headers)
    owner_headers, owner = _affiliate(
        client, admin_headers, institution["id"]
    )
    member_headers, member = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )
    lab = _lab(client, owner_headers)
    added = client.post(
        f"/labs/{lab['id']}/members",
        json={"user_id": member["id"]},
        headers=owner_headers,
    )
    assert added.status_code == 201, added.text

    demoted = client.put(
        f"/admin/users/{owner['id']}/role",
        json={"role": "student"},
        headers=admin_headers,
    )
    assert demoted.status_code == 200, demoted.text
    relogin = client.post(
        "/auth/login",
        json={"email": owner["email"], "password": "TestPassword123!"},
    )
    assert relogin.status_code == 200, relogin.text
    headers = {
        "Authorization": f"Bearer {relogin.json()['access_token']}"
    }

    update = client.put(
        f"/labs/{lab['id']}",
        json={"description": "Malicious rename"},
        headers=headers,
    )
    assert update.status_code == 403, update.text

    add = client.post(
        f"/labs/{lab['id']}/members",
        json={"user_id": member["id"]},
        headers=headers,
    )
    assert add.status_code == 403, add.text

    remove = client.delete(
        f"/labs/{lab['id']}/members/{member['id']}",
        headers=headers,
    )
    assert remove.status_code == 403, remove.text

    assert client.get(f"/labs/{lab['id']}", headers=headers).status_code == 200


def test_successful_login_does_not_consume_the_failure_limit(
    client, monkeypatch
):
    _, user = register_test_account(client, role="student")
    monkeypatch.setattr("app.api.auth.LOGIN_MAX", 1)

    wrong = client.post(
        "/auth/login",
        json={"email": user["email"], "password": "WrongPassword123!"},
    )
    assert wrong.status_code == 401, wrong.text

    correct = client.post(
        "/auth/login",
        json={"email": user["email"], "password": "TestPassword123!"},
    )
    assert correct.status_code == 200, correct.text


def test_partial_profile_update_preserves_other_fields(client):
    headers, _ = register_test_account(client, role="student")
    full = {
        "research_areas": "Machine Learning",
        "expertise": "NLP",
        "skills": "Python",
        "projects": "Search engine",
        "publications": "A paper",
        "courses": "Algorithms",
        "academic_details": "B.Tech",
    }
    saved = client.put("/students/me/profile", json=full, headers=headers)
    assert saved.status_code == 200, saved.text

    partial = client.put(
        "/students/me/profile",
        json={"skills": "Rust"},
        headers=headers,
    )
    assert partial.status_code == 200, partial.text
    body = partial.json()
    assert body["skills"] == "Rust"
    for field, value in full.items():
        if field != "skills":
            assert body[field] == value, field


def test_unaffiliation_strips_lab_membership_and_blocks_owned_labs(
    client, admin_headers
):
    institution = _institution(client, admin_headers)
    owner_headers, owner = _affiliate(
        client, admin_headers, institution["id"]
    )
    member_headers, member = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )
    lab = _lab(client, owner_headers, visibility="institution")
    added = client.post(
        f"/labs/{lab['id']}/members",
        json={"user_id": member["id"]},
        headers=owner_headers,
    )
    assert added.status_code == 201, added.text

    owned = client.delete(
        f"/admin/institutions/{institution['id']}/members/{owner['id']}",
        headers=admin_headers,
    )
    assert owned.status_code == 409, owned.text

    removed = client.delete(
        f"/admin/institutions/{institution['id']}/members/{member['id']}",
        headers=admin_headers,
    )
    assert removed.status_code == 200, removed.text

    assert client.get(f"/labs/{lab['id']}", headers=member_headers).status_code == 404
    mine = client.get("/labs", params={"mine": "true"}, headers=member_headers)
    assert mine.status_code == 200
    assert mine.json()["labs"] == []

    session = SessionLocal()
    try:
        assert (
            session.query(ResearchLabMember)
            .filter_by(lab_id=lab["id"], user_id=member["id"])
            .count()
            == 0
        )
    finally:
        session.close()


def test_legacy_recommendation_rejects_unknown_fields(client, monkeypatch):
    headers, _ = register_test_account(client, role="student")
    monkeypatch.setattr(
        "app.api.students.generate_recommendations", lambda **_: []
    )

    response = client.post(
        "/recommendations/researchers",
        json={"skills": "Python", "unexpected": "value"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_legacy_roadmap_rejects_unknown_fields(client):
    headers, _ = register_test_account(client, role="student")

    response = client.post(
        "/recommendations/roadmap/researcher",
        json={"researcher_id": 1, "unexpected": "value"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def _proposal(client, data, headers=None):
    response = client.post(
        COLLABORATIONS,
        json={
            "requester_lab_id": data["lab_a"]["id"],
            "partner_lab_id": data["lab_b"]["id"],
            "title": "Joint retrieval study",
            "description": "Shared benchmark.",
        },
        headers=headers or data["owner_a"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_collaboration_transition_rejects_concurrent_status_change(
    client, admin_headers, monkeypatch
):
    from app.services import labs as lab_service

    data = _setup_labs(client, admin_headers)
    proposal = _proposal(client, data)

    real_affiliated = lab_service.owner_is_affiliated
    fired = {"done": False}

    def affiliate_then_compete(db, lab, user):
        if not fired["done"]:
            fired["done"] = True
            session = SessionLocal()
            try:
                row = session.get(
                    InterUniversityCollaboration, proposal["id"]
                )
                row.status = "declined"
                session.commit()
            finally:
                session.close()
        return real_affiliated(db, lab, user)

    monkeypatch.setattr(
        lab_service, "owner_is_affiliated", affiliate_then_compete
    )

    raced = client.post(
        f"{COLLABORATIONS}/{proposal['id']}/status",
        json={"status": "active", "note": "Accepted."},
        headers=data["owner_b"],
    )
    assert raced.status_code == 409, raced.text

    session = SessionLocal()
    try:
        row = session.get(InterUniversityCollaboration, proposal["id"])
        assert row.status == "declined"
        assert row.resolution_note == ""
    finally:
        session.close()


def test_publication_transition_rejects_concurrent_status_change(
    client, monkeypatch
):
    from app.api import publications as publications_api

    headers, _ = register_test_account(client, role="student")
    created = client.post(
        "/publication-submissions",
        json={
            "title": "Concurrent Retrieval Study",
            "venue": "Journal of Research Systems",
            "venue_type": "journal",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    submitted = client.post(
        f"/publication-submissions/{submission_id}/status",
        json={"status": "submitted"},
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text

    real_now = publications_api.research_outputs.now
    fired = {"done": False}

    def now_then_compete():
        if not fired["done"]:
            fired["done"] = True
            session = SessionLocal()
            try:
                row = session.get(PublicationSubmission, submission_id)
                row.status = "withdrawn"
                session.commit()
            finally:
                session.close()
        return real_now()

    monkeypatch.setattr(
        publications_api.research_outputs, "now", now_then_compete
    )

    raced = client.post(
        f"/publication-submissions/{submission_id}/status",
        json={"status": "under_review", "note": "Reviewing."},
        headers=headers,
    )
    assert raced.status_code == 409, raced.text

    session = SessionLocal()
    try:
        row = session.get(PublicationSubmission, submission_id)
        assert row.status == "withdrawn"
        assert (
            session.query(PublicationStatusEvent)
            .filter(PublicationStatusEvent.to_status == "under_review")
            .count()
            == 0
        )
    finally:
        session.close()


def test_application_withdrawal_rejects_concurrent_decision(
    client, admin_headers
):
    from sqlalchemy import event

    from app.database import engine

    created = client.post(
        "/opportunities",
        json={
            "category": "research",
            "title": "Concurrent Application Study",
            "description": "Work on retrieval.",
            "organization": "AI Lab",
            "status": "open",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    opportunity_id = created.json()["id"]

    headers, _ = register_test_account(client, role="student")
    applied = client.post(
        f"/opportunities/{opportunity_id}/applications",
        json={"message": "I would like to contribute."},
        headers=headers,
    )
    assert applied.status_code == 201, applied.text
    application_id = applied.json()["id"]

    fired = {"done": False}

    def decide_before_withdraw_update(
        conn, cursor, statement, parameters, context, executemany
    ):
        if fired["done"]:
            return
        normalized = " ".join(statement.split()).upper()
        if not normalized.startswith("UPDATE OPPORTUNITY_APPLICATIONS"):
            return
        fired["done"] = True
        session = SessionLocal()
        try:
            row = session.get(OpportunityApplication, application_id)
            row.status = "accepted"
            row.updated_at = int(time.time())
            session.commit()
        finally:
            session.close()

    event.listen(
        engine, "before_cursor_execute", decide_before_withdraw_update
    )
    try:
        raced = client.delete(
            f"/opportunities/{opportunity_id}/applications/me",
            headers=headers,
        )
    finally:
        event.remove(
            engine, "before_cursor_execute", decide_before_withdraw_update
        )
    assert raced.status_code == 409, raced.text
    assert fired["done"] is True

    session = SessionLocal()
    try:
        row = session.get(OpportunityApplication, application_id)
        assert row.status == "accepted"
    finally:
        session.close()
