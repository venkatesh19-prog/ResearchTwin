"""Model artifact compatibility, caching, and failure-mode tests."""

import threading
import time
import warnings

import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.services import recommendation


EXPECTED_ORDER = [
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
]


def fitted_pipeline():
    x = np.array([
        [0.1, 0.1, 0.1, 0.1, 0.0, 0.1, 0.1],
        [0.6, 0.7, 0.6, 0.7, 0.5, 0.6, 0.6],
        [0.9, 0.8, 0.9, 0.8, 1.0, 0.8, 0.9],
    ])
    y = [0, 1, 1]

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(max_iter=200)),
    ])
    pipeline.fit(x, y)
    return pipeline


def recommendation_error():
    error_cls = getattr(recommendation, "RecommendationError", None)
    assert error_cls is not None, (
        "recommendation must define RecommendationError"
    )
    return error_cls


def test_expected_feature_order_matches_training_configuration():
    assert list(recommendation.EXPECTED_FEATURES) == EXPECTED_ORDER


def test_shipped_bundle_uses_expected_features():
    bundle = recommendation.load_model()

    assert list(bundle["features"]) == EXPECTED_ORDER
    assert bundle["model_version"] == "researchtwin-logistic-v2-7features"


def test_shipped_bundle_loads_without_runtime_version_warnings():
    from sklearn.exceptions import InconsistentVersionWarning

    recommendation._model_bundle = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        recommendation.load_model()

    mismatches = [
        warning
        for warning in caught
        if issubclass(warning.category, InconsistentVersionWarning)
    ]

    assert not mismatches, (
        "The active model was trained with a different scikit-learn "
        "version. Install the pins from constraints.txt before running "
        "the application."
    )


def test_shipped_bundle_contains_scaler_and_classifier():
    bundle = recommendation.load_model()

    assert set(bundle["model"].named_steps) == {"scaler", "classifier"}


def test_load_model_returns_cached_instance():
    first = recommendation.load_model()
    second = recommendation.load_model()

    assert first is second


def test_load_model_initializes_once_under_concurrency(monkeypatch):
    real_load = joblib.load
    calls = []

    def slow_load(path, *args, **kwargs):
        calls.append(path)
        time.sleep(0.05)
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(recommendation.joblib, "load", slow_load)

    recommendation._model_bundle = None
    loaded = []

    def worker():
        loaded.append(recommendation.load_model())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    assert len(loaded) == 8
    assert all(bundle is loaded[0] for bundle in loaded)


def test_validate_model_bundle_accepts_valid_bundle():
    bundle = {
        "model": fitted_pipeline(),
        "features": list(EXPECTED_ORDER),
    }

    assert recommendation.validate_model_bundle(bundle) is bundle


def test_load_model_rejects_wrong_feature_order(tmp_path, monkeypatch):
    error_cls = recommendation_error()

    bundle_path = tmp_path / "wrong_order.joblib"
    joblib.dump(
        {
            "model": fitted_pipeline(),
            "features": list(reversed(EXPECTED_ORDER)),
        },
        bundle_path,
    )

    monkeypatch.setattr(recommendation, "MODEL_PATH", str(bundle_path))
    recommendation._model_bundle = None

    with pytest.raises(error_cls):
        recommendation.load_model()


def test_load_model_rejects_bundle_without_features(tmp_path, monkeypatch):
    error_cls = recommendation_error()

    bundle_path = tmp_path / "no_features.joblib"
    joblib.dump({"model": fitted_pipeline()}, bundle_path)

    monkeypatch.setattr(recommendation, "MODEL_PATH", str(bundle_path))
    recommendation._model_bundle = None

    with pytest.raises(error_cls):
        recommendation.load_model()


def test_load_model_rejects_object_that_is_not_a_pipeline(tmp_path, monkeypatch):
    error_cls = recommendation_error()

    bundle_path = tmp_path / "not_a_pipeline.joblib"
    joblib.dump(
        {"model": object(), "features": list(EXPECTED_ORDER)},
        bundle_path,
    )

    monkeypatch.setattr(recommendation, "MODEL_PATH", str(bundle_path))
    recommendation._model_bundle = None

    with pytest.raises(error_cls):
        recommendation.load_model()


def test_load_model_missing_file_raises_controlled_error(tmp_path, monkeypatch):
    error_cls = recommendation_error()

    monkeypatch.setattr(
        recommendation, "MODEL_PATH", str(tmp_path / "missing.joblib")
    )
    recommendation._model_bundle = None

    with pytest.raises(error_cls):
        recommendation.load_model()


def test_load_model_corrupt_file_raises_controlled_error(tmp_path, monkeypatch):
    error_cls = recommendation_error()

    bundle_path = tmp_path / "corrupt.joblib"
    bundle_path.write_bytes(b"not a joblib payload")

    monkeypatch.setattr(recommendation, "MODEL_PATH", str(bundle_path))
    recommendation._model_bundle = None

    with pytest.raises(error_cls):
        recommendation.load_model()
