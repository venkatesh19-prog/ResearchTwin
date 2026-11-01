"""SHAP explanation correctness and initialization tests."""

import threading
import time

import numpy as np
import pandas as pd
import shap as shap_lib

from app.services import recommendation


FEATURES = [
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
]


def test_explanation_orders_contributions_by_magnitude():
    features = list(FEATURES)
    shap_values = np.array([0.10, -0.50, 0.30, 0.0, -0.20, 0.05, 0.40])
    feature_values = np.array([0.1, 0.2, 0.3, 0.0, 0.5, 0.6, 0.7])

    explanation = recommendation.generate_explanation(
        shap_values, feature_values, features
    )

    magnitudes = [
        abs(item["shap_value"]) for item in explanation["all_contributions"]
    ]
    assert magnitudes == sorted(magnitudes, reverse=True)

    positives = [
        item["shap_value"] for item in explanation["top_positive_factors"]
    ]
    negatives = [
        item["shap_value"] for item in explanation["top_negative_factors"]
    ]
    assert positives and all(value > 0 for value in positives)
    assert negatives and all(value < 0 for value in negatives)

    assert len(explanation["all_contributions"]) == len(features)
    assert explanation["summary"].startswith(
        "The recommendation is primarily supported by"
    )


def test_explanation_without_positive_evidence_uses_fallback_summary():
    features = list(FEATURES)
    shap_values = np.full(len(features), -0.1)
    feature_values = np.zeros(len(features))

    explanation = recommendation.generate_explanation(
        shap_values, feature_values, features
    )

    assert explanation["top_positive_factors"] == []
    assert explanation["summary"] == (
        "The model found limited positive evidence for this researcher match."
    )


def test_explainer_is_cached():
    first = recommendation.get_shap_explainer()
    second = recommendation.get_shap_explainer()

    assert first is second


def test_explainer_initializes_once_under_concurrency(monkeypatch):
    real_explainer = shap_lib.LinearExplainer
    calls = []

    def slow_explainer(*args, **kwargs):
        calls.append(1)
        time.sleep(0.05)
        return real_explainer(*args, **kwargs)

    monkeypatch.setattr(shap_lib, "LinearExplainer", slow_explainer)

    recommendation._shap_explainer = None
    created = []

    def worker():
        created.append(recommendation.get_shap_explainer())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    assert len(created) == 8
    assert all(explainer is created[0] for explainer in created)


def test_explainer_attributes_match_the_scaled_classifier_margin():
    bundle = recommendation.load_model()
    features = bundle["features"]
    scaler = bundle["model"].named_steps["scaler"]
    classifier = bundle["model"].named_steps["classifier"]

    frame = pd.DataFrame(
        [
            [0.2, 0.4, 0.3, 0.5, 0.1, 0.6, 0.2],
            [0.8, 0.9, 0.7, 0.6, 1.0, 0.5, 0.9],
        ],
        columns=features,
    )
    scaled = scaler.transform(frame)

    explainer = recommendation.get_shap_explainer()
    shap_result = explainer(scaled)

    assert shap_result.values.shape == (2, len(features))

    base_value = float(np.ravel(explainer.expected_value)[0])
    margins = classifier.decision_function(scaled)

    np.testing.assert_allclose(
        shap_result.values.sum(axis=1) + base_value,
        margins,
        atol=1e-6,
    )


def test_explainer_explains_scaled_features_not_raw_values():
    bundle = recommendation.load_model()
    features = bundle["features"]
    scaler = bundle["model"].named_steps["scaler"]

    raw = pd.DataFrame(
        np.zeros((1, len(features))), columns=features
    )
    scaled = scaler.transform(raw)

    explainer = recommendation.get_shap_explainer()
    shap_result = explainer(scaled)

    assert shap_result.values.shape == (1, len(features))
    assert np.all(np.isfinite(shap_result.values))
