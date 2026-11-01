"""Shared pytest fixtures for the ResearchTwin backend.

The database URL is set to a throwaway SQLite file *before* `app` is imported,
so tests never touch `backend/researchtwin.db`.
"""

import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TMP_DIR = Path(tempfile.mkdtemp(prefix="researchtwin-tests-"))
os.environ["DATABASE_URL"] = "sqlite:///" + (_TMP_DIR / "test.db").as_posix()
os.environ.setdefault(
    "FRONTEND_ORIGINS", "https://starlit-empanada-a323e3.netlify.app"
)
os.environ["RATE_LIMIT_HASH_SECRET"] = (
    "local-test-rate-limit-secret-not-for-production-2026"
)
os.environ["RATE_LIMIT_TRUST_CF_CONNECTING_IP"] = "false"
os.environ["RATE_LIMIT_REQUIRE_SHARED_DATABASE"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import RateLimitCounter, Researcher, User  # noqa: E402
from app.services.auth import create_session  # noqa: E402


SAMPLE_RESEARCHERS = [
    {
        "name": "Dr. Ada Lovelace",
        "department": "Computer Science and Engineering",
        "designation": "Professor",
        "experience": 12,
        "research_areas": "Artificial Intelligence, Machine Learning",
        "expertise": "Deep Learning, NLP",
        "skills": "Python, PyTorch, Transformers",
        "publications": "Transformer Models for Text Classification",
        "projects": "Semantic Search Engine",
        "profile_url": "https://example.com/ada",
    },
    {
        "name": "Dr. Grace Hopper",
        "department": "Information Technology",
        "designation": "Associate Professor",
        "experience": 9,
        "research_areas": "Cybersecurity, Distributed Systems",
        "expertise": "Network Security, Compilers",
        "skills": "Python, Linux, Wireshark",
        "publications": "Secure Network Compilers",
        "projects": "Intrusion Detection Platform",
        "profile_url": "https://example.com/grace",
    },
    {
        "name": "Dr. Alan Turing",
        "department": "Computer Science and Engineering",
        "designation": "Professor",
        "experience": 15,
        "research_areas": "Algorithms, Optimization, Machine Learning",
        "expertise": "Combinatorial Optimization",
        "skills": "C++, Python, MATLAB",
        "publications": "Optimization for Intelligent Systems",
        "projects": "Resource Allocation Optimizer",
        "profile_url": "https://example.com/alan",
    },
]


def register_test_account(client, role: str = "student", email: str | None = None):
    email = email or f"{role}-{uuid.uuid4().hex}@example.test"
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "TestPassword123!",
            "full_name": f"Test {role.title()}",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return (
        {"Authorization": f"Bearer {response.json()['access_token']}"},
        response.json()["user"],
    )


@pytest.fixture()
def admin_headers(db):
    admin = User(
        email=f"operator-{uuid.uuid4().hex}@example.test",
        full_name="Test Operator",
        role="admin",
        password_hash="provisioned-out-of-band-for-test-only",
        is_active=True,
        created_at=int(time.time()),
    )
    db.add(admin)
    db.commit()
    token, _ = create_session(db, admin)
    return {"Authorization": f"Bearer {token}"}


STUDENT_PROFILE = {
    "research_areas": "Artificial Intelligence, Machine Learning",
    "expertise": "Deep Learning, NLP",
    "skills": "Python, PyTorch, Transformers",
    "projects": "Semantic search engine",
    "publications": "Transformer models",
    "top_k": 5,
}


@pytest.fixture(autouse=True)
def reset_model_caches():
    """Keep module-level caches from leaking between tests."""
    from app.services import recommendation

    recommendation._model_bundle = None
    recommendation._shap_explainer = None

    from app.services import semantic_matching

    semantic_matching.get_model.cache_clear()

    db = SessionLocal()
    try:
        db.query(RateLimitCounter).delete()
        db.commit()
    finally:
        db.close()

    yield

    recommendation._model_bundle = None
    recommendation._shap_explainer = None
    semantic_matching.get_model.cache_clear()
    db = SessionLocal()
    try:
        db.query(RateLimitCounter).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def app_instance():
    return app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def raw_client():
    """Client that returns 500 responses instead of re-raising server errors."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def empty_db():
    """Ensure the researchers table exists and is empty for this test."""
    session = SessionLocal()
    try:
        session.query(Researcher).delete()
        session.commit()
    finally:
        session.close()
    return None


@pytest.fixture()
def seeded_db(empty_db):
    """Insert three researchers; remove them afterwards."""
    session = SessionLocal()
    try:
        session.add_all(Researcher(**row) for row in SAMPLE_RESEARCHERS)
        session.commit()
    finally:
        session.close()

    yield

    session = SessionLocal()
    try:
        session.query(Researcher).delete()
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def engine_under_test():
    return engine


def make_semantic_results(researchers, scores=None):
    """Deterministic semantic results shaped like the real service output."""
    return [
        {
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department,
            "semantic_score": (
                scores[i] if scores is not None else round(0.9 - 0.1 * i, 4)
            ),
            "semantic_available": True,
        }
        for i, researcher in enumerate(researchers)
    ]


@pytest.fixture()
def patch_semantic(monkeypatch):
    """Replace the embedding model with a deterministic stub for fast tests."""

    def _patch(scores=None, results_factory=None):
        recorded = {"calls": 0}

        def fake(student_profile, researchers):
            researchers = list(researchers)
            recorded["calls"] += 1
            recorded["researchers"] = researchers
            recorded["student_profile"] = student_profile
            if results_factory is not None:
                return results_factory(student_profile, researchers)
            return make_semantic_results(researchers, scores)

        monkeypatch.setattr(
            "app.services.recommendation.calculate_semantic_similarity",
            fake,
        )
        return recorded

    return _patch
