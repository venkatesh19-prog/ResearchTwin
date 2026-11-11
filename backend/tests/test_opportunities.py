"""Research opportunities and funding discovery.

These tests cover the shared opportunity subsystem: faculty/admin creation,
public search and filtering, eligibility evaluation from the saved student
profile, transparent matching, application tracking, and the optional
external funding adapter. They also assert that the subsystem stays separate
from research teams and auth role groups.
"""

import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    Group,
    GroupMembership,
    Opportunity,
    OpportunityApplication,
    ResearchTeam,
    ResearchTeamMember,
    Researcher,
    FacultyResearcherLink,
)
from app.services import funding_sources, recommendation
from conftest import register_test_account

BASE = "/opportunities"
APPLICATIONS = "/students/me/opportunity-applications"
MATCHES = "/students/me/opportunity-matches"

PROFILE = {
    "research_areas": "Artificial Intelligence, Machine Learning",
    "expertise": "Deep Learning, NLP",
    "skills": "Python, PyTorch",
    "projects": "Semantic search engine",
    "publications": "Transformer models",
}


@pytest.fixture(autouse=True)
def clean_opportunity_tables():
    session = SessionLocal()
    try:
        session.query(OpportunityApplication).delete()
        session.query(Opportunity).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.query(OpportunityApplication).delete()
        session.query(Opportunity).delete()
        session.commit()
    finally:
        session.close()


def _researcher(db, name="Dr. Ada Lovelace"):
    return db.query(Researcher).filter(Researcher.name == name).one()


def _faculty_with_link(client, db, researcher_id):
    headers, user = register_test_account(client, role="faculty")
    db.add(
        FacultyResearcherLink(
            faculty_user_id=user["id"],
            researcher_id=researcher_id,
            created_at=int(time.time()),
        )
    )
    db.commit()
    return headers, user


def _create(client, headers, **overrides):
    payload = {
        "category": "research",
        "title": "LLM Research Assistant",
        "description": "Work on transformer models and retrieval.",
        "organization": "AI Lab",
        "required_skills": "Python, PyTorch",
        "required_research_areas": "Artificial Intelligence, Machine Learning",
        "required_expertise": "Deep Learning, NLP",
        "status": "open",
    }
    payload.update(overrides)
    return client.post(BASE, json=payload, headers=headers)


