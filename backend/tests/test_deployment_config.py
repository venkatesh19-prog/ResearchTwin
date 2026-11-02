"""Deployment configuration must install the verified ONNX runtime."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_build_installs_pinned_runtime_and_fetches_onnx_model():
    render = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")
    requirements = (REPO_ROOT / "backend" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "constraints.txt" in render
    assert "scripts/fetch_embedding_model.py" in render
    assert "torch" not in render
    assert "onnxruntime==" in requirements
    assert "sentence-transformers" not in requirements


def test_render_runs_one_worker_and_bounds_recommendation_work():
    render = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "--workers 1" in render
    assert re.search(
        r"key: RECOMMENDATION_MAX_CONCURRENCY\s+value: \"2\"", render
    )
    assert re.search(
        r"key: RATE_LIMIT_TRUST_CF_CONNECTING_IP\s+value: \"false\"", render
    )
    assert "RATE_LIMIT_TRUSTED_PROXY_CIDRS" in render
