"""Health and readiness probes."""

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.services import recommendation


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


def write_bundle(path, **overrides):
    bundle = {
        "model": fitted_pipeline(),
        "features": list(recommendation.EXPECTED_FEATURES),
        "model_version": "researchtwin-logistic-v2-7features",
        "training_data_sha256": "0" * 64,
    }
    bundle.update(overrides)
    joblib.dump(bundle, path)
    return path


def test_health_returns_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_root_reports_running(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "message" in body


def test_readiness_reports_ready_with_valid_artifacts(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_artifact_check_matches_bundle_provenance():
    status = recommendation.verify_serving_artifacts()
    bundle = recommendation.load_model()

    assert status["model_version"] == bundle["model_version"]
    assert status["dataset_sha256"] == bundle["training_data_sha256"]


def test_readiness_fails_when_bundle_feature_order_is_wrong(
    client, tmp_path, monkeypatch
):
    bundle_path = write_bundle(
        tmp_path / "wrong_order.joblib",
        features=list(reversed(recommendation.EXPECTED_FEATURES)),
    )
    monkeypatch.setattr(recommendation, "MODEL_PATH", str(bundle_path))
    recommendation._model_bundle = None

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_fails_when_model_artifact_is_unloadable(
    client, tmp_path, monkeypatch
):
    bundle_path = tmp_path / "corrupt.joblib"
    bundle_path.write_bytes(b"not a joblib payload")
    monkeypatch.setattr(recommendation, "MODEL_PATH", str(bundle_path))
    recommendation._model_bundle = None

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_fails_when_shap_dataset_is_missing(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        recommendation, "DATA_PATH", str(tmp_path / "missing_background.csv")
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_fails_when_shap_dataset_does_not_match_training_hash(
    client, tmp_path, monkeypatch
):
    swapped = tmp_path / "matching_topk_labeled.csv"
    swapped.write_text(
        "tfidf_similarity,semantic_similarity\n0.1,0.2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(recommendation, "DATA_PATH", str(swapped))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_fails_when_lazy_runtime_dependencies_are_missing(
    client, monkeypatch
):
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, package=None):
        if name in {"sentence_transformers", "shap"}:
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_does_not_load_the_sentence_transformer_model(
    client, monkeypatch
):
    from app.services import semantic_matching

    def fail():
        raise AssertionError(
            "readiness must not initialise the sentence-transformer model"
        )

    monkeypatch.setattr(semantic_matching, "get_model", fail)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
