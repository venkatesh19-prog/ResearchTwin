"""Recommendation engine tests using the real model bundle and SHAP.

Semantic matching is stubbed so these tests never download the embedding model.
"""

import pytest
from types import SimpleNamespace

from app.services import recommendation, semantic_matching
from app.services.recommendation import (
    calculate_features,
    calculate_skill_overlap,
    generate_recommendations,
)
from app.services.skill_gap import calculate_skill_gap, normalize_skills

from conftest import STUDENT_PROFILE, make_semantic_results


def test_recommendation_overlap_uses_the_skill_gap_delimiters_and_normalization():
    researcher = SimpleNamespace(
        id=7,
        name="Dr. Skill Parser",
        skills="Python; C++\nPyTorch",
    )
    student_skills = " python, c++; Julia "

    overlap = calculate_skill_overlap(student_skills, researcher.skills)
    gap = calculate_skill_gap(student_skills, researcher)

    assert overlap == pytest.approx(2 / 3)
    assert gap["matched_skills"] == ["c++", "python"]
    assert overlap == pytest.approx(
        len(gap["matched_skills"]) / len(normalize_skills(researcher.skills))
    )


def test_serving_features_match_the_seven_feature_model(seeded_db, db):
    researcher = db.query(recommendation.Researcher).first()
    profile = dict(STUDENT_PROFILE, department=researcher.department)

    features = calculate_features(profile, researcher, semantic_score=0.5)

    assert tuple(features) == recommendation.EXPECTED_FEATURES
    assert "department_match" not in features


def error_cls():
    error = getattr(recommendation, "RecommendationError", None)
    assert error is not None, "recommendation must define RecommendationError"
    return error


def test_recommendations_are_ranked_and_limited(seeded_db, db, patch_semantic):
    recorded = patch_semantic(scores=[0.2, 0.8, 0.5])

    results = generate_recommendations(STUDENT_PROFILE, db, top_k=2)

    assert len(results) == 2
    scores = [result["match_score"] for result in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)

    for result in results:
        assert set(result["component_scores"]) == set(
            recommendation.EXPECTED_FEATURES
        )
        assert isinstance(result["why_recommended"], str)
        assert result["why_recommended"]
        assert len(result["explanation"]["all_contributions"]) == len(
            recommendation.EXPECTED_FEATURES
        )
        assert isinstance(result["matched_skills"], list)
        assert isinstance(result["skill_gap"], list)

    assert recorded["calls"] == 1
    assert len(recorded["researchers"]) == 3


def test_semantic_scores_follow_researcher_id_not_position(
    seeded_db, db, patch_semantic
):
    seeded_researchers = (
        db.query(recommendation.Researcher).order_by(
            recommendation.Researcher.id
        ).all()
    )
    scores_by_id = {
        seeded_researchers[0].id: 0.11,
        seeded_researchers[1].id: 0.77,
        seeded_researchers[2].id: 0.33,
    }

    def shuffled_results(student_profile, researchers):
        results = make_semantic_results(
            researchers,
            scores=[scores_by_id[researcher.id] for researcher in researchers],
        )
        return list(reversed(results))

    patch_semantic(results_factory=shuffled_results)

    results = generate_recommendations(STUDENT_PROFILE, db, top_k=3)
    by_id = {result["researcher_id"]: result for result in results}

    for researcher_id, expected in scores_by_id.items():
        assert by_id[researcher_id]["component_scores"][
            "semantic_similarity"
        ] == pytest.approx(expected)


def test_missing_semantic_result_raises_controlled_error(
    seeded_db, db, patch_semantic
):
    error = error_cls()

    def incomplete_results(student_profile, researchers):
        return make_semantic_results(researchers[:1])

    patch_semantic(results_factory=incomplete_results)

    with pytest.raises(error):
        generate_recommendations(STUDENT_PROFILE, db, top_k=3)


def test_duplicate_semantic_ids_raise_controlled_error(
    seeded_db, db, patch_semantic
):
    error = error_cls()

    def duplicated_results(student_profile, researchers):
        results = make_semantic_results(researchers)
        results.append(dict(results[0]))
        return results

    patch_semantic(results_factory=duplicated_results)

    with pytest.raises(error):
        generate_recommendations(STUDENT_PROFILE, db, top_k=3)


def test_unknown_semantic_id_raises_controlled_error(
    seeded_db, db, patch_semantic
):
    error = error_cls()

    def foreign_results(student_profile, researchers):
        results = make_semantic_results(researchers)
        foreign = dict(results[0])
        foreign["researcher_id"] = 999999
        return results + [foreign]

    patch_semantic(results_factory=foreign_results)

    with pytest.raises(error):
        generate_recommendations(STUDENT_PROFILE, db, top_k=3)


def test_empty_database_returns_no_recommendations(empty_db, db, patch_semantic):
    recorded = patch_semantic()

    assert generate_recommendations(STUDENT_PROFILE, db, top_k=5) == []
    assert recorded["calls"] == 0


def test_semantic_unavailability_is_reported_not_silently_zeroed(
    seeded_db, db, patch_semantic
):
    def partially_available(student_profile, researchers):
        results = make_semantic_results(researchers, scores=[0.4, 0.3, 0.2])
        results[0]["semantic_available"] = False
        results[0]["semantic_score"] = 0.0
        return results

    patch_semantic(results_factory=partially_available)

    results = generate_recommendations(STUDENT_PROFILE, db, top_k=3)
    flags = {
        result["researcher_id"]: result["semantic_available"]
        for result in results
    }

    assert list(flags.values()).count(False) == 1


def test_embedding_model_is_not_used_when_scores_are_supplied(
    seeded_db, db, patch_semantic, monkeypatch
):
    def fail():
        raise AssertionError("per-researcher embedding must not run")

    monkeypatch.setattr(semantic_matching, "get_model", fail)
    patch_semantic()

    assert len(generate_recommendations(STUDENT_PROFILE, db, top_k=3)) == 3


def test_top_k_larger_than_candidate_count_returns_all(seeded_db, db, patch_semantic):
    patch_semantic()

    results = generate_recommendations(STUDENT_PROFILE, db, top_k=25)

    assert len(results) == 3
