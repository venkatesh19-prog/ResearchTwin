"""Inter-university collaboration between labs at different institutions."""

import uuid

import pytest

from app.database import SessionLocal
from app.models import (
    Institution,
    InstitutionMembership,
    InterUniversityCollaboration,
    ResearchLab,
    ResearchLabMember,
)
from conftest import register_test_account

COLLABORATIONS = "/interuniversity-collaborations"


def _name(prefix):
    return f"{prefix} {uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def clean_phase6_tables():
    session = SessionLocal()
    try:
        session.query(InterUniversityCollaboration).delete()
        session.query(ResearchLabMember).delete()
        session.query(ResearchLab).delete()
        session.query(InstitutionMembership).delete()
        session.query(Institution).delete()
        session.commit()
    finally:
        session.close()
    yield


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


def _add_member(client, owner_headers, lab_id, user_id):
    response = client.post(
        f"/labs/{lab_id}/members",
        json={"user_id": user_id},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _propose(client, headers, requester_lab_id, partner_lab_id, title=None):
    return client.post(
        COLLABORATIONS,
        json={
            "requester_lab_id": requester_lab_id,
            "partner_lab_id": partner_lab_id,
            "title": title or _name("Joint study"),
            "description": "Shared benchmark and evaluation.",
        },
        headers=headers,
    )


def _setup(client, admin_headers):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    owner_a, owner_a_user = _affiliate(client, admin_headers, institution_a["id"])
    owner_b, owner_b_user = _affiliate(client, admin_headers, institution_b["id"])
    lab_a = _lab(client, owner_a)
    lab_b = _lab(client, owner_b)
    return {
        "institution_a": institution_a,
        "institution_b": institution_b,
        "owner_a": owner_a,
        "owner_a_user": owner_a_user,
        "owner_b": owner_b,
        "owner_b_user": owner_b_user,
        "lab_a": lab_a,
        "lab_b": lab_b,
    }


def test_cross_institution_collaboration_lifecycle(client, admin_headers):
    data = _setup(client, admin_headers)
    student_a, student_a_user = _affiliate(
        client, admin_headers, data["institution_a"]["id"], role="student"
    )
    student_b, student_b_user = _affiliate(
        client, admin_headers, data["institution_b"]["id"], role="student"
    )
    _add_member(client, data["owner_a"], data["lab_a"]["id"], student_a_user["id"])
    _add_member(client, data["owner_b"], data["lab_b"]["id"], student_b_user["id"])

    assert _propose(
        client,
        student_a,
        data["lab_a"]["id"],
        data["lab_b"]["id"],
    ).status_code == 403

    created = _propose(
        client,
        data["owner_a"],
        data["lab_a"]["id"],
        data["lab_b"]["id"],
        title="Cross-campus retrieval study",
    )
    assert created.status_code == 201, created.text
    collaboration = created.json()
    assert collaboration["status"] == "proposed"
    assert collaboration["access_role"] == "requester"
    assert collaboration["requester_lab"]["id"] == data["lab_a"]["id"]
    assert collaboration["partner_lab"]["id"] == data["lab_b"]["id"]
    assert (
        collaboration["requester_lab"]["institution"]["id"]
        == data["institution_a"]["id"]
    )
    assert (
        collaboration["partner_lab"]["institution"]["id"]
        == data["institution_b"]["id"]
    )
    collaboration_id = collaboration["id"]

    for headers in (data["owner_a"], data["owner_b"], student_a, student_b):
        listing = client.get(COLLABORATIONS, headers=headers)
        assert listing.status_code == 200, listing.text
        assert collaboration_id in {
            item["id"] for item in listing.json()["collaborations"]
        }

    partner_view = client.get(
        f"{COLLABORATIONS}/{collaboration_id}", headers=student_b
    )
    assert partner_view.status_code == 200, partner_view.text
    assert partner_view.json()["access_role"] == "partner"

    accepted = client.post(
        f"{COLLABORATIONS}/{collaboration_id}/status",
        json={"status": "active", "note": "Approved by the partner lab."},
        headers=data["owner_b"],
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "active"
    assert body["responded_at"] is not None
    assert body["decided_by_user_id"] == data["owner_b_user"]["id"]
    assert body["resolution_note"] == "Approved by the partner lab."

    active = client.get(
        COLLABORATIONS, params={"status": "active"}, headers=student_a
    )
    assert active.status_code == 200
    assert [item["id"] for item in active.json()["collaborations"]] == [
        collaboration_id
    ]

    completed = client.post(
        f"{COLLABORATIONS}/{collaboration_id}/status",
        json={"status": "completed", "note": "Benchmark released."},
        headers=data["owner_a"],
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"

    completed_list = client.get(
        COLLABORATIONS, params={"status": "completed"}, headers=data["owner_b"]
    )
    assert completed_list.json()["total"] == 1


def test_collaboration_proposal_authorization(client, admin_headers):
    data = _setup(client, admin_headers)
    peer, peer_user = _affiliate(
        client, admin_headers, data["institution_a"]["id"]
    )
    _add_member(client, data["owner_a"], data["lab_a"]["id"], peer_user["id"])

    not_owner = _propose(
        client, peer, data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert not_owner.status_code == 403

    private_lab = _lab(client, data["owner_b"], visibility="institution")
    hidden = _propose(
        client, data["owner_a"], data["lab_a"]["id"], private_lab["id"]
    )
    assert hidden.status_code == 404

    same_institution = _lab(client, peer)
    same = _propose(
        client, data["owner_a"], data["lab_a"]["id"], same_institution["id"]
    )
    assert same.status_code == 422

    created = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert created.status_code == 201, created.text
    collaboration_id = created.json()["id"]

    outsider_institution = _institution(client, admin_headers)
    outsider, _ = _affiliate(
        client, admin_headers, outsider_institution["id"]
    )
    assert client.get(
        f"{COLLABORATIONS}/{collaboration_id}", headers=outsider
    ).status_code == 404

    requester_accept = client.post(
        f"{COLLABORATIONS}/{collaboration_id}/status",
        json={"status": "active"},
        headers=data["owner_a"],
    )
    assert requester_accept.status_code == 403

    partner_withdraw = client.post(
        f"{COLLABORATIONS}/{collaboration_id}/status",
        json={"status": "withdrawn"},
        headers=data["owner_b"],
    )
    assert partner_withdraw.status_code == 403


def test_collaboration_detail_read_access_for_lab_members(client, admin_headers):
    data = _setup(client, admin_headers)
    student_b, student_b_user = _affiliate(
        client, admin_headers, data["institution_b"]["id"], role="student"
    )
    _add_member(client, data["owner_b"], data["lab_b"]["id"], student_b_user["id"])

    created = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert created.status_code == 201, created.text
    collaboration_id = created.json()["id"]
    path = f"{COLLABORATIONS}/{collaboration_id}"

    detail = client.get(path, headers=student_b)
    assert detail.status_code == 200, detail.text
    assert detail.json()["access_role"] == "partner"

    assert client.get(path).status_code == 401

    student_mutation = client.post(
        f"{path}/status",
        json={"status": "active"},
        headers=student_b,
    )
    assert student_mutation.status_code == 403


def test_collaboration_status_transitions(client, admin_headers):
    data = _setup(client, admin_headers)

    first = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    early_completion = client.post(
        f"{COLLABORATIONS}/{first_id}/status",
        json={"status": "completed"},
        headers=data["owner_a"],
    )
    assert early_completion.status_code == 409

    withdrawn = client.post(
        f"{COLLABORATIONS}/{first_id}/status",
        json={"status": "withdrawn", "note": "Superseded."},
        headers=data["owner_a"],
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"

    terminal = client.post(
        f"{COLLABORATIONS}/{first_id}/status",
        json={"status": "active"},
        headers=data["owner_b"],
    )
    assert terminal.status_code == 409

    second = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]

    declined = client.post(
        f"{COLLABORATIONS}/{second_id}/status",
        json={"status": "declined", "note": "No capacity this term."},
        headers=data["owner_b"],
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"

    third = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert third.status_code == 201, third.text
    third_id = third.json()["id"]
    activated = client.post(
        f"{COLLABORATIONS}/{third_id}/status",
        json={"status": "active"},
        headers=data["owner_b"],
    )
    assert activated.status_code == 200

    same_status = client.post(
        f"{COLLABORATIONS}/{third_id}/status",
        json={"status": "active"},
        headers=data["owner_b"],
    )
    assert same_status.status_code == 409

    invalid_literal = client.post(
        f"{COLLABORATIONS}/{third_id}/status",
        json={"status": "accepted"},
        headers=data["owner_b"],
    )
    assert invalid_literal.status_code == 422


def test_collaboration_duplicates_and_validation(client, admin_headers):
    data = _setup(client, admin_headers)

    created = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert created.status_code == 201, created.text
    collaboration_id = created.json()["id"]

    duplicate = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert duplicate.status_code == 409

    reverse_duplicate = _propose(
        client, data["owner_b"], data["lab_b"]["id"], data["lab_a"]["id"]
    )
    assert reverse_duplicate.status_code == 409

    missing_title = client.post(
        COLLABORATIONS,
        json={
            "requester_lab_id": data["lab_a"]["id"],
            "partner_lab_id": data["lab_b"]["id"],
        },
        headers=data["owner_a"],
    )
    assert missing_title.status_code == 422

    extra_field = client.post(
        COLLABORATIONS,
        json={
            "requester_lab_id": data["lab_a"]["id"],
            "partner_lab_id": data["lab_b"]["id"],
            "title": "Extra",
            "status": "active",
        },
        headers=data["owner_a"],
    )
    assert extra_field.status_code == 422

    missing_lab = _propose(
        client, data["owner_a"], data["lab_a"]["id"], 999999
    )
    assert missing_lab.status_code == 404

    long_note = client.post(
        f"{COLLABORATIONS}/{collaboration_id}/status",
        json={"status": "declined", "note": "x" * 2001},
        headers=data["owner_b"],
    )
    assert long_note.status_code == 422

    declined = client.post(
        f"{COLLABORATIONS}/{collaboration_id}/status",
        json={"status": "declined"},
        headers=data["owner_b"],
    )
    assert declined.status_code == 200

    retry = _propose(
        client, data["owner_a"], data["lab_a"]["id"], data["lab_b"]["id"]
    )
    assert retry.status_code == 201

    outsider_institution = _institution(client, admin_headers)
    outsider, _ = _affiliate(
        client, admin_headers, outsider_institution["id"]
    )
    outsider_list = client.get(COLLABORATIONS, headers=outsider)
    assert outsider_list.status_code == 200
    assert outsider_list.json()["total"] == 0
    assert client.get(
        f"{COLLABORATIONS}/{collaboration_id}", headers=outsider
    ).status_code == 404
