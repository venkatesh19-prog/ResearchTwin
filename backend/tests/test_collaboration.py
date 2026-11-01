"""Collaboration request workflow (§6): ownership, roles, and decisions."""

import uuid

import pytest
from sqlalchemy.orm import Query

from app.database import SessionLocal, get_db
from app.models import CollaborationRequest, FacultyResearcherLink, User
from conftest import register_test_account

STUDENT_REQUESTS = "/students/me/collaboration-requests"
FACULTY_REQUESTS = "/faculty/me/collaboration-requests"
LINK = "/faculty/me/researcher-link"
ADMIN_LINK = "/admin/faculty/{faculty_user_id}/researcher-link"
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
def clean_collaboration_tables():
    """Directory records are recycled between tests, so links must be too."""
    session = SessionLocal()
    try:
        session.query(CollaborationRequest).delete()
        session.query(FacultyResearcherLink).delete()
        session.commit()
    finally:
        session.close()
    yield


def _student(client):
    headers, user = register_test_account(client, role="student")
    saved = client.put(
        "/students/me/profile",
        json={
            **{field: "" for field in PROFILE_FIELDS},
            "research_areas": "Machine Learning",
            "skills": "Python, PyTorch",
            "academic_details": "Final-year B.Tech CSE",
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    return headers, user


def _assign(client, admin_headers, faculty_user_id, researcher_id):
    return client.put(
        ADMIN_LINK.format(faculty_user_id=faculty_user_id),
        json={"researcher_id": researcher_id},
        headers=admin_headers,
    )


def _linked_faculty(client, admin_headers):
    headers, user = register_test_account(client, role="faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]
    linked = _assign(client, admin_headers, user["id"], researcher_id)
    assert linked.status_code == 200, linked.text
    return headers, researcher_id


def _create(client, headers, researcher_id, message="I would like to assist with your ML work."):
    return client.post(
        STUDENT_REQUESTS,
        json={"researcher_id": researcher_id, "message": message},
        headers=headers,
    )


def test_student_creates_a_pending_request(client, seeded_db):
    headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    response = _create(client, headers, researcher_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["researcher"]["name"] == "Dr. Ada Lovelace"
    assert body["faculty_response"] == ""
    assert body["reviewed_at"] is None


def test_request_requires_a_message(client, seeded_db):
    headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    assert _create(client, headers, researcher_id, message="   ").status_code == 422
    assert _create(client, headers, 987654).status_code == 404


def test_duplicate_pending_request_is_rejected(client, seeded_db):
    headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    assert _create(client, headers, researcher_id).status_code == 201
    second = _create(client, headers, researcher_id)

    assert second.status_code == 409
    assert "pending" in second.json()["detail"].lower()


def test_faculty_account_cannot_open_a_student_request(client, seeded_db):
    headers, _ = register_test_account(client, role="faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]

    assert _create(client, headers, researcher_id).status_code == 403


def test_students_only_see_their_own_requests(client, seeded_db):
    headers, _ = _student(client)
    other_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    _create(client, headers, researcher_id, message="Mine")

    listing = client.get(STUDENT_REQUESTS, headers=other_headers).json()["requests"]
    assert listing == []

    own = client.get(STUDENT_REQUESTS, headers=headers).json()["requests"]
    assert len(own) == 1
    assert own[0]["message"] == "Mine"


def test_anonymous_access_is_refused(client, seeded_db):
    assert client.get(STUDENT_REQUESTS).status_code == 401
    assert client.get(FACULTY_REQUESTS).status_code == 401
    assert client.get(LINK).status_code == 401
    assert client.put(LINK, json={"researcher_id": 1}).status_code == 401
    assert client.put(
        f"{FACULTY_REQUESTS}/1/decision", json={"decision": "accept"}
    ).status_code == 401


def test_faculty_must_link_a_directory_record(client, seeded_db):
    headers, _ = register_test_account(client, role="faculty")

    assert client.get(LINK, headers=headers).json() == {"linked": False, "researcher": None}

    listing = client.get(FACULTY_REQUESTS, headers=headers)
    assert listing.status_code == 400
    assert "admin" in listing.json()["detail"].lower()


@pytest.mark.parametrize("full_name", ["Unverified Faculty", "Dr. Ada Lovelace"])
def test_public_faculty_cannot_self_claim_even_by_name(client, seeded_db, full_name):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = _create(client, student_headers, researcher_id).json()
    signup = client.post(
        "/auth/register",
        json={
            "email": f"unverified-{uuid.uuid4().hex}@example.test",
            "password": "TestPassword123!",
            "full_name": full_name,
            "role": "faculty",
        },
    )
    assert signup.status_code == 201, signup.text
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    for target_id in (researcher_id, 987654):
        denied = client.put(LINK, json={"researcher_id": target_id}, headers=headers)
        assert denied.status_code == 403, denied.text
        assert "admin" in denied.json()["detail"].lower()
        assert "verif" in denied.json()["detail"].lower()
    assert client.get(LINK, headers=headers).json() == {"linked": False, "researcher": None}
    assert client.get(FACULTY_REQUESTS, headers=headers).status_code == 400
    decision = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "accept"},
        headers=headers,
    )
    assert decision.status_code == 400
    assert "admin" in decision.json()["detail"].lower()
    assert client.get(STUDENT_REQUESTS, headers=student_headers).json()["requests"][0] == created


@pytest.mark.parametrize("role, expected", [(None, 401), ("student", 403), ("faculty", 403)])
def test_only_admin_can_assign_faculty(client, seeded_db, role, expected):
    faculty_headers, faculty = register_test_account(client, role="faculty")
    headers = {}
    if role == "faculty":
        headers = faculty_headers
    elif role:
        headers, _ = register_test_account(client, role=role)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    denied = _assign(client, headers, faculty["id"], researcher_id)

    assert denied.status_code == expected, denied.text
    assert client.get(LINK, headers=faculty_headers).json()["linked"] is False


@pytest.mark.parametrize("target", ["unknown", "inactive", "student", "admin"])
def test_admin_assignment_requires_active_faculty(client, seeded_db, admin_headers, db, target):
    researcher_id = client.get("/researchers/").json()[0]["id"]
    if target == "unknown":
        faculty_id = 987654
    elif target == "admin":
        faculty_id = client.get("/auth/me", headers=admin_headers).json()["id"]
    else:
        _, user = register_test_account(client, role="faculty" if target == "inactive" else "student")
        faculty_id = user["id"]
        if target == "inactive":
            db.get(User, faculty_id).is_active = False
            db.commit()

    response = _assign(client, admin_headers, faculty_id, researcher_id)

    assert response.status_code == (404 if target == "unknown" else 422), response.text
    assert db.query(FacultyResearcherLink).count() == 0


def test_admin_assignment_requires_a_real_researcher(client, seeded_db, admin_headers):
    headers, faculty = register_test_account(client, role="faculty")

    missing = _assign(client, admin_headers, faculty["id"], 987654)

    assert missing.status_code == 404, missing.text
    assert "researcher" in missing.json()["detail"].lower()
    assert client.get(LINK, headers=headers).json()["linked"] is False


def test_admin_assignment_and_same_link_confirmation_are_idempotent(client, seeded_db, admin_headers, db):
    headers, faculty = register_test_account(client, role="faculty")
    researcher_id = client.get("/researchers/").json()[0]["id"]
    assigned = _assign(client, admin_headers, faculty["id"], researcher_id)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["linked"] is True
    assert assigned.json()["researcher"]["id"] == researcher_id
    link = db.query(FacultyResearcherLink).one()
    original = (link.id, link.faculty_user_id, link.researcher_id, link.created_at)

    repeated = _assign(client, admin_headers, faculty["id"], researcher_id)
    confirmed = client.put(LINK, json={"researcher_id": researcher_id}, headers=headers)

    assert repeated.status_code == confirmed.status_code == 200
    assert repeated.json() == confirmed.json() == assigned.json()
    assert client.get(LINK, headers=headers).json() == assigned.json()
    db.expire_all()
    link = db.query(FacultyResearcherLink).one()
    assert (link.id, link.faculty_user_id, link.researcher_id, link.created_at) == original


def test_admin_cannot_reassign_faculty_or_claim_another_accounts_record(client, seeded_db, admin_headers, db):
    headers, faculty = register_test_account(client, role="faculty")
    other_headers, other = register_test_account(client, role="faculty")
    researchers = client.get("/researchers/").json()
    researcher_id, different_id = [row["id"] for row in researchers[:2]]
    assert _assign(client, admin_headers, faculty["id"], researcher_id).status_code == 200

    taken = _assign(client, admin_headers, other["id"], researcher_id)
    switched = _assign(client, admin_headers, faculty["id"], different_id)

    assert taken.status_code == 409, taken.text
    assert switched.status_code == 409, switched.text
    assert client.get(LINK, headers=headers).json()["researcher"]["id"] == researcher_id
    assert client.get(LINK, headers=other_headers).json()["linked"] is False
    assert db.query(FacultyResearcherLink).count() == 1


@pytest.mark.parametrize("conflict", ["faculty", "researcher"])
def test_assignment_integrity_race_returns_409_and_rolls_back(
    client, seeded_db, admin_headers, db, app_instance, monkeypatch, conflict
):
    _, faculty = register_test_account(client, role="faculty")
    _, other = register_test_account(client, role="faculty")
    researcher_id, different_id = [row["id"] for row in client.get("/researchers/").json()[:2]]
    assert _assign(client, admin_headers, faculty["id"], researcher_id).status_code == 200
    target_id = faculty["id"] if conflict == "faculty" else other["id"]
    target_record = different_id if conflict == "faculty" else researcher_id
    original_first = Query.first

    def stale_link_lookup(query):
        # Simulate prechecks that ran before the winning assignment committed.
        # The INSERT still hits the real database's unique constraints.
        if query.session is db and query.column_descriptions[0]["entity"] is FacultyResearcherLink:
            return None
        return original_first(query)

    with monkeypatch.context() as patch:
        patch.setitem(app_instance.dependency_overrides, get_db, lambda: db)
        patch.setattr(Query, "first", stale_link_lookup)
        response = _assign(client, admin_headers, target_id, target_record)

    assert response.status_code == 409, response.text
    # Querying this same session would fail if IntegrityError was not rolled back.
    link = db.query(FacultyResearcherLink).one()
    assert (link.faculty_user_id, link.researcher_id) == (faculty["id"], researcher_id)


def test_linked_faculty_cannot_switch_records(client, seeded_db, admin_headers):
    headers, researcher_id = _linked_faculty(client, admin_headers)
    other_headers, other = register_test_account(client, role="faculty")
    researchers = client.get("/researchers/").json()
    assert _assign(client, admin_headers, other["id"], researchers[1]["id"]).status_code == 200

    for target_id in (researchers[1]["id"], researchers[2]["id"], 987654):
        denied = client.put(LINK, json={"researcher_id": target_id}, headers=headers)
        assert denied.status_code == 403, denied.text
        assert "admin" in denied.json()["detail"].lower()
        assert "verif" in denied.json()["detail"].lower()
    assert client.get(LINK, headers=headers).json()["researcher"]["id"] == researcher_id
    assert client.get(LINK, headers=other_headers).json()["researcher"]["id"] == researchers[1]["id"]


def test_researcher_link_route_status_matrix(client, seeded_db, admin_headers):
    """One table of every caller class against the faculty-only link route."""
    researcher_id, different_id = [row["id"] for row in client.get("/researchers/").json()[:2]]
    student_headers, _ = register_test_account(client, role="student")
    unlinked_headers, unlinked = register_test_account(client, role="faculty")
    linked_headers, linked_id = _linked_faculty(client, admin_headers)
    assert linked_id == researcher_id

    anonymous = client.put(LINK, json={"researcher_id": researcher_id})
    student = client.put(LINK, json={"researcher_id": researcher_id}, headers=student_headers)
    unlinked_claim = client.put(LINK, json={"researcher_id": researcher_id}, headers=unlinked_headers)
    switch = client.put(LINK, json={"researcher_id": different_id}, headers=linked_headers)
    invented = client.put(LINK, json={"researcher_id": 987654}, headers=linked_headers)
    confirmation = client.put(LINK, json={"researcher_id": researcher_id}, headers=linked_headers)

    assert anonymous.status_code == 401, anonymous.text
    assert student.status_code == 403, student.text
    for denied in (unlinked_claim, switch, invented):
        assert denied.status_code == 403, denied.text
        assert "admin" in denied.json()["detail"].lower()
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json() == client.get(LINK, headers=linked_headers).json()

    # Denials must not disturb links, and administrator assignment still works.
    assert client.get(LINK, headers=unlinked_headers).json() == {"linked": False, "researcher": None}
    assigned = _assign(client, admin_headers, unlinked["id"], different_id)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["researcher"]["id"] == different_id


def test_verified_link_keeps_working_after_faculty_profile_save(
    client, seeded_db, admin_headers
):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = _create(client, student_headers, researcher_id, message="Still reachable.").json()
    directory_skills = client.get(f"/researchers/{researcher_id}").json()["skills"]

    faculty_headers, _ = _linked_faculty(client, admin_headers)
    saved = client.put(
        "/faculty/me/profile", json={"skills": "Python, Rust"}, headers=faculty_headers
    )
    assert saved.status_code == 200, saved.text

    listing = client.get(FACULTY_REQUESTS, headers=faculty_headers)
    assert listing.status_code == 200, listing.text
    assert [record["id"] for record in listing.json()["requests"]] == [created["id"]]

    decision = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "accept", "response": "Send your CV."},
        headers=faculty_headers,
    )
    assert decision.status_code == 200, decision.text
    assert client.get(f"/researchers/{researcher_id}").json()["skills"] == directory_skills


def test_linked_faculty_sees_the_request_and_student_profile(client, seeded_db, admin_headers):
    student_headers, student = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    _create(client, student_headers, researcher_id, message="Happy to help on NLP.")

    faculty_headers, _ = _linked_faculty(client, admin_headers)
    body = client.get(FACULTY_REQUESTS, headers=faculty_headers).json()

    assert len(body["requests"]) == 1
    record = body["requests"][0]
    assert record["message"] == "Happy to help on NLP."
    assert record["student"]["full_name"] == "Test Student"
    assert record["student"]["skills"] == "Python, PyTorch"
    assert record["student"]["academic_details"] == "Final-year B.Tech CSE"
    assert "email" not in record["student"]


def test_faculty_only_sees_requests_for_their_own_record(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    researchers = client.get("/researchers/").json()
    mine = researchers[0]["id"]
    theirs = researchers[1]["id"]

    _create(client, student_headers, mine)
    _create(client, student_headers, theirs, message="Different researcher.")

    faculty_headers, linked_id = _linked_faculty(client, admin_headers)
    body = client.get(FACULTY_REQUESTS, headers=faculty_headers).json()

    assert linked_id == mine
    assert [record["researcher_id"] for record in body["requests"]] == [mine]


def test_faculty_accepts_with_an_optional_response(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = _create(client, student_headers, researcher_id).json()

    faculty_headers, _ = _linked_faculty(client, admin_headers)
    decision = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "accept", "response": "Yes — send your CV."},
        headers=faculty_headers,
    )

    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "accepted"
    assert decision.json()["faculty_response"] == "Yes — send your CV."
    assert decision.json()["reviewed_at"]

    student_view = client.get(STUDENT_REQUESTS, headers=student_headers).json()["requests"][0]
    assert student_view["status"] == "accepted"
    assert student_view["faculty_response"] == "Yes — send your CV."


def test_faculty_rejects_without_a_response(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = _create(client, student_headers, researcher_id).json()

    faculty_headers, _ = _linked_faculty(client, admin_headers)
    decision = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "reject"},
        headers=faculty_headers,
    )

    assert decision.status_code == 200
    assert decision.json()["status"] == "rejected"
    assert decision.json()["faculty_response"] == ""


