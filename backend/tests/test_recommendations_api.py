"""HTTP contract tests for /recommendations."""

import pytest

from app.services import recommendation, semantic_matching

from conftest import STUDENT_PROFILE, register_test_account


ENDPOINT = "/recommendations/researchers"


EXPECTED_RECOMMENDATION_KEYS = {
    "researcher_id",
    "name",
    "department",
    "match_score",
    "component_scores",
    "semantic_available",
    "why_recommended",
    "explanation",
    "matched_skills",
    "skill_gap",
}


def _student_headers_with_profile(client):
    headers, _ = register_test_account(client)
    profile = {key: value for key, value in STUDENT_PROFILE.items() if key != "top_k"}
    response = client.put("/students/me/profile", json=profile, headers=headers)
    assert response.status_code == 200, response.text
    return headers


def semantic_error_cls():
    error = getattr(semantic_matching, "SemanticMatchingError", None)
    assert error is not None, "semantic_matching must define SemanticMatchingError"
    return error


def recommendation_error_cls():
    error = getattr(recommendation, "RecommendationError", None)
    assert error is not None, "recommendation must define RecommendationError"
    return error


def test_recommendations_return_the_documented_contract(
    client, seeded_db, patch_semantic
):
    patch_semantic(scores=[0.7, 0.4, 0.2])

    headers = _student_headers_with_profile(client)
    response = client.post(ENDPOINT, json=STUDENT_PROFILE, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"student_profile", "recommendations"}
    assert body["student_profile"]["research_areas"] == (
        STUDENT_PROFILE["research_areas"]
    )

    recommendations = body["recommendations"]
    assert len(recommendations) == 3

    for item in recommendations:
        assert EXPECTED_RECOMMENDATION_KEYS.issubset(item)
        assert set(item["component_scores"]) == set(
            recommendation.EXPECTED_FEATURES
        )
        assert 0.0 <= item["match_score"] <= 1.0
        assert isinstance(item["explanation"]["all_contributions"], list)
        assert len(item["explanation"]["all_contributions"]) == len(
            recommendation.EXPECTED_FEATURES
        )

    scores = [item["match_score"] for item in recommendations]
    assert scores == sorted(scores, reverse=True)


def test_top_k_is_honoured(client, seeded_db, patch_semantic):
    patch_semantic()
    payload = dict(STUDENT_PROFILE, top_k=2)

    headers = _student_headers_with_profile(client)
    response = client.post(ENDPOINT, json=payload, headers=headers)

    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 2


@pytest.mark.parametrize("top_k", [0, -1, 51])
def test_out_of_range_top_k_is_rejected(raw_client, seeded_db, patch_semantic, top_k):
    patch_semantic()
    payload = dict(STUDENT_PROFILE, top_k=top_k)
    headers = _student_headers_with_profile(raw_client)

    response = raw_client.post(ENDPOINT, json=payload, headers=headers)

    assert response.status_code == 422


def test_malformed_json_is_rejected(client):
    headers = _student_headers_with_profile(client)
    response = client.post(
        ENDPOINT,
        content=b'{"research_areas": "AI",',
        headers={**headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_null_body_is_rejected(client):
    headers = _student_headers_with_profile(client)
    response = client.post(ENDPOINT, json=None, headers=headers)

    assert response.status_code == 422


def test_empty_database_returns_empty_recommendations(
    client, empty_db, patch_semantic
):
    patch_semantic()

    headers = _student_headers_with_profile(client)
    response = client.post(ENDPOINT, json=STUDENT_PROFILE, headers=headers)

    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_semantic_failure_maps_to_503(
    raw_client, seeded_db, monkeypatch
):
    error = semantic_error_cls()

    def broken_semantic(student_profile, researchers):
        raise error("embedding backend unavailable")

    monkeypatch.setattr(
        "app.services.recommendation.calculate_semantic_similarity",
        broken_semantic,
    )

    headers = _student_headers_with_profile(raw_client)
    response = raw_client.post(ENDPOINT, json=STUDENT_PROFILE, headers=headers)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == "Recommendation service unavailable"
    assert "embedding backend unavailable" not in detail


def test_shap_failure_maps_to_503(
    raw_client, seeded_db, patch_semantic, monkeypatch
):
    patch_semantic()

    def broken_explainer():
        raise RuntimeError("shap backend exploded")

    monkeypatch.setattr(recommendation, "get_shap_explainer", broken_explainer)

    headers = _student_headers_with_profile(raw_client)
    response = raw_client.post(ENDPOINT, json=STUDENT_PROFILE, headers=headers)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == "Recommendation service unavailable"
    assert "shap backend exploded" not in detail


def test_model_failure_maps_to_503(
    raw_client, seeded_db, patch_semantic, monkeypatch, tmp_path
):
    recommendation_error_cls()
    patch_semantic()
    monkeypatch.setattr(
        recommendation, "MODEL_PATH", str(tmp_path / "missing.joblib")
    )

    headers = _student_headers_with_profile(raw_client)
    response = raw_client.post(ENDPOINT, json=STUDENT_PROFILE, headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "Recommendation service unavailable"


def test_roadmap_requires_authentication(client):
    response = client.post(
        "/recommendations/roadmap/researcher",
        json={"researcher_id": 1},
    )

    assert response.status_code == 401


def test_roadmap_unknown_researcher_returns_404(client):
    headers = _student_headers_with_profile(client)
    response = client.post(
        "/recommendations/roadmap/researcher",
        json={"researcher_id": 987654},
        headers=headers,
    )

    assert response.status_code == 404


def test_roadmap_known_researcher_returns_plan(client, seeded_db):
    headers = _student_headers_with_profile(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    response = client.post(
        "/recommendations/roadmap/researcher",
        json={"researcher_id": researcher_id},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["researcher"]["id"] == researcher_id
    assert isinstance(body["skill_gaps"], list)
    assert body["total_skill_gaps"] == len(body["skill_gaps"])
    assert response.headers["Deprecation"] == "true"


def test_roadmap_ignores_client_supplied_skill_lists(client, seeded_db):
    headers = _student_headers_with_profile(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]

    response = client.post(
        "/recommendations/roadmap/researcher",
        json={
            "researcher_id": researcher_id,
            "matched_skills": ["Quantum Computing"],
            "skill_gap": ["Blockchain"],
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert "quantum computing" not in [skill.lower() for skill in body["matched_skills"]]
    assert [item["skill"] for item in body["skill_gaps"]] != ["Blockchain"]
