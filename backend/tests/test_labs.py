"""Research lab directory: institutions, visibility and lab membership."""

import json
import uuid

import pytest

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    Institution,
    InstitutionMembership,
    InterUniversityCollaboration,
    ResearchLab,
    ResearchLabMember,
)
from conftest import register_test_account


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


def _institution(client, admin_headers, name=None):
    response = client.post(
        "/admin/institutions",
        json={"name": name or _name("University")},
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


def _lab(client, headers, name=None, visibility="institution", **extra):
    response = client.post(
        "/labs",
        json={
            "name": name or _name("Lab"),
            "description": "Applied systems research.",
            "research_areas": "Machine Learning, Retrieval",
            "visibility": visibility,
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_institution_directory_and_admin_provisioning(
    client, db, admin_headers
):
    institution = _institution(client, admin_headers, "Alpha University")
    assert institution["name"] == "Alpha University"
    assert institution["member_count"] == 0
    assert institution["lab_count"] == 0

    public = client.get("/institutions")
    assert public.status_code == 200, public.text
    assert [item["id"] for item in public.json()["institutions"]] == [
        institution["id"]
    ]

    duplicate = client.post(
        "/admin/institutions",
        json={"name": "Alpha University"},
        headers=admin_headers,
    )
    assert duplicate.status_code == 409

    student_headers, _ = register_test_account(client, role="student")
    forbidden = client.post(
        "/admin/institutions",
        json={"name": _name("University")},
        headers=student_headers,
    )
    assert forbidden.status_code == 403

    faculty_headers, faculty = _affiliate(
        client, admin_headers, institution["id"]
    )
    unaffiliated_headers, _ = register_test_account(client, role="faculty")
    assert client.get(
        "/institutions/me", headers=unaffiliated_headers
    ).json() == {"institution": None}

    mine = client.get("/institutions/me", headers=faculty_headers)
    assert mine.status_code == 200, mine.text
    assert mine.json()["institution"]["id"] == institution["id"]

    members = client.get(
        f"/admin/institutions/{institution['id']}/members",
        headers=admin_headers,
    )
    assert members.status_code == 200, members.text
    assert [row["user_id"] for row in members.json()["members"]] == [
        faculty["id"]
    ]

    second = _institution(client, admin_headers)
    move = client.put(
        f"/admin/institutions/{second['id']}/members/{faculty['id']}",
        headers=admin_headers,
    )
    assert move.status_code == 409

    removed = client.delete(
        f"/admin/institutions/{institution['id']}/members/{faculty['id']}",
        headers=admin_headers,
    )
    assert removed.status_code == 200, removed.text
    assert client.get(
        "/institutions/me", headers=faculty_headers
    ).json() == {"institution": None}

    anonymous_admin = client.get("/admin/institutions")
    assert anonymous_admin.status_code == 401


def test_lab_creation_requires_faculty_and_institution(
    client, admin_headers
):
    student_headers, _ = register_test_account(client, role="student")
    assert client.post(
        "/labs", json={"name": _name("Lab")}, headers=student_headers
    ).status_code == 403

    lone_faculty, _ = register_test_account(client, role="faculty")
    assert client.post(
        "/labs", json={"name": _name("Lab")}, headers=lone_faculty
    ).status_code == 400

    institution = _institution(client, admin_headers)
    faculty_headers, faculty = _affiliate(
        client, admin_headers, institution["id"]
    )
    name = _name("Lab")
    created = _lab(client, faculty_headers, name=name, visibility="public")
    assert created["name"] == name
    assert created["visibility"] == "public"
    assert created["owner_user_id"] == faculty["id"]
    assert created["institution"]["id"] == institution["id"]
    assert created["is_owner"] is True
    assert created["is_member"] is True
    assert [row["user_id"] for row in created["members"]] == [faculty["id"]]

    duplicate = client.post(
        "/labs", json={"name": name}, headers=faculty_headers
    )
    assert duplicate.status_code == 409

    other_institution = _institution(client, admin_headers)
    other_faculty, _ = _affiliate(
        client, admin_headers, other_institution["id"]
    )
    same_name_elsewhere = client.post(
        "/labs", json={"name": name}, headers=other_faculty
    )
    assert same_name_elsewhere.status_code == 201

    assert client.post(
        "/labs", json={"name": "  "}, headers=faculty_headers
    ).status_code == 422
    assert client.post(
        "/labs",
        json={"name": _name("Lab"), "visibility": "secret"},
        headers=faculty_headers,
    ).status_code == 422
    assert client.post(
        "/labs",
        json={"name": _name("Lab"), "owner_user_id": 1},
        headers=faculty_headers,
    ).status_code == 422
    assert client.post("/labs", json={"name": _name("Lab")}).status_code == 401


def test_lab_visibility_and_directory_scoping(client, admin_headers):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    owner_a, _ = _affiliate(client, admin_headers, institution_a["id"])
    student_a, student_a_user = _affiliate(
        client, admin_headers, institution_a["id"], role="student"
    )
    student_b, _ = _affiliate(
        client, admin_headers, institution_b["id"], role="student"
    )

    open_lab = _lab(client, owner_a, visibility="public")
    hidden_lab = _lab(client, owner_a, visibility="institution")

    directory = client.get("/labs")
    assert directory.status_code == 200, directory.text
    assert [item["id"] for item in directory.json()["labs"]] == [open_lab["id"]]
    assert client.get(f"/labs/{hidden_lab['id']}").status_code == 404

    assert client.get(
        f"/labs/{hidden_lab['id']}", headers=student_b
    ).status_code == 404
    visible = client.get(f"/labs/{hidden_lab['id']}", headers=student_a)
    assert visible.status_code == 200, visible.text
    assert visible.json()["institution"]["id"] == institution_a["id"]

    filtered = client.get("/labs", params={"q": open_lab["name"][:10]})
    assert [item["id"] for item in filtered.json()["labs"]] == [open_lab["id"]]

    by_institution = client.get(
        "/labs", params={"institution_id": institution_a["id"]}
    )
    assert [item["id"] for item in by_institution.json()["labs"]] == [
        open_lab["id"]
    ]

    mine = client.get("/labs", params={"mine": True}, headers=owner_a)
    assert mine.status_code == 200, mine.text
    assert {item["id"] for item in mine.json()["labs"]} == {
        open_lab["id"],
        hidden_lab["id"],
    }
    assert client.get(
        "/labs", params={"mine": True}, headers=student_b
    ).json()["total"] == 0
    assert client.get("/labs", params={"mine": True}).status_code == 401

    paged = client.get("/labs", params={"limit": 1}, headers=student_a)
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert len(paged.json()["labs"]) == 1

    institution_detail = client.get(
        f"/labs/{open_lab['id']}", headers=student_a
    ).json()
    assert institution_detail["member_count"] == 1
    assert "members" not in institution_detail
    assert institution_detail["institution"]["name"] == institution_a["name"]


def test_lab_detail_roster_visible_only_to_members(client, admin_headers):
    institution = _institution(client, admin_headers)
    owner_headers, owner = _affiliate(client, admin_headers, institution["id"])
    member_headers, member = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )
    peer_headers, _ = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )
    lab = _lab(client, owner_headers, visibility="public")
    assert client.post(
        f"/labs/{lab['id']}/members",
        json={"user_id": member["id"]},
        headers=owner_headers,
    ).status_code == 201

    anonymous = client.get(f"/labs/{lab['id']}")
    assert anonymous.status_code == 200, anonymous.text
    assert anonymous.json()["member_count"] == 2
    assert "members" not in anonymous.json()
    assert client.get(f"/labs/{lab['id']}/members").status_code == 403

    peer_view = client.get(f"/labs/{lab['id']}", headers=peer_headers)
    assert peer_view.status_code == 200, peer_view.text
    assert "members" not in peer_view.json()
    assert client.get(
        f"/labs/{lab['id']}/members", headers=peer_headers
    ).status_code == 403

    for headers, expected in (
        (owner_headers, {owner["id"], member["id"]}),
        (member_headers, {owner["id"], member["id"]}),
    ):
        detail = client.get(f"/labs/{lab['id']}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert {row["user_id"] for row in detail.json()["members"]} == expected
        roster = client.get(f"/labs/{lab['id']}/members", headers=headers)
        assert roster.status_code == 200, roster.text
        assert {row["user_id"] for row in roster.json()["members"]} == expected


def test_lab_ownership_and_updates(client, admin_headers):
    institution = _institution(client, admin_headers)
    owner, _ = _affiliate(client, admin_headers, institution["id"])
    peer, _ = _affiliate(client, admin_headers, institution["id"])
    outsider_institution = _institution(client, admin_headers)
    outsider, _ = _affiliate(
        client, admin_headers, outsider_institution["id"]
    )

    lab = _lab(client, owner)
    second = _lab(client, owner)

    assert client.put(
        f"/labs/{lab['id']}", json={"name": "Renamed"}, headers=peer
    ).status_code == 403
    assert client.delete(f"/labs/{lab['id']}", headers=peer).status_code == 403
    assert client.put(
        f"/labs/{lab['id']}", json={"name": "Renamed"}, headers=outsider
    ).status_code == 404
    assert client.put(
        f"/labs/{lab['id']}", json={"name": "Renamed"}
    ).status_code == 401

    updated = client.put(
        f"/labs/{lab['id']}",
        json={
            "name": "Renamed Lab",
            "description": "Updated focus.",
            "visibility": "public",
        },
        headers=owner,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "Renamed Lab"
    assert body["description"] == "Updated focus."
    assert body["visibility"] == "public"

    conflict = client.put(
        f"/labs/{lab['id']}",
        json={"name": second["name"]},
        headers=owner,
    )
    assert conflict.status_code == 409

    deleted = client.delete(f"/labs/{lab['id']}", headers=owner)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert client.get(f"/labs/{lab['id']}", headers=owner).status_code == 404
    session = SessionLocal()
    try:
        assert session.query(ResearchLab).filter_by(id=lab["id"]).count() == 0
        assert (
            session.query(ResearchLabMember)
            .filter_by(lab_id=lab["id"])
            .count()
            == 0
        )
    finally:
        session.close()


def test_lab_membership_rules(client, admin_headers):
    institution = _institution(client, admin_headers)
    owner, owner_user = _affiliate(client, admin_headers, institution["id"])
    peer, peer_user = _affiliate(client, admin_headers, institution["id"])
    student, student_user = _affiliate(
        client, admin_headers, institution["id"], role="student"
    )
    outsider_institution = _institution(client, admin_headers)
    outsider, outsider_user = _affiliate(
        client, admin_headers, outsider_institution["id"], role="student"
    )
    lab = _lab(client, owner)
    members_url = f"/labs/{lab['id']}/members"

    added = client.post(
        members_url, json={"user_id": student_user["id"]}, headers=owner
    )
    assert added.status_code == 201, added.text
    assert added.json()["user_id"] == student_user["id"]
    assert added.json()["is_owner"] is False

    assert client.post(
        members_url, json={"user_id": student_user["id"]}, headers=owner
    ).status_code == 409
    assert client.post(
        members_url, json={"user_id": 999999}, headers=owner
    ).status_code == 404
    assert client.post(
        members_url, json={"user_id": owner_user["id"]}, headers=owner
    ).status_code == 422
    assert client.post(
        members_url, json={"user_id": peer_user["id"]}, headers=peer
    ).status_code == 403

    listing = client.get(members_url, headers=owner)
    assert listing.status_code == 200, listing.text
    assert {row["user_id"] for row in listing.json()["members"]} == {
        owner_user["id"],
        student_user["id"],
    }
    assert client.get(members_url, headers=peer).status_code == 403
    assert client.get(members_url, headers=outsider).status_code == 404

    left = client.delete(
        f"{members_url}/{student_user['id']}", headers=student
    )
    assert left.status_code == 200, left.text
    assert client.delete(
        f"{members_url}/{student_user['id']}", headers=student
    ).status_code == 404
    assert client.delete(
        f"{members_url}/{owner_user['id']}", headers=owner
    ).status_code == 422

    re_added = client.post(
        members_url, json={"user_id": student_user["id"]}, headers=owner
    )
    assert re_added.status_code == 201
    removed = client.delete(
        f"{members_url}/{student_user['id']}", headers=owner
    )
    assert removed.status_code == 200

    cross_institution = client.post(
        members_url, json={"user_id": outsider_user["id"]}, headers=owner
    )
    assert cross_institution.status_code == 422


def test_lab_delete_blocked_by_open_collaboration(
    client, admin_headers
):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    owner_a, _ = _affiliate(client, admin_headers, institution_a["id"])
    owner_b, _ = _affiliate(client, admin_headers, institution_b["id"])
    lab_a = _lab(client, owner_a, visibility="public")
    lab_b = _lab(client, owner_b, visibility="public")

    proposal = client.post(
        "/interuniversity-collaborations",
        json={
            "requester_lab_id": lab_a["id"],
            "partner_lab_id": lab_b["id"],
            "title": "Joint retrieval study",
            "description": "Shared benchmark.",
        },
        headers=owner_a,
    )
    assert proposal.status_code == 201, proposal.text

    blocked = client.delete(f"/labs/{lab_a['id']}", headers=owner_a)
    assert blocked.status_code == 409

    declined = client.post(
        f"/interuniversity-collaborations/{proposal.json()['id']}/status",
        json={"status": "declined", "note": "Out of scope for now."},
        headers=owner_b,
    )
    assert declined.status_code == 200, declined.text

    deleted = client.delete(f"/labs/{lab_a['id']}", headers=owner_a)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/labs/{lab_a['id']}", headers=owner_a).status_code == 404


def test_lab_delete_blocked_by_completed_collaboration(client, admin_headers):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    owner_a, _ = _affiliate(client, admin_headers, institution_a["id"])
    owner_b, _ = _affiliate(client, admin_headers, institution_b["id"])
    lab_a = _lab(client, owner_a, visibility="public")
    lab_b = _lab(client, owner_b, visibility="public")

    proposal = client.post(
        "/interuniversity-collaborations",
        json={
            "requester_lab_id": lab_a["id"],
            "partner_lab_id": lab_b["id"],
            "title": "Long-running retrieval study",
            "description": "Shared benchmark.",
        },
        headers=owner_a,
    )
    assert proposal.status_code == 201, proposal.text
    collaboration_id = proposal.json()["id"]

    accepted = client.post(
        f"/interuniversity-collaborations/{collaboration_id}/status",
        json={"status": "active", "note": "Approved."},
        headers=owner_b,
    )
    assert accepted.status_code == 200, accepted.text

    completed = client.post(
        f"/interuniversity-collaborations/{collaboration_id}/status",
        json={"status": "completed", "note": "Study finished."},
        headers=owner_a,
    )
    assert completed.status_code == 200, completed.text

    blocked = client.delete(f"/labs/{lab_a['id']}", headers=owner_a)
    assert blocked.status_code == 409

    history = client.get(
        f"/interuniversity-collaborations/{collaboration_id}", headers=owner_b
    )
    assert history.status_code == 200, history.text
    assert history.json()["status"] == "completed"


def test_lab_delete_records_audit_event(client, db, admin_headers):
    institution_a = _institution(client, admin_headers)
    institution_b = _institution(client, admin_headers)
    owner_a, user_a = _affiliate(client, admin_headers, institution_a["id"])
    owner_b, _ = _affiliate(client, admin_headers, institution_b["id"])
    lab_a = _lab(client, owner_a, visibility="public")
    lab_b = _lab(client, owner_b, visibility="public")

    proposal = client.post(
        "/interuniversity-collaborations",
        json={
            "requester_lab_id": lab_a["id"],
            "partner_lab_id": lab_b["id"],
            "title": "Declined pilot",
            "description": "Not pursued.",
        },
        headers=owner_a,
    )
    assert proposal.status_code == 201, proposal.text

    declined = client.post(
        f"/interuniversity-collaborations/{proposal.json()['id']}/status",
        json={"status": "declined", "note": "Not a fit."},
        headers=owner_b,
    )
    assert declined.status_code == 200, declined.text

    deleted = client.delete(f"/labs/{lab_a['id']}", headers=owner_a)
    assert deleted.status_code == 200, deleted.text

    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == "lab.delete",
            AuditEvent.target_type == "lab",
            AuditEvent.target_id == lab_a["id"],
            AuditEvent.actor_user_id == user_a["id"],
        )
        .all()
    )
    assert len(events) == 1
    event = events[0]
    assert event.actor_user_id == user_a["id"]
    detail = json.loads(event.detail)
    assert detail["name"] == lab_a["name"]
    assert detail["removed_collaborations"] == 1