def _save_profile(client, headers, **overrides):
    payload = dict(PROFILE)
    payload.update(overrides)
    response = client.put("/students/me/profile", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response


def _apply(client, headers, opportunity_id, message="I would like to contribute."):
    return client.post(
        f"{BASE}/{opportunity_id}/applications",
        json={"message": message},
        headers=headers,
    )


def _applications(client, headers, opportunity_id):
    return client.get(
        f"{BASE}/{opportunity_id}/applications", headers=headers
    )


def _decision(client, headers, opportunity_id, application_id, decision="accept"):
    return client.put(
        f"{BASE}/{opportunity_id}/applications/{application_id}",
        json={"decision": decision, "note": "Reviewed."},
        headers=headers,
    )


def test_opportunity_creation_permissions_and_validation(
    client, seeded_db, admin_headers, db
):
    researcher = _researcher(db)
    assert client.post(BASE, json={"category": "research", "title": "Anonymous"}).status_code == 401

    student_headers, _ = register_test_account(client, role="student")
    assert _create(client, student_headers).status_code == 403
    assert client.post(
        BASE,
        json={"category": "funding", "title": "Student grant"},
        headers=student_headers,
    ).status_code == 403

    unlinked_headers, _ = register_test_account(client, role="faculty")
    assert _create(client, unlinked_headers).status_code == 403

    faculty_headers, faculty = _faculty_with_link(client, db, researcher.id)
    created = _create(client, faculty_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["researcher_id"] == researcher.id
    assert body["created_by_user_id"] == faculty["id"]
    assert body["category"] == "research"
    assert body["status"] == "open"
    assert body["is_open"] is True
    assert body["deadline_passed"] is False

    wrong_link = _create(
        client,
        faculty_headers,
        researcher_id=_researcher(db, "Dr. Alan Turing").id,
    )
    assert wrong_link.status_code == 422, wrong_link.text

    funding_by_faculty = _create(client, faculty_headers, category="funding")
    assert funding_by_faculty.status_code == 403, funding_by_faculty.text

    funding = _create(client, admin_headers, category="funding", title="AI Travel Grant")
    assert funding.status_code == 201, funding.text
    assert funding.json()["researcher_id"] is None

    admin_research = _create(
        client, admin_headers, title="Institutional Research Call", researcher_id=None
    )
    assert admin_research.status_code == 201, admin_research.text
    assert admin_research.json()["researcher_id"] is None

    linked_admin_research = _create(
        client, admin_headers, title="Linked Call", researcher_id=researcher.id
    )
    assert linked_admin_research.status_code == 201
    assert linked_admin_research.json()["researcher_id"] == researcher.id

    assert _create(client, admin_headers, title="Unknown", researcher_id=987654).status_code == 404
    assert _create(client, admin_headers, title="   ").status_code == 422
    assert _create(client, admin_headers, title="Bad URL", url="ftp://example.com").status_code == 422
    assert _create(client, admin_headers, title="Bad status", status="archived").status_code == 422
    assert _create(client, admin_headers, title="Extra", unknown_field=True).status_code == 422
    assert _create(client, admin_headers, title="Bad deadline", deadline_at=-1).status_code == 422


def test_opportunity_search_filters_and_pagination(
    client, seeded_db, admin_headers, db
):
    researcher = _researcher(db)
    now = int(time.time())
    vision = _create(
        client,
        admin_headers,
        title="Vision Models",
        description="Computer vision research.",
        researcher_id=researcher.id,
        required_skills="",
    )
    funding_soon = _create(
        client,
        admin_headers,
        category="funding",
        title="AI Travel Grant",
        description="Travel support for AI conferences.",
        organization="NSF",
        deadline_at=now + 1000,
        required_skills="",
    )
    funding_closed = _create(
        client,
        admin_headers,
        category="funding",
        title="AI Equipment Grant",
        description="Equipment support.",
        organization="University",
        deadline_at=now + 5000,
        required_skills="",
        status="closed",
    )
    draft = _create(
        client,
        admin_headers,
        title="Secret Draft",
        description="Not published yet.",
        status="draft",
    )
    expired = _create(
        client,
        admin_headers,
        title="Expired Call",
        description="Past deadline.",
        deadline_at=now - 60,
        required_skills="",
    )

    listed = client.get(BASE)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 4
    titles = {item["title"] for item in body["opportunities"]}
    assert titles == {"Vision Models", "AI Travel Grant", "AI Equipment Grant", "Expired Call"}
    assert "Secret Draft" not in titles

    expired_payload = next(
        item for item in body["opportunities"] if item["title"] == "Expired Call"
    )
    assert expired_payload["deadline_passed"] is True
    assert expired_payload["is_open"] is False

    funding = client.get(BASE, params={"category": "funding"}).json()
    assert funding["total"] == 2

    by_text = client.get(BASE, params={"q": "equipment"}).json()
    assert [item["title"] for item in by_text["opportunities"]] == ["AI Equipment Grant"]

    closed = client.get(BASE, params={"status": "closed"}).json()
    assert [item["title"] for item in closed["opportunities"]] == ["AI Equipment Grant"]

    before = client.get(BASE, params={"deadline_before": now + 2000}).json()
    assert {item["title"] for item in before["opportunities"]} == {
        "AI Travel Grant",
        "Expired Call",
    }
    after = client.get(BASE, params={"deadline_after": now + 2000}).json()
    assert [item["title"] for item in after["opportunities"]] == ["AI Equipment Grant"]

    by_researcher = client.get(BASE, params={"researcher_id": researcher.id}).json()
    assert [item["title"] for item in by_researcher["opportunities"]] == ["Vision Models"]

    page = client.get(BASE, params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 4
    assert len(page["opportunities"]) == 1
    assert page["limit"] == 1 and page["offset"] == 1

    assert client.get(BASE, params={"limit": 0}).status_code == 422
    assert client.get(BASE, params={"offset": -1}).status_code == 422
    assert client.get(BASE, params={"status": "draft"}).status_code == 422

    student_headers, _ = register_test_account(client, role="student")
    assert client.get(f"{BASE}/{draft.json()['id']}").status_code == 404
    assert client.get(f"{BASE}/{draft.json()['id']}", headers=student_headers).status_code == 404
    assert client.get(f"{BASE}/{draft.json()['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{BASE}/{vision.json()['id']}").status_code == 200
    assert client.get(f"{BASE}/987654").status_code == 404

    mine = client.get(f"{BASE}/mine", headers=admin_headers)
    assert mine.status_code == 200
    assert mine.json()["total"] == 5
    assert {item["title"] for item in mine.json()["opportunities"]} >= {"Secret Draft"}


def test_opportunity_update_delete_permissions(
    client, seeded_db, admin_headers, db
):
    researcher = _researcher(db)
    owner_headers, owner = _faculty_with_link(client, db, researcher.id)
    other_headers, _ = _faculty_with_link(
        client, db, _researcher(db, "Dr. Alan Turing").id
    )
    opportunity = _create(client, owner_headers).json()
    student_headers, student = register_test_account(client, role="student")
    applied = _apply(client, student_headers, opportunity["id"])
    assert applied.status_code == 201, applied.text

    assert client.put(
        f"{BASE}/{opportunity['id']}",
        json={"title": "Hijacked"},
        headers=other_headers,
    ).status_code == 403
    assert client.put(
        f"{BASE}/{opportunity['id']}",
        json={"title": "Hijacked"},
        headers=student_headers,
    ).status_code == 403
    assert client.delete(
        f"{BASE}/{opportunity['id']}", headers=other_headers
    ).status_code == 403
    assert client.delete(
        f"{BASE}/{opportunity['id']}", headers=student_headers
    ).status_code == 403

    updated = client.put(
        f"{BASE}/{opportunity['id']}",
        json={"title": "Updated Call", "status": "closed", "deadline_at": None},
        headers=owner_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Updated Call"
    assert updated.json()["status"] == "closed"
    assert updated.json()["deadline_at"] is None
    assert updated.json()["is_open"] is False

    assert client.put(
        f"{BASE}/{opportunity['id']}",
        json={"title": "   "},
        headers=owner_headers,
    ).status_code == 422
    assert client.put(
        f"{BASE}/{opportunity['id']}",
        json={"category": "funding"},
        headers=owner_headers,
    ).status_code == 422

    admin_update = client.put(
        f"{BASE}/{opportunity['id']}",
        json={"organization": "Institutional Office"},
        headers=admin_headers,
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["organization"] == "Institutional Office"

    deleted = client.delete(f"{BASE}/{opportunity['id']}", headers=owner_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert client.get(f"{BASE}/{opportunity['id']}", headers=owner_headers).status_code == 404
    assert db.query(OpportunityApplication).filter(
        OpportunityApplication.student_user_id == student["id"]
    ).count() == 0


def test_eligibility_uses_saved_profile_and_never_invents_gaps(
    client, seeded_db, admin_headers
):
    student_headers, _ = register_test_account(client, role="student")
    opportunity = _create(
        client, admin_headers, required_skills="Python, SQL"
    ).json()
    endpoint = f"{BASE}/{opportunity['id']}/eligibility"

    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=student_headers).status_code == 400

    _save_profile(client, student_headers)
    eligible = client.get(endpoint, headers=student_headers)
    assert eligible.status_code == 200, eligible.text
    body = eligible.json()
    assert body["eligible"] is False
    assert body["profile_ready"] is True
    assert body["student_skills_provided"] is True
    assert body["matched_skills"] == ["python"]
    assert body["missing_skills"] == ["sql"]
    assert body["reasons"]

    no_skills = _create(
        client, admin_headers, title="No skill requirement", required_skills=""
    ).json()
    open_body = client.get(
        f"{BASE}/{no_skills['id']}/eligibility", headers=student_headers
    ).json()
    assert open_body["eligible"] is True
    assert open_body["matched_skills"] == []
    assert open_body["missing_skills"] == []

    closed = _create(
        client, admin_headers, title="Closed call", status="closed"
    ).json()
    closed_body = client.get(
        f"{BASE}/{closed['id']}/eligibility", headers=student_headers
    ).json()
    assert closed_body["eligible"] is False

    expired = _create(
        client,
        admin_headers,
        title="Expired call",
        deadline_at=int(time.time()) - 60,
    ).json()
    expired_body = client.get(
        f"{BASE}/{expired['id']}/eligibility", headers=student_headers
    ).json()
    assert expired_body["eligible"] is False
    assert expired_body["deadline_passed"] is True

    blank_headers, _ = register_test_account(client, role="student")
    _save_profile(
        client,
        blank_headers,
        skills="",
        research_areas="",
        expertise="",
        projects="",
        publications="",
    )
    blank = client.get(endpoint, headers=blank_headers)
    assert blank.status_code == 200, blank.text
    assert blank.json()["eligible"] is None
    assert blank.json()["student_skills_provided"] is False
    assert blank.json()["profile_ready"] is False
    assert blank.json()["matched_skills"] == []
    assert blank.json()["missing_skills"] == []

    listing = client.get(
        BASE, params={"eligible_only": "true"}, headers=student_headers
    )
    assert listing.status_code == 200, listing.text
    ids = {item["id"] for item in listing.json()["opportunities"]}
    assert no_skills["id"] in ids
    assert opportunity["id"] not in ids
    assert closed["id"] not in ids
    assert expired["id"] not in ids

    assert client.get(BASE, params={"eligible_only": "true"}).status_code == 401
    assert client.get(
        BASE, params={"eligible_only": "true"}, headers=blank_headers
    ).status_code == 400


def test_opportunity_matching_is_transparent_and_omits_no_signal(
    client, seeded_db, admin_headers
):
    student_headers, _ = register_test_account(client, role="student")
    assert client.post(MATCHES, json={}, headers=student_headers).status_code == 400
    _save_profile(
        client,
        student_headers,
        skills="",
        research_areas="",
        expertise="",
        projects="",
        publications="",
    )
    assert client.post(MATCHES, json={}, headers=student_headers).status_code == 400
    _save_profile(client, student_headers)

    relevant = _create(client, admin_headers, title="Transformer Retrieval Assistant").json()
    unrelated = _create(
        client,
        admin_headers,
        title="Marine Biology Field Survey",
        description="Coastal ecology and coral sampling.",
        required_skills="Welding, Scuba",
        required_research_areas="Marine Biology",
        required_expertise="Coral Ecology",
    ).json()
    _create(client, admin_headers, title="Closed AI Call", status="closed")
    _create(
        client,
        admin_headers,
        title="Expired AI Call",
        deadline_at=int(time.time()) - 60,
    )

    response = client.post(MATCHES, json={"top_k": 5}, headers=student_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "transparent_similarity_v1"
    assert body["profile_used"]["research_areas"] == PROFILE["research_areas"]
    titles = [item["opportunity"]["title"] for item in body["matches"]]
    assert titles == ["Transformer Retrieval Assistant"]
    assert unrelated["title"] not in titles
    match = body["matches"][0]
    assert 0 < match["match_score"] <= 1
    assert set(match["signals"]) <= {
        "research_area_similarity",
        "expertise_similarity",
        "skill_overlap",
        "text_similarity",
    }
    assert "component_scores" not in match
    assert match["eligibility"]["eligible"] is True
    assert recommendation.EXPECTED_FEATURES == (
        "tfidf_similarity",
        "semantic_similarity",
        "research_area_similarity",
        "expertise_similarity",
        "skill_overlap",
        "project_similarity",
        "publication_similarity",
    )

    assert client.post(MATCHES, json={}).status_code == 401
    for top_k in (0, 21):
        assert client.post(
            MATCHES, json={"top_k": top_k}, headers=student_headers
        ).status_code == 422

    partial = _create(
        client,
        admin_headers,
        title="Transformer SQL Assistant",
        required_skills="Python, SQL",
    )
    assert partial.status_code == 201, partial.text
    matched_titles = {
        item["opportunity"]["title"]
        for item in client.post(
            MATCHES, json={"top_k": 5}, headers=student_headers
        ).json()["matches"]
    }
    assert matched_titles == {
        "Transformer Retrieval Assistant",
        "Transformer SQL Assistant",
    }
    eligible_titles = [
        item["opportunity"]["title"]
        for item in client.post(
            MATCHES,
            json={"top_k": 5, "eligible_only": True},
            headers=student_headers,
        ).json()["matches"]
    ]
    assert eligible_titles == ["Transformer Retrieval Assistant"]

    empty = client.post(
        MATCHES,
        json={"category": "funding"},
        headers=student_headers,
    )
    assert empty.status_code == 200
    assert empty.json()["matches"] == []


def test_application_lifecycle_and_duplicate_pending(
    client, seeded_db, admin_headers, db
):
    opportunity = _create(client, admin_headers).json()
    student_one_headers, student_one = register_test_account(client, role="student")
    student_two_headers, student_two = register_test_account(client, role="student")
    outsider_headers, _ = register_test_account(client, role="student")

    first = _apply(client, student_one_headers, opportunity["id"])
    assert first.status_code == 201, first.text
    application = first.json()
    assert application["status"] == "pending"
    assert application["student_user_id"] == student_one["id"]
    assert application["decision_note"] == ""
    assert application["reviewed_at"] is None

    duplicate = _apply(client, student_one_headers, opportunity["id"])
    assert duplicate.status_code == 409, duplicate.text
    assert _apply(client, student_one_headers, opportunity["id"], message="").status_code == 422

    second = _apply(client, student_two_headers, opportunity["id"])
    assert second.status_code == 201

    mine = client.get(APPLICATIONS, headers=student_one_headers)
    assert mine.status_code == 200
    assert mine.json()["total"] == 1
    assert mine.json()["applications"][0]["opportunity"]["id"] == opportunity["id"]

    assert _applications(client, outsider_headers, opportunity["id"]).status_code == 403
    assert _applications(client, student_one_headers, opportunity["id"]).status_code == 403

    manager_view = _applications(client, admin_headers, opportunity["id"])
    assert manager_view.status_code == 200, manager_view.text
    assert manager_view.json()["total"] == 2
    emails = {item["student_email"] for item in manager_view.json()["applications"]}
    assert emails == {student_one["email"], student_two["email"]}

    assert client.put(
        f"{BASE}/{opportunity['id']}/applications/{application['id']}",
        json={"decision": "maybe"},
        headers=admin_headers,
    ).status_code == 422

    accepted = _decision(
        client, admin_headers, opportunity["id"], application["id"], "accept"
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["reviewed_at"] is not None
    assert accepted.json()["decision_note"] == "Reviewed."

    assert _apply(client, student_one_headers, opportunity["id"]).status_code == 409
    repeated = _decision(
        client, admin_headers, opportunity["id"], application["id"], "reject"
    )
    assert repeated.status_code == 409

    withdrawn = client.delete(
        f"{BASE}/{opportunity['id']}/applications/me", headers=student_two_headers
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["withdrawn"] is True
    assert withdrawn.json()["application"]["status"] == "withdrawn"

    assert client.delete(
        f"{BASE}/{opportunity['id']}/applications/me", headers=student_two_headers
    ).status_code == 404
    assert client.delete(
        f"{BASE}/{opportunity['id']}/applications/me", headers=student_one_headers
    ).status_code == 409

    reapplied = _apply(client, student_two_headers, opportunity["id"], message="Trying again.")
    assert reapplied.status_code == 201, reapplied.text
    rejected = _decision(
        client, admin_headers, opportunity["id"], reapplied.json()["id"], "reject"
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert _apply(client, student_two_headers, opportunity["id"]).status_code == 409

    actions = {
        event.action
        for event in db.query(AuditEvent)
        .filter(AuditEvent.target_type == "opportunity")
        .all()
    }
    assert {"opportunity.apply", "opportunity.decide", "opportunity.withdraw"} <= actions


def test_application_rejects_drafts_closed_and_expired(
    client, seeded_db, admin_headers
):
    student_headers, _ = register_test_account(client, role="student")
    draft = _create(client, admin_headers, title="Draft", status="draft").json()
    closed = _create(client, admin_headers, title="Closed", status="closed").json()
    expired = _create(
        client,
        admin_headers,
        title="Expired",
        deadline_at=int(time.time()) - 60,
    ).json()

    assert _apply(client, student_headers, draft["id"]).status_code == 404
    assert _apply(client, student_headers, closed["id"]).status_code == 409
    assert _apply(client, student_headers, expired["id"]).status_code == 409
    assert _apply(client, student_headers, 987654).status_code == 404
    assert client.post(
        f"{BASE}/{expired['id']}/applications", json={"message": "No auth"}
    ).status_code == 401


def test_linked_faculty_can_manage_applications_for_their_researcher(
    client, seeded_db, admin_headers, db
):
    researcher = _researcher(db)
    linked_headers, linked = _faculty_with_link(client, db, researcher.id)
    other_headers, _ = _faculty_with_link(
        client, db, _researcher(db, "Dr. Grace Hopper").id
    )
    opportunity = _create(
        client, admin_headers, researcher_id=researcher.id, title="Linked Call"
    ).json()
    student_headers, _ = register_test_account(client, role="student")
    applied = _apply(client, student_headers, opportunity["id"]).json()

    assert _applications(client, linked_headers, opportunity["id"]).status_code == 200
    assert _applications(client, other_headers, opportunity["id"]).status_code == 403
    assert _decision(
        client, other_headers, opportunity["id"], applied["id"]
    ).status_code == 403

    decided = _decision(client, linked_headers, opportunity["id"], applied["id"])
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "accepted"
    assert decided.json()["reviewed_by_user_id"] == linked["id"]


def test_funding_discovery_deadlines_and_admin_only_creation(
    client, seeded_db, admin_headers, db
):
    assert client.get(BASE, params={"category": "funding"}).json()["total"] == 0

    faculty_headers, _ = _faculty_with_link(client, db, _researcher(db).id)
    assert _create(client, faculty_headers, category="funding").status_code == 403

    now = int(time.time())
    soon = _create(
        client,
        admin_headers,
        category="funding",
        title="Short Deadline Grant",
        organization="NSF",
        deadline_at=now + 600,
        required_skills="",
    ).json()
    later = _create(
        client,
        admin_headers,
        category="funding",
        title="Long Deadline Grant",
        organization="DOE",
        deadline_at=now + 9000,
        required_skills="",
    ).json()

    funding = client.get(BASE, params={"category": "funding"}).json()
    assert funding["total"] == 2
    assert {item["title"] for item in funding["opportunities"]} == {
        "Short Deadline Grant",
        "Long Deadline Grant",
    }
    assert all(item["category"] == "funding" for item in funding["opportunities"])
    assert all(item["researcher_id"] is None for item in funding["opportunities"])

    before = client.get(
        BASE, params={"category": "funding", "deadline_before": now + 1000}
    ).json()
    assert [item["id"] for item in before["opportunities"]] == [soon["id"]]
    after = client.get(
        BASE, params={"category": "funding", "deadline_after": now + 1000}
    ).json()
    assert [item["id"] for item in after["opportunities"]] == [later["id"]]


def test_external_funding_adapter_is_disabled_by_default(
    client, seeded_db, admin_headers, monkeypatch
):
    monkeypatch.delenv(funding_sources.ENABLED_ENV, raising=False)

    assert client.get("/admin/opportunities/sources").status_code == 401
    student_headers, _ = register_test_account(client, role="student")
    assert client.get(
        "/admin/opportunities/sources", headers=student_headers
    ).status_code == 403

    sources = client.get("/admin/opportunities/sources", headers=admin_headers)
    assert sources.status_code == 200, sources.text
    entry = next(
        item for item in sources.json()["sources"] if item["name"] == "grants_gov"
    )
    assert entry["enabled"] is False

    imported = client.post(
        "/admin/opportunities/import",
        json={"source": "grants_gov", "query": "AI", "limit": 5},
        headers=admin_headers,
    )
    assert imported.status_code == 400, imported.text
    assert "disabled" in imported.json()["detail"].lower()
    assert client.get(BASE, params={"category": "funding"}).json()["total"] == 0

    unknown = client.post(
        "/admin/opportunities/import",
        json={"source": "unknown_source", "query": "AI", "limit": 5},
        headers=admin_headers,
    )
    assert unknown.status_code == 400
    assert client.post(
        "/admin/opportunities/import",
        json={"source": "grants_gov", "query": "", "limit": 5},
        headers=admin_headers,
    ).status_code == 422
    assert client.post(
        "/admin/opportunities/import",
        json={"source": "grants_gov", "query": "AI", "limit": 0},
        headers=admin_headers,
    ).status_code == 422


def test_external_funding_import_is_honest_and_idempotent(
    client, seeded_db, admin_headers, monkeypatch
):
    monkeypatch.setenv(funding_sources.ENABLED_ENV, "true")
    now = int(time.time())
    fetched = [
        {
            "external_source": "grants_gov",
            "external_id": "9001",
            "title": "Solar Research Grant",
            "description": "A real source record.",
            "organization": "DOE",
            "url": "",
            "deadline_at": now + 86400,
            "required_skills": "",
            "required_research_areas": "",
            "required_expertise": "",
            "eligibility": "Open to universities.",
        }
    ]
    monkeypatch.setattr(funding_sources, "fetch", lambda query, limit: list(fetched))

    first = client.post(
        "/admin/opportunities/import",
        json={"source": "grants_gov", "query": "solar", "limit": 5},
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0
    assert body["opportunities"][0]["status"] == "draft"
    assert body["opportunities"][0]["external_source"] == "grants_gov"
    assert body["opportunities"][0]["external_id"] == "9001"
    assert body["opportunities"][0]["title"] == "Solar Research Grant"
    assert body["opportunities"][0]["organization"] == "DOE"

    public = client.get(BASE, params={"category": "funding"}).json()
    assert public["total"] == 0

    second = client.post(
        "/admin/opportunities/import",
        json={"source": "grants_gov", "query": "solar", "limit": 5},
        headers=admin_headers,
    )
    assert second.status_code == 200
    assert second.json()["imported"] == 0
    assert second.json()["skipped"] == 1

    def broken(query, limit):
        raise funding_sources.FundingSourceError("source unreachable")

    monkeypatch.setattr(funding_sources, "fetch", broken)
    failed = client.post(
        "/admin/opportunities/import",
        json={"source": "grants_gov", "query": "solar", "limit": 5},
        headers=admin_headers,
    )
    assert failed.status_code == 502
    assert client.get(BASE, params={"category": "funding"}).json()["total"] == 0


def test_external_source_mapping_does_not_invent_fields():
    mapped = funding_sources._map_hit(
        {
            "id": 42,
            "title": "Coral Grant",
            "agencyName": "NOAA",
            "closeDate": "12/31/2026",
            "synopsis": "Coastal research support.",
        }
    )
    assert mapped["external_id"] == "42"
    assert mapped["external_source"] == "grants_gov"
    assert mapped["title"] == "Coral Grant"
    assert mapped["organization"] == "NOAA"
    assert mapped["description"] == "Coastal research support."
    assert mapped["deadline_at"] is not None
    assert mapped["url"] == ""
    assert mapped["required_skills"] == ""

    sparse = funding_sources._map_hit({"id": 43, "title": "No Date"})
    assert sparse["deadline_at"] is None
    assert sparse["organization"] == ""
    assert sparse["description"] == ""

    assert funding_sources._map_hit({"id": 44}) is None
    assert funding_sources._map_hit({"title": "No id"}) is None
    assert funding_sources._map_hit({"id": 45, "title": "  "}) is None


def test_opportunity_database_constraints(client, seeded_db, admin_headers, db):
    now = int(time.time())
    first = Opportunity(
        category="funding",
        title="External One",
        description="",
        status="draft",
        external_source="grants_gov",
        external_id="same-id",
        created_at=now,
        updated_at=now,
    )
    db.add(first)
    db.commit()

    db.add(
        Opportunity(
            category="funding",
            title="External Two",
            description="",
            status="draft",
            external_source="grants_gov",
            external_id="same-id",
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    opportunity = _create(client, admin_headers).json()
    student_headers, student = register_test_account(client, role="student")
    assert _apply(client, student_headers, opportunity["id"]).status_code == 201
    db.add(
        OpportunityApplication(
            opportunity_id=opportunity["id"],
            student_user_id=student["id"],
            message="Duplicate",
            status="pending",
            decision_note="",
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_opportunities_do_not_touch_teams_or_role_groups(
    client, seeded_db, admin_headers
):
    student_headers, _ = register_test_account(client, role="student")
    session = SessionLocal()
    try:
        before = (
            session.query(Group).count(),
            session.query(GroupMembership).count(),
            session.query(ResearchTeam).count(),
            session.query(ResearchTeamMember).count(),
        )
    finally:
        session.close()

    opportunity = _create(client, admin_headers).json()
    assert _apply(client, student_headers, opportunity["id"]).status_code == 201
    assert client.get(APPLICATIONS, headers=student_headers).status_code == 200

    session = SessionLocal()
    try:
        after = (
            session.query(Group).count(),
            session.query(GroupMembership).count(),
            session.query(ResearchTeam).count(),
            session.query(ResearchTeamMember).count(),
        )
    finally:
        session.close()

    assert before == after


# Shaped by frontend/research-2.0.js opportunityUpdatePayload and
# opportunityCreatePayload; tests/frontend/api-client-2.0-contract.test.cjs
# pins these field sets to the view.
FRONTEND_EDIT_BODY = {
    "status": "open",
    "title": "Edited in the 2.0 view",
    "description": "Recruit participants.",
    "organization": "Example University",
    "location": "Remote",
    "url": "",
    "deadline_at": None,
    "required_skills": "Python",
    "required_research_areas": "education",
    "required_expertise": "ML",
    "eligibility": "Enrolled students",
}
FRONTEND_PUBLISH_BODY = {"category": "funding", **FRONTEND_EDIT_BODY}


def test_opportunity_update_accepts_the_full_edit_form_body(
    client, seeded_db, admin_headers
):
    opportunity = _create(client, admin_headers).json()

    updated = client.put(
        f"{BASE}/{opportunity['id']}",
        json=FRONTEND_EDIT_BODY,
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Edited in the 2.0 view"
    assert updated.json()["category"] == opportunity["category"]


def test_opportunity_create_accepts_the_full_publish_form_body(
    client, seeded_db, admin_headers
):
    published = client.post(
        BASE, json=FRONTEND_PUBLISH_BODY, headers=admin_headers
    )
    assert published.status_code == 201, published.text
    assert published.json()["category"] == "funding"
    assert published.json()["title"] == "Edited in the 2.0 view"
