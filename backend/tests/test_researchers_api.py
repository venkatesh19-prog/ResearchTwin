"""CRUD and search contract tests for /researchers."""

BASE = "/researchers/"

RESEARCHER_PAYLOAD = {
    "name": "Dr. Test Subject",
    "department": "Computer Science and Engineering",
    "designation": "Assistant Professor",
    "experience": 4,
    "research_areas": "Machine Learning, Information Retrieval",
    "expertise": "Ranking Models",
    "skills": "Python, SQL",
    "publications": "Neural Ranking",
    "projects": "Search Evaluation Toolkit",
    "profile_url": "https://example.com/test",
}


def test_list_is_empty_after_reset(client, empty_db):
    response = client.get(BASE)

    assert response.status_code == 200
    assert response.json() == []


def test_create_read_update_delete_round_trip(client, empty_db, admin_headers):
    created = client.post(BASE, json=RESEARCHER_PAYLOAD, headers=admin_headers)
    assert created.status_code == 200

    body = created.json()
    researcher_id = body["id"]
    assert body["name"] == RESEARCHER_PAYLOAD["name"]
    assert body["skills"] == RESEARCHER_PAYLOAD["skills"]

    fetched = client.get(f"{BASE}{researcher_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == researcher_id

    updated_payload = dict(RESEARCHER_PAYLOAD, designation="Professor")
    updated = client.put(
        f"{BASE}{researcher_id}", json=updated_payload, headers=admin_headers
    )
    assert updated.status_code == 200
    assert updated.json()["designation"] == "Professor"

    deleted = client.delete(f"{BASE}{researcher_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json()["researcher_id"] == researcher_id

    missing = client.get(f"{BASE}{researcher_id}")
    assert missing.status_code == 404


def test_missing_researcher_returns_404(client, empty_db, admin_headers):
    assert client.get(f"{BASE}424242").status_code == 404
    assert (
        client.put(
            f"{BASE}424242", json=RESEARCHER_PAYLOAD, headers=admin_headers
        ).status_code == 404
    )
    assert client.delete(f"{BASE}424242", headers=admin_headers).status_code == 404


def test_create_requires_name(client, empty_db, admin_headers):
    response = client.post(
        BASE, json={"department": "CS"}, headers=admin_headers
    )

    assert response.status_code == 422


def test_filters_are_applied(client, empty_db, admin_headers):
    client.post(
        BASE,
        json=dict(RESEARCHER_PAYLOAD, name="Dr. ML", skills="Python, PyTorch"),
        headers=admin_headers,
    )
    client.post(
        BASE,
        json=dict(
            RESEARCHER_PAYLOAD,
            name="Dr. Security",
            department="Information Technology",
            research_areas="Cybersecurity",
            skills="Wireshark",
        ),
        headers=admin_headers,
    )

    by_department = client.get(BASE, params={"department": "Information"}).json()
    assert [item["name"] for item in by_department] == ["Dr. Security"]

    by_area = client.get(BASE, params={"research_area": "Machine Learning"}).json()
    assert [item["name"] for item in by_area] == ["Dr. ML"]

    by_skill = client.get(BASE, params={"skill": "PyTorch"}).json()
    assert [item["name"] for item in by_skill] == ["Dr. ML"]


def test_free_text_search_matches_descriptive_fields_and_escapes_wildcards(
    client, empty_db, admin_headers
):
    client.post(BASE, json=dict(RESEARCHER_PAYLOAD, name="Dr. ML"), headers=admin_headers)
    client.post(
        BASE,
        json=dict(
            RESEARCHER_PAYLOAD,
            name="Dr. Security",
            department="Information Technology",
            research_areas="Cybersecurity",
            skills="Wireshark",
        ),
        headers=admin_headers,
    )

    by_name = client.get(BASE, params={"search": "Security"}).json()
    assert [item["name"] for item in by_name] == ["Dr. Security"]

    by_publication = client.get(BASE, params={"search": "Ranking"}).json()
    assert {item["name"] for item in by_publication} == {"Dr. Security", "Dr. ML"}

    no_match = client.get(BASE, params={"search": "quantum optics"}).json()
    assert no_match == []

    # A literal percent must not behave like a wildcard.
    assert client.get(BASE, params={"search": "%"}).json() == []


def test_intelligence_endpoint_returns_profiles(client, empty_db, admin_headers):
    client.post(BASE, json=RESEARCHER_PAYLOAD, headers=admin_headers)

    response = client.get(f"{BASE}intelligence")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1


def test_directory_reads_support_stable_bounded_pages(client, seeded_db):
    first_page = client.get(BASE, params={"limit": 2})
    second_page = client.get(BASE, params={"limit": 2, "offset": 2})

    assert first_page.status_code == second_page.status_code == 200
    first_ids = [row["id"] for row in first_page.json()]
    second_ids = [row["id"] for row in second_page.json()]
    assert len(first_ids) == 2
    assert len(second_ids) == 1
    assert set(first_ids).isdisjoint(second_ids)
    assert first_ids == sorted(first_ids)

    intelligence_page = client.get(
        "/researchers/intelligence", params={"limit": 1, "offset": 1}
    )
    assert intelligence_page.status_code == 200
    assert len(intelligence_page.json()) == 1

    assert client.get(BASE, params={"limit": 501}).status_code == 422
    assert client.get(BASE, params={"offset": -1}).status_code == 422
