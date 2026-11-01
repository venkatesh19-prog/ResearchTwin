"""Release-candidate acceptance tests.

These tests encode the contract the deployed frontend relies on:
finite and ranked scores, a complete explanation/skill-gap schema,
the production frontend origin in CORS, precise validation errors,
a readiness probe, and no server-side paths in error details.

Tests that fail here are release blockers, not test bugs.
"""

import math
import sqlite3

import pytest

from app.services import recommendation
from app.services.recommendation import EXPECTED_FEATURES
from conftest import SAMPLE_RESEARCHERS, STUDENT_PROFILE, register_test_account

RECOMMENDATIONS = "/students/me/recommendations"
NETLIFY_ORIGIN = "https://starlit-empanada-a323e3.netlify.app"
FLOAT_EPS = 1e-9


def _saved_student_headers(client, profile=None):
    profile = profile or STUDENT_PROFILE
    headers, _ = register_test_account(client)
    profile_fields = {
        key: profile[key]
        for key in (
            "research_areas",
            "expertise",
            "skills",
            "projects",
            "publications",
        )
        if key in profile
    }
    saved = client.put(
        "/students/me/profile",
        json={
            **profile_fields,
            "courses": "",
            "academic_details": "",
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    return headers


def _post_profile(client, **overrides):
    payload = {**STUDENT_PROFILE, **overrides}
    headers = _saved_student_headers(client, payload)
    response = client.post(
        RECOMMENDATIONS,
        json={"top_k": payload["top_k"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["recommendations"]


# ------------------------------------------------------------------
# 4/5/6 - recommendations: count, numeric ordering, schema
# ------------------------------------------------------------------

def test_requested_number_of_recommendations_is_returned(
    client, seeded_db, patch_semantic
):
    patch_semantic()
    items = _post_profile(client, top_k=2)

    assert len(items) == 2


def test_match_scores_are_finite_bounded_and_descending(
    client, seeded_db, patch_semantic
):
    patch_semantic()
    items = _post_profile(client, top_k=3)

    scores = [item["match_score"] for item in items]

    assert len(scores) == 3
    for score in scores:
        assert isinstance(score, (int, float))
        assert not isinstance(score, bool)
        assert math.isfinite(score)
        assert 0.0 <= score <= 1.0

    assert scores == sorted(scores, reverse=True)

    for item in items:
        for feature, value in item["component_scores"].items():
            assert feature in EXPECTED_FEATURES
            assert math.isfinite(value)
            assert -FLOAT_EPS <= value <= 1.0 + FLOAT_EPS


def test_explanation_schema_is_complete_and_numeric(
    client, seeded_db, patch_semantic
):
    patch_semantic()
    items = _post_profile(client, top_k=3)

    for item in items:
        explanation = item["explanation"]

        assert isinstance(explanation["summary"], str)
        assert explanation["summary"].strip()
        assert item["why_recommended"] == explanation["summary"]

        contributions = explanation["all_contributions"]
        assert len(contributions) == len(EXPECTED_FEATURES)
        assert {entry["feature"] for entry in contributions} == set(
            EXPECTED_FEATURES
        )
        assert len({entry["feature"] for entry in contributions}) == len(
            EXPECTED_FEATURES
        )

        for entry in contributions:
            assert set(entry) == {"feature", "shap_value", "feature_value"}
            assert math.isfinite(entry["shap_value"])
            assert math.isfinite(entry["feature_value"])
            assert -FLOAT_EPS <= entry["feature_value"] <= 1.0 + FLOAT_EPS

        for key in ("top_positive_factors", "top_negative_factors"):
            assert isinstance(explanation[key], list)
            for entry in explanation[key]:
                assert set(entry) == {"feature", "shap_value", "feature_value"}

        magnitudes = [abs(entry["shap_value"]) for entry in contributions]
        assert magnitudes == sorted(magnitudes, reverse=True)


def test_skill_gap_schema_matches_researcher_record(
    client, seeded_db, patch_semantic
):
    patch_semantic()
    items = _post_profile(client, top_k=3)

    by_name = {item["name"]: item for item in items}
    assert set(by_name) == {row["name"] for row in SAMPLE_RESEARCHERS}

    rows = {row["name"]: row for row in SAMPLE_RESEARCHERS}

    for name, item in by_name.items():
        matched = item["matched_skills"]
        gap = item["skill_gap"]

        assert isinstance(matched, list) and isinstance(gap, list)
        assert all(isinstance(skill, str) for skill in matched + gap)
        assert matched == sorted(matched)
        assert gap == sorted(gap)
        assert set(matched).isdisjoint(gap)

        researcher_skills = {
            skill.strip().lower()
            for skill in rows[name]["skills"].split(",")
            if skill.strip()
        }
        assert set(matched) <= researcher_skills
        assert set(gap) <= researcher_skills
        assert set(matched) | set(gap) == researcher_skills

    ada = by_name["Dr. Ada Lovelace"]
    assert ada["matched_skills"] == ["python", "pytorch", "transformers"]
    assert ada["skill_gap"] == []


# ------------------------------------------------------------------
# 3 - database records are readable
# ------------------------------------------------------------------

def test_researcher_directory_reads_database_records(client, seeded_db):
    response = client.get("/researchers/")

    assert response.status_code == 200
    payload = response.text
    rows = response.json()

    assert len(rows) == len(SAMPLE_RESEARCHERS)
    assert {row["name"] for row in rows} == {
        sample["name"] for sample in SAMPLE_RESEARCHERS
    }
    for row in rows:
        for key in ("id", "name", "department", "research_areas", "skills"):
            assert key in row

    lowered = payload.lower()
    assert "sqlite:///" not in lowered
    assert "researchtwin.db" not in lowered
    assert ".venv" not in lowered


# ------------------------------------------------------------------
# 7 - invalid requests
# ------------------------------------------------------------------

@pytest.mark.parametrize("top_k", ["five", 0, -1, 51, 2.5, None])
def test_invalid_top_k_is_rejected(client, seeded_db, top_k):
    headers = _saved_student_headers(client)
    response = client.post(
        RECOMMENDATIONS,
        json={"top_k": top_k},
        headers=headers,
    )

    assert response.status_code == 422
    assert "recommendations" not in response.text


def test_malformed_json_is_rejected(client):
    headers = _saved_student_headers(client)
    response = client.post(
        RECOMMENDATIONS,
        content=b'{"research_areas": "AI", ',
        headers={**headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_non_json_body_is_rejected(client):
    headers = _saved_student_headers(client)
    response = client.post(
        RECOMMENDATIONS,
        content=b"research_areas=AI",
        headers={**headers, "Content-Type": "text/plain"},
    )

    assert response.status_code == 422


def test_unknown_researcher_roadmap_returns_404(client):
    headers = _saved_student_headers(client)
    response = client.post(
        "/recommendations/roadmap/researcher",
        json={"researcher_id": 999999, "matched_skills": []},
        headers=headers,
    )

    assert response.status_code == 404


def test_roadmap_rejects_a_faculty_account(client):
    headers, _ = register_test_account(client, role="faculty")
    response = client.get(
        "/students/me/researchers/1/roadmap",
        headers=headers,
    )

    assert response.status_code == 403


# ------------------------------------------------------------------
# 2 - health and readiness probes
# ------------------------------------------------------------------

def test_health_probe_reports_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.parametrize("path", ["/ready", "/readiness"])
def test_readiness_probe_is_available(client, path):
    response = client.get(path)

    assert response.status_code == 200, (
        f"{path} missing; deployments have no readiness probe "
        "distinct from the liveness-style /health endpoint"
    )
    body = response.json()
    assert body.get("status") in {"ready", "healthy"}


# ------------------------------------------------------------------
# 8/9 - empty and degraded matching paths
# ------------------------------------------------------------------

def test_empty_database_returns_empty_recommendations(client, empty_db):
    assert _post_profile(client) == []


def test_semantic_unavailable_keeps_scores_finite(
    client, seeded_db, patch_semantic
):
    def unavailable(student_profile, researchers):
        return [
            {
                "researcher_id": researcher.id,
                "name": researcher.name,
                "department": researcher.department,
                "semantic_score": 0.0,
                "semantic_available": False,
            }
            for researcher in researchers
        ]

    patch_semantic(results_factory=unavailable)
    items = _post_profile(client, top_k=3)

    assert items
    for item in items:
        assert item["semantic_available"] is False
        assert item["component_scores"]["semantic_similarity"] == 0.0
        assert math.isfinite(item["match_score"])


# ------------------------------------------------------------------
# 12 - CORS for the deployed frontend origin
# ------------------------------------------------------------------

def test_cors_preflight_allows_deployed_frontend_origin(client):
    response = client.options(
        RECOMMENDATIONS,
        headers={
            "Origin": NETLIFY_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == NETLIFY_ORIGIN
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert "authorization" in response.headers.get(
        "access-control-allow-headers", ""
    ).lower()


def test_cors_simple_request_allows_deployed_frontend_origin(client):
    response = client.get("/health", headers={"Origin": NETLIFY_ORIGIN})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == NETLIFY_ORIGIN


def test_cors_does_not_echo_unlisted_origin(client):
    response = client.get(
        "/health", headers={"Origin": "https://attacker.example"}
    )

    assert response.headers.get("access-control-allow-origin") != (
        "https://attacker.example"
    )


# ------------------------------------------------------------------
# 13 - error details must not leak server paths
# ------------------------------------------------------------------

def test_model_failure_detail_does_not_leak_server_path(
    raw_client, seeded_db, patch_semantic, monkeypatch, tmp_path
):
    patch_semantic()
    monkeypatch.setattr(
        recommendation,
        "MODEL_PATH",
        str(tmp_path / "missing" / "researchtwin_logistic_render.joblib"),
    )

    headers = _saved_student_headers(raw_client)
    response = raw_client.post(
        RECOMMENDATIONS, json={"top_k": 5}, headers=headers
    )

    assert response.status_code == 503
    detail = response.json().get("detail", "")
    assert str(tmp_path) not in detail
    assert "ResearchTwin model not found" not in detail


def test_import_failure_detail_does_not_leak_database_path(
    client, monkeypatch, admin_headers
):
    def exploding_import(csv_path, db):
        raise sqlite3.OperationalError(
            "unable to open database file: "
            r"C:\deploy\secret-location\researchtwin.db"
        )

    monkeypatch.setattr(
        "app.api.researchers.import_researchers", exploding_import
    )

    response = client.post("/researchers/import", headers=admin_headers)

    assert response.status_code == 500
    detail = response.json().get("detail", "")
    assert "secret-location" not in detail
    assert "unable to open database" not in detail
    assert "sqlite" not in detail.lower()