def test_faculty_cannot_answer_a_request_for_another_record(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    other_researcher_id = client.get("/researchers/").json()[1]["id"]
    foreign = _create(client, student_headers, other_researcher_id).json()

    faculty_headers, linked_id = _linked_faculty(client, admin_headers)
    assert linked_id != other_researcher_id

    denied = client.put(
        f"{FACULTY_REQUESTS}/{foreign['id']}/decision",
        json={"decision": "accept", "response": "Not mine to answer."},
        headers=faculty_headers,
    )
    assert denied.status_code == 403

    unchanged = client.get(STUDENT_REQUESTS, headers=student_headers).json()["requests"][0]
    assert unchanged["status"] == "pending"


def test_decision_requires_a_known_request(client, seeded_db, admin_headers):
    faculty_headers, _ = _linked_faculty(client, admin_headers)
    missing = client.put(
        f"{FACULTY_REQUESTS}/987654/decision",
        json={"decision": "accept"},
        headers=faculty_headers,
    )
    assert missing.status_code == 404


def test_student_cannot_decide_a_request(client, seeded_db):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = _create(client, student_headers, researcher_id).json()

    response = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "accept"},
        headers=student_headers,
    )
    assert response.status_code == 403


def test_invalid_decision_is_rejected(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    created = _create(client, student_headers, researcher_id).json()

    faculty_headers, _ = _linked_faculty(client, admin_headers)
    response = client.put(
        f"{FACULTY_REQUESTS}/{created['id']}/decision",
        json={"decision": "maybe"},
        headers=faculty_headers,
    )
    assert response.status_code == 422


def test_faculty_status_filter(client, seeded_db, admin_headers):
    student_headers, _ = _student(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    pending = _create(client, student_headers, researcher_id).json()

    faculty_headers, _ = _linked_faculty(client, admin_headers)
    client.put(
        f"{FACULTY_REQUESTS}/{pending['id']}/decision",
        json={"decision": "reject"},
        headers=faculty_headers,
    )

    assert client.get(
        f"{FACULTY_REQUESTS}?status=pending", headers=faculty_headers
    ).json()["requests"] == []
    assert len(client.get(
        f"{FACULTY_REQUESTS}?status=rejected", headers=faculty_headers
    ).json()["requests"]) == 1
    assert client.get(
        f"{FACULTY_REQUESTS}?status=accepted", headers=faculty_headers
    ).json()["requests"] == []


@pytest.mark.parametrize("first, expected", [("accept", "accepted"), ("reject", "rejected")])
@pytest.mark.parametrize("repeat", ["accept", "reject"])
def test_reviewed_request_cannot_be_decided_again(
    client, seeded_db, admin_headers, first, expected, repeat
):
    student_headers, _ = _student(client)
    faculty_headers, researcher_id = _linked_faculty(client, admin_headers)
    created = _create(client, student_headers, researcher_id).json()
    endpoint = f"{FACULTY_REQUESTS}/{created['id']}/decision"
    original = client.put(
        endpoint, json={"decision": first, "response": "Original response"}, headers=faculty_headers
    )
    assert original.status_code == 200, original.text
    assert original.json()["status"] == expected

    repeated = client.put(
        endpoint, json={"decision": repeat, "response": "Overwrite"}, headers=faculty_headers
    )

    assert repeated.status_code == 409, repeated.text
    assert client.get(STUDENT_REQUESTS, headers=student_headers).json()["requests"][0] == original.json()


@pytest.mark.parametrize("first, repeat", [("accept", "reject"), ("reject", "accept")])
def test_stale_pending_decision_cannot_overwrite_concurrent_review(
    client, seeded_db, admin_headers, app_instance, monkeypatch, first, repeat
):
    student_headers, _ = _student(client)
    faculty_headers, researcher_id = _linked_faculty(client, admin_headers)
    created = _create(client, student_headers, researcher_id).json()
    endpoint = f"{FACULTY_REQUESTS}/{created['id']}/decision"
    with SessionLocal() as stale_db:
        # Keep a pending ORM snapshot while another request commits its decision.
        stale_record = stale_db.get(CollaborationRequest, created["id"])
        original = client.put(
            endpoint, json={"decision": first, "response": "First reviewer"}, headers=faculty_headers
        )
        assert original.status_code == 200, original.text
        assert stale_record.status == "pending"
        with monkeypatch.context() as patch:
            patch.setitem(app_instance.dependency_overrides, get_db, lambda: stale_db)
            stale_decision = client.put(
                endpoint, json={"decision": repeat, "response": "Stale reviewer"}, headers=faculty_headers
            )

        assert stale_decision.status_code == 409, stale_decision.text
        stale_db.refresh(stale_record)
        assert stale_record.status == original.json()["status"]
        assert stale_record.faculty_response == "First reviewer"
    assert client.get(STUDENT_REQUESTS, headers=student_headers).json()["requests"][0] == original.json()


@pytest.mark.parametrize("status", ["unknown", "accept", ""])
def test_unknown_inbox_status_is_rejected(client, seeded_db, admin_headers, status):
    headers, _ = _linked_faculty(client, admin_headers)

    response = client.get(FACULTY_REQUESTS, params={"status": status}, headers=headers)

    assert response.status_code == 422, response.text
