"""Deployment configuration must install the verified CPU-only runtime."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_build_installs_cpu_torch_with_constraints():
    text = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "download.pytorch.org/whl/cpu" in text
    assert "constraints.txt" in text
