"""Per-user researcher directory search history."""

import pytest

from app.database import SessionLocal
from app.models import SearchHistory
from conftest import register_test_account


@pytest.fixture(autouse=True)
def clean_search_history():
    session = SessionLocal()
    try:
        session.query(SearchHistory).delete()
        session.commit()
    finally:
        session.close()
    yield


def test_search_history_requires_authentication(client):
    assert client.get("/search-history").status_code == 401
    assert client.post("/search-history", json={"query": "AI"}).status_code == 401


def test_recorded_searches_are_returned_newest_first(client):
    headers, _ = register_test_account(client)
    for query in ("machine learning", "computer vision"):
        response = client.post(
            "/search-history", json={"query": query}, headers=headers
        )
        assert response.status_code == 200, response.text

    response = client.get("/search-history", headers=headers)
    assert response.status_code == 200
    assert [item["query"] for item in response.json()] == [
        "computer vision",
        "machine learning",
    ]


def test_history_is_private_to_each_account(client):
    first, _ = register_test_account(client, email="history-first@example.test")
    second, _ = register_test_account(client, email="history-second@example.test")
    client.post("/search-history", json={"query": "AI"}, headers=first)

    assert [item["query"] for item in client.get("/search-history", headers=first).json()] == [
        "AI"
    ]
    assert client.get("/search-history", headers=second).json() == []


def test_repeated_consecutive_search_is_not_duplicated(client):
    headers, _ = register_test_account(client)
    client.post("/search-history", json={"query": "NLP"}, headers=headers)
    client.post("/search-history", json={"query": "  nlp  "}, headers=headers)

    entries = client.get("/search-history", headers=headers).json()
    assert len(entries) == 1
    assert entries[0]["query"].lower() == "nlp"


def test_blank_and_oversized_queries_are_rejected(client):
    headers, _ = register_test_account(client)
    blank = client.post("/search-history", json={"query": "   "}, headers=headers)
    oversized = client.post("/search-history", json={"query": "x" * 201}, headers=headers)

    assert blank.status_code == 422
    assert oversized.status_code == 422


def test_history_is_capped_per_account(client):
    headers, _ = register_test_account(client)
    for index in range(25):
        response = client.post(
            "/search-history", json={"query": f"query-{index}"}, headers=headers
        )
        assert response.status_code == 200, response.text

    entries = client.get("/search-history?limit=50", headers=headers).json()
    assert len(entries) == 20
    assert entries[0]["query"] == "query-24"
    assert entries[-1]["query"] == "query-5"
