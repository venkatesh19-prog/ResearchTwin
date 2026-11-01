"""Roadmap derivation (§3) and persisted milestone progress (§7)."""

import pytest

from conftest import register_test_account

ROADMAP = "/students/me/researchers/{researcher_id}/roadmap"
PROFILE_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
    "courses",
    "academic_details",
)


def _student(client, skills="Python, SQL"):
    headers, _ = register_test_account(client)
    saved = client.put(
        "/students/me/profile",
        json={field: "" for field in PROFILE_FIELDS} | {"skills": skills},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    return headers


def _first_researcher_id(client):
    """Ada Lovelace: skills Python, PyTorch, Transformers."""
    return client.get("/researchers/").json()[0]["id"]


def test_roadmap_requires_a_student_session(client, seeded_db):
    assert client.get(ROADMAP.format(researcher_id=1)).status_code == 401


def test_roadmap_requires_a_saved_profile(client, seeded_db):
    headers, _ = register_test_account(client)
    response = client.get(
        ROADMAP.format(researcher_id=_first_researcher_id(client)),
        headers=headers,
    )

    assert response.status_code == 400
    assert "profile" in response.json()["detail"].lower()


def test_unknown_researcher_roadmap_is_404(client, seeded_db):
    headers = _student(client)
    assert client.get(ROADMAP.format(researcher_id=987654), headers=headers).status_code == 404


def test_roadmap_uses_the_saved_profile_skills(client, seeded_db):
    headers = _student(client, skills="Python, SQL")
    body = client.get(
        ROADMAP.format(researcher_id=_first_researcher_id(client)),
        headers=headers,
    ).json()

    assert body["matched_skills"] == ["python"]
    assert [item["skill"] for item in body["skill_gaps"]] == [
        "pytorch",
        "transformers",
    ]
    assert body["total_skill_gaps"] == 2


def test_blank_student_skills_are_not_reported_as_total_gaps(client, seeded_db):
    """The defect: an empty skill string made every researcher skill a gap."""
    headers = _student(client, skills="")
    body = client.get(
        ROADMAP.format(researcher_id=_first_researcher_id(client)),
        headers=headers,
    ).json()

    assert body["student_skills_provided"] is False
    assert body["skill_gaps"] == []
    assert body["matched_skills"] == []
    assert "add your technical skills" in body["message"].lower()
    assert body["researcher_skills"] == ["python", "pytorch", "transformers"]
    assert body["researcher_skill_count"] == 3


def test_roadmap_item_carries_the_full_learning_plan(client, seeded_db):
    headers = _student(client, skills="Python")
    body = client.get(
        ROADMAP.format(researcher_id=_first_researcher_id(client)),
        headers=headers,
    ).json()

    item = next(entry for entry in body["skill_gaps"] if entry["skill"] == "pytorch")

    assert item["priority"] == "high"
    assert item["reason"]
    assert item["project"]
    assert len(item["completion_criteria"]) == 3
    assert [milestone["index"] for milestone in item["milestones"]] == [0, 1, 2]
    assert all(entry["completed"] is False for entry in item["milestones"])
    assert all(entry["text"] for entry in item["milestones"])
    assert body["researcher"]["name"] == "Dr. Ada Lovelace"


def test_unlisted_skill_gets_a_generic_plan(client, empty_db, admin_headers):
    created = client.post(
        "/researchers/",
        json={
            "name": "Dr. Nobody",
            "department": "Linguistics",
            "skills": "Historical Syntax",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    researcher_id = created.json()["id"]

    headers = _student(client, skills="Python")
    body = client.get(
        ROADMAP.format(researcher_id=researcher_id),
        headers=headers,
    ).json()

    item = body["skill_gaps"][0]
    assert item["skill"] == "historical syntax"
    assert item["priority"] == "medium"
    assert "confirm its relevance" in item["reason"].lower()


def test_milestone_completion_persists_and_reopens(client, seeded_db):
    headers = _student(client, skills="Python")
    researcher_id = _first_researcher_id(client)
    path = ROADMAP.format(researcher_id=researcher_id)

    updated = client.put(
        f"{path}/progress",
        json={"skill": "pytorch", "milestone_index": 0, "completed": True},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()

    assert body["progress"] == {
        "total_milestones": 6,
        "completed_milestones": 1,
        "completion_percentage": 17,
    }

    reloaded = client.get(path, headers=headers).json()
    pytorch = next(item for item in reloaded["skill_gaps"] if item["skill"] == "pytorch")
    assert pytorch["milestones"][0]["completed"] is True
    assert pytorch["milestones_completed"] == 1

    reopened = client.put(
        f"{path}/progress",
        json={"skill": "pytorch", "milestone_index": 0, "completed": False},
        headers=headers,
    ).json()
    assert reopened["progress"]["completed_milestones"] == 0
    assert reopened["progress"]["completion_percentage"] == 0


def test_progress_is_scoped_to_the_owning_student(client, seeded_db):
    headers = _student(client, skills="Python")
    researcher_id = _first_researcher_id(client)
    path = ROADMAP.format(researcher_id=researcher_id)

    client.put(
        f"{path}/progress",
        json={"skill": "transformers", "milestone_index": 2, "completed": True},
        headers=headers,
    )

    other_headers = _student(client, skills="Python")
    other_body = client.get(path, headers=other_headers).json()

    assert other_body["progress"]["completed_milestones"] == 0
    assert all(
        milestone["completed"] is False
        for item in other_body["skill_gaps"]
        for milestone in item["milestones"]
    )


def test_progress_is_scoped_to_the_selected_researcher(client, seeded_db):
    headers = _student(client, skills="Python")
    researchers = client.get("/researchers/").json()
    first, second = researchers[0]["id"], researchers[2]["id"]

    client.put(
        f"{ROADMAP.format(researcher_id=first)}/progress",
        json={"skill": "pytorch", "milestone_index": 0, "completed": True},
        headers=headers,
    )

    other = client.get(
        ROADMAP.format(researcher_id=second), headers=headers
    ).json()
    assert other["progress"]["completed_milestones"] == 0


def test_unknown_milestone_cannot_be_persisted(client, seeded_db):
    headers = _student(client, skills="Python")
    path = ROADMAP.format(researcher_id=_first_researcher_id(client))

    out_of_range = client.put(
        f"{path}/progress",
        json={"skill": "pytorch", "milestone_index": 9, "completed": True},
        headers=headers,
    )
    assert out_of_range.status_code == 404

    unknown_skill = client.put(
        f"{path}/progress",
        json={"skill": "blockchain", "milestone_index": 0, "completed": True},
        headers=headers,
    )
    assert unknown_skill.status_code == 404

    assert client.get(path, headers=headers).json()["progress"][
        "completed_milestones"
    ] == 0


def test_roadmap_route_rejects_a_body_payload(client, seeded_db):
    headers = _student(client, skills="Python")
    response = client.post(
        ROADMAP.format(researcher_id=_first_researcher_id(client)),
        json={"skill": "pytorch"},
        headers=headers,
    )

    assert response.status_code == 405


def test_simultaneous_first_milestone_saves_are_idempotent(client, seeded_db, monkeypatch, db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Query
    from app.models import RoadmapProgress

    headers = _student(client, skills="Python")
    researcher_id = _first_researcher_id(client)
    path = ROADMAP.format(researcher_id=researcher_id)
    barrier = Barrier(2)
    original_first = Query.first

    def synchronized_first(query):
        result = original_first(query)
        if query.column_descriptions[0].get("entity") is RoadmapProgress:
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(Query, "first", synchronized_first)
    payload = {"skill": "pytorch", "milestone_index": 0, "completed": True}
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(
            lambda _: client.put(f"{path}/progress", json=payload, headers=headers),
            range(2),
        ))
    assert [response.status_code for response in responses] == [200, 200]
    assert client.get(path, headers=headers).json()["progress"]["completed_milestones"] == 1
    assert db.query(RoadmapProgress).filter_by(researcher_id=researcher_id).count() == 1
