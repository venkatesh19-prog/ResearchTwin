"""Research teams: ownership, invitations, membership, and team recommendations.

These teams are deliberately separate from the role groups used for access
control (``groups``/``group_memberships``).
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    Group,
    GroupMembership,
    ResearchTeam,
    ResearchTeamInvitation,
    ResearchTeamMember,
    User,
)
from app.services import recommendation, semantic_matching
from conftest import register_test_account

TEAMS = "/teams"
FOCUS = {
    "research_areas": "Artificial Intelligence, Machine Learning",
    "expertise": "Deep Learning, NLP",
    "skills": "Python, PyTorch, Transformers",
    "projects": "Semantic search engine",
    "publications": "Transformer models",
}


@pytest.fixture(autouse=True)
def clean_team_tables():
    session = SessionLocal()
    try:
        session.query(ResearchTeamInvitation).delete()
        session.query(ResearchTeamMember).delete()
        session.query(ResearchTeam).delete()
        session.commit()
    finally:
        session.close()
    yield


def _team(client, headers, name="AI Lab", focus=None):
    payload = {"name": name, "description": "Shared research work."}
    payload.update(FOCUS if focus is None else focus)
    return client.post(TEAMS, json=payload, headers=headers)


def _invite(client, headers, team_id, user_id):
    return client.post(
        f"{TEAMS}/{team_id}/invitations",
        json={"user_id": user_id},
        headers=headers,
    )


def _accept_invitation(client, headers, team_id, invitation_id):
    return client.put(
        f"{TEAMS}/{team_id}/invitations/{invitation_id}",
        json={"decision": "accept"},
        headers=headers,
    )


def _decline_invitation(client, headers, team_id, invitation_id):
    return client.put(
        f"{TEAMS}/{team_id}/invitations/{invitation_id}",
        json={"decision": "decline"},
        headers=headers,
    )


def _team_with_member(client):
    owner_headers, owner = register_test_account(client, role="student")
    member_headers, member = register_test_account(client, role="faculty")
    created = _team(client, owner_headers)
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    invited = _invite(client, owner_headers, team_id, member["id"])
    assert invited.status_code == 201, invited.text
    accepted = _accept_invitation(
        client, member_headers, team_id, invited.json()["id"]
    )
    assert accepted.status_code == 200, accepted.text
    return owner_headers, owner, member_headers, member, team_id


def test_team_creation_and_visibility(client, seeded_db, admin_headers):
    assert client.post(TEAMS, json={"name": "Anonymous"}).status_code == 401

    owner_headers, owner = register_test_account(client, role="student")
    assert _team(client, admin_headers, name="Admin team").status_code == 403

    created = _team(client, owner_headers)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "AI Lab"
    assert body["owner_user_id"] == owner["id"]
    assert body["role"] == "owner"
    assert body["focus"]["research_areas"] == FOCUS["research_areas"]
    assert [(member["user_id"], member["role"]) for member in body["members"]] == [
        (owner["id"], "owner")
    ]

    listing = client.get("/teams/me", headers=owner_headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["teams"]] == [body["id"]]
    assert listing.json()["invitations"] == []

    outsider_headers, _ = register_test_account(client, role="student")
    assert client.get("/teams/me", headers=outsider_headers).json() == {
        "teams": [],
        "invitations": [],
    }
    assert client.get(f"{TEAMS}/{body['id']}", headers=outsider_headers).status_code == 404
    assert client.get(f"{TEAMS}/987654", headers=owner_headers).status_code == 404
    assert client.get(f"{TEAMS}/{body['id']}").status_code == 401


def test_owner_invites_and_invitee_accepts(client, seeded_db):
    owner_headers, owner = register_test_account(client, role="student")
    invitee_headers, invitee = register_test_account(client, role="faculty")
    team_id = _team(client, owner_headers).json()["id"]

    invited = _invite(client, owner_headers, team_id, invitee["id"])
    assert invited.status_code == 201, invited.text
    invitation = invited.json()
    assert invitation["status"] == "pending"

    duplicate = _invite(client, owner_headers, team_id, invitee["id"])
    assert duplicate.status_code == 409, duplicate.text

    pending = client.get("/teams/me", headers=invitee_headers).json()
    assert [item["id"] for item in pending["invitations"]] == [invitation["id"]]
    assert pending["teams"] == []

    owner_view = client.get(f"{TEAMS}/{team_id}", headers=owner_headers).json()
    assert [item["id"] for item in owner_view["invitations"]] == [invitation["id"]]

    outsider_headers, _ = register_test_account(client, role="student")
    assert _accept_invitation(
        client, outsider_headers, team_id, invitation["id"]
    ).status_code == 404

    accepted = _accept_invitation(
        client, invitee_headers, team_id, invitation["id"]
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["responded_at"]

    detail = client.get(f"{TEAMS}/{team_id}", headers=invitee_headers)
    assert detail.status_code == 200, detail.text
    roles = {member["user_id"]: member["role"] for member in detail.json()["members"]}
    assert roles == {owner["id"]: "owner", invitee["id"]: "member"}
    assert detail.json()["invitations"] == []

    repeated = _accept_invitation(
        client, invitee_headers, team_id, invitation["id"]
    )
    assert repeated.status_code == 409, repeated.text


def test_invitation_decline_and_target_validation(client, seeded_db, admin_headers, db):
    owner_headers, owner = register_test_account(client, role="student")
    invitee_headers, invitee = register_test_account(client, role="faculty")
    team_id = _team(client, owner_headers).json()["id"]

    first = _invite(client, owner_headers, team_id, invitee["id"]).json()
    declined = _decline_invitation(
        client, invitee_headers, team_id, first["id"]
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"
    assert client.get(f"{TEAMS}/{team_id}", headers=invitee_headers).status_code == 404

    again = _invite(client, owner_headers, team_id, invitee["id"])
    assert again.status_code == 201, again.text

    assert _invite(client, owner_headers, team_id, owner["id"]).status_code == 422
    assert _invite(client, owner_headers, team_id, 987654).status_code == 404
    admin_id = client.get("/auth/me", headers=admin_headers).json()["id"]
    assert _invite(client, owner_headers, team_id, admin_id).status_code == 422

    _, inactive = register_test_account(client, role="student")
    db.get(User, inactive["id"]).is_active = False
    db.commit()
    assert _invite(client, owner_headers, team_id, inactive["id"]).status_code == 422

    member_headers, member = register_test_account(client, role="student")
    member_invite = _invite(client, owner_headers, team_id, member["id"]).json()
    assert _accept_invitation(
        client, member_headers, team_id, member_invite["id"]
    ).status_code == 200
    assert _invite(client, member_headers, team_id, invitee["id"]).status_code == 403


def test_membership_removal_and_leave(client, seeded_db):
    owner_headers, owner, member_headers, member, team_id = _team_with_member(client)
    outsider_headers, outsider = register_test_account(client, role="student")

    assert client.delete(
        f"{TEAMS}/{team_id}/members/{outsider['id']}", headers=owner_headers
    ).status_code == 404
    assert client.delete(
        f"{TEAMS}/{team_id}/members/{owner['id']}", headers=member_headers
    ).status_code == 403
    assert client.delete(
        f"{TEAMS}/{team_id}/members/{member['id']}", headers=outsider_headers
    ).status_code == 404
    assert client.delete(
        f"{TEAMS}/{team_id}/members/{owner['id']}", headers=owner_headers
    ).status_code == 409

    left = client.delete(
        f"{TEAMS}/{team_id}/members/{member['id']}", headers=member_headers
    )
    assert left.status_code == 200, left.text
    assert client.get(f"{TEAMS}/{team_id}", headers=member_headers).status_code == 404

    reinvited = _invite(client, owner_headers, team_id, member["id"])
    assert reinvited.status_code == 201
    assert _accept_invitation(
        client, member_headers, team_id, reinvited.json()["id"]
    ).status_code == 200

    removed = client.delete(
        f"{TEAMS}/{team_id}/members/{member['id']}", headers=owner_headers
    )
    assert removed.status_code == 200, removed.text
    assert client.get(f"{TEAMS}/{team_id}", headers=member_headers).status_code == 404


def test_team_deletion_is_owner_only_and_cascades(client, seeded_db, db):
    owner_headers, _, member_headers, member, team_id = _team_with_member(client)
    outsider_headers, _ = register_test_account(client, role="student")

    assert client.delete(f"{TEAMS}/{team_id}", headers=member_headers).status_code == 403
    assert client.delete(f"{TEAMS}/{team_id}", headers=outsider_headers).status_code == 404

    deleted = client.delete(f"{TEAMS}/{team_id}", headers=owner_headers)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"{TEAMS}/{team_id}", headers=owner_headers).status_code == 404
    assert db.query(ResearchTeamMember).count() == 0
    assert db.query(ResearchTeamInvitation).count() == 0


def test_team_recommendations_reuse_the_existing_engine(client, seeded_db, patch_semantic):
    owner_headers, _, member_headers, _, team_id = _team_with_member(client)
    recorded = patch_semantic(scores=[0.8, 0.5, 0.3])

    response = client.post(
        f"{TEAMS}/{team_id}/recommendations",
        json={"top_k": 2},
        headers=owner_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["team"]["id"] == team_id
    assert body["profile_used"]["research_areas"] == FOCUS["research_areas"]
    assert len(body["recommendations"]) == 2
    scores = [item["match_score"] for item in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    for item in body["recommendations"]:
        assert set(item["component_scores"]) == set(recommendation.EXPECTED_FEATURES)

    assert client.post(
        f"{TEAMS}/{team_id}/recommendations",
        json={},
        headers=member_headers,
    ).status_code == 200
    assert recorded["calls"] == 2


def test_team_recommendation_validation_and_failures(
    client, seeded_db, admin_headers, monkeypatch
):
    owner_headers, _ = register_test_account(client, role="student")
    blank = _team(
        client,
        owner_headers,
        focus={field: "" for field in FOCUS},
    ).json()
    assert client.post(
        f"{TEAMS}/{blank['id']}/recommendations", json={}, headers=owner_headers
    ).status_code == 400

    team_id = _team(client, owner_headers).json()["id"]
    outsider_headers, _ = register_test_account(client, role="student")
    assert client.post(
        f"{TEAMS}/{team_id}/recommendations", json={}, headers=outsider_headers
    ).status_code == 404
    assert client.post(
        f"{TEAMS}/{team_id}/recommendations", json={}, headers=admin_headers
    ).status_code == 404

    for top_k in (0, 11):
        assert client.post(
            f"{TEAMS}/{team_id}/recommendations",
            json={"top_k": top_k},
            headers=owner_headers,
        ).status_code == 422

    error = getattr(semantic_matching, "SemanticMatchingError")

    def broken(student_profile, researchers):
        raise error("embedding backend unavailable")

    monkeypatch.setattr(
        "app.services.recommendation.calculate_semantic_similarity", broken
    )
    failed = client.post(
        f"{TEAMS}/{team_id}/recommendations", json={}, headers=owner_headers
    )
    assert failed.status_code == 503
    assert failed.json()["detail"] == "Recommendation service unavailable"


def test_team_database_constraints(client, seeded_db, db):
    owner_headers, owner = register_test_account(client, role="student")
    team_id = _team(client, owner_headers).json()["id"]

    duplicate_member = ResearchTeamMember(
        team_id=team_id, user_id=owner["id"], role="owner", created_at=1
    )
    db.add(duplicate_member)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    invitee_headers, invitee = register_test_account(client, role="faculty")
    _invite(client, owner_headers, team_id, invitee["id"])
    duplicate_invitation = ResearchTeamInvitation(
        team_id=team_id,
        invited_user_id=invitee["id"],
        invited_by_user_id=owner["id"],
        status="pending",
        created_at=1,
        responded_at=None,
    )
    db.add(duplicate_invitation)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_teams_do_not_touch_auth_role_groups(client, seeded_db):
    owner_headers, owner = register_test_account(client, role="student")
    member_headers, member = register_test_account(client, role="faculty")

    session = SessionLocal()
    try:
        before = (
            session.query(Group).count(),
            session.query(GroupMembership).count(),
        )
        team_id = _team(client, owner_headers).json()["id"]
        invitation = _invite(client, owner_headers, team_id, member["id"]).json()
        assert _accept_invitation(
            client, member_headers, team_id, invitation["id"]
        ).status_code == 200
        after = (
            session.query(Group).count(),
            session.query(GroupMembership).count(),
        )
    finally:
        session.close()

    assert before == after
    detail = client.get(f"{TEAMS}/{team_id}", headers=owner_headers).json()
    assert {item["user_id"] for item in detail["members"]} == {
        owner["id"],
        member["id"],
    }
