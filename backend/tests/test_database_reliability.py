"""Non-destructive database reliability tests.

These tests never open `backend/researchtwin.db`; `conftest.py` points
DATABASE_URL at a throwaway SQLite file before the app is imported.
"""

import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base, SessionLocal, get_db
from app.main import app
from app.models import Researcher
from app.services import recommendation

from conftest import STUDENT_PROFILE, register_test_account

RECOMMENDATIONS_ENDPOINT = "/students/me/recommendations"


def _saved_student_headers(client):
    headers, _ = register_test_account(client)
    response = client.put(
        "/students/me/profile",
        json={key: value for key, value in STUDENT_PROFILE.items() if key != "top_k"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return headers


class BrokenSession:
    """Session stand-in whose every query fails like an unreachable database."""

    def __init__(self):
        self.error = OperationalError(
            "SELECT 1", {}, Exception("database is unavailable")
        )

    def query(self, *args, **kwargs):
        raise self.error

    def execute(self, *args, **kwargs):
        raise self.error

    def close(self):
        pass


@pytest.fixture()
def broken_db():
    def _override():
        yield BrokenSession()

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)


def test_create_all_is_idempotent_and_preserves_existing_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'idempotent.db'}")
    Base.metadata.create_all(bind=engine)

    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        session.add(Researcher(name="Existing Researcher", department="CS"))
        session.commit()

    Base.metadata.create_all(bind=engine)

    with session_factory() as session:
        assert session.query(Researcher).count() == 1
        assert session.query(Researcher).one().name == "Existing Researcher"

    engine.dispose()


def test_create_all_fails_fast_when_database_file_cannot_be_opened(tmp_path):
    unreachable = tmp_path / "missing" / "nested" / "x.db"
    engine = create_engine(f"sqlite:///{unreachable}")

    with pytest.raises(OperationalError):
        Base.metadata.create_all(bind=engine)

    engine.dispose()


def test_get_db_rolls_back_and_closes_when_request_raises():
    generator = database.get_db()
    session = next(generator)
    session.execute(text("SELECT 1"))
    assert session.in_transaction() is True

    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("handler failed"))

    assert session.in_transaction() is False


def test_health_reports_unhealthy_when_database_is_unavailable(
    raw_client, broken_db
):
    response = raw_client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}


def test_researcher_list_returns_503_when_database_is_unavailable(
    raw_client, broken_db
):
    response = raw_client.get("/researchers/")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"


def test_recommendations_return_503_when_database_is_unavailable(
    raw_client, broken_db
):
    # A valid token ensures authentication reaches the overridden, failing DB.
    from app.database import SessionLocal
    from app.models import User
    from app.services.auth import create_session

    db = SessionLocal()
    try:
        user = User(
            email=f"broken-db-{uuid.uuid4().hex}@example.test",
            full_name="Broken DB Student",
            role="student",
            password_hash="test-only",
            is_active=True,
            created_at=int(time.time()),
        )
        db.add(user)
        db.commit()
        token, _ = create_session(db, user)
    finally:
        db.close()

    response = raw_client.post(
        RECOMMENDATIONS_ENDPOINT,
        json={"top_k": 5},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"


def test_recommendations_with_no_researchers_return_empty_list(
    client, empty_db
):
    headers = _saved_student_headers(client)
    response = client.post(
        RECOMMENDATIONS_ENDPOINT, json={"top_k": 5}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_recommendation_ids_and_explanations_match_database_rows(
    client, seeded_db, patch_semantic
):
    patch_semantic()

    headers = _saved_student_headers(client)
    response = client.post(
        RECOMMENDATIONS_ENDPOINT, json={"top_k": 5}, headers=headers
    )
    assert response.status_code == 200
    items = response.json()["recommendations"]

    session = SessionLocal()
    try:
        rows = {row.id: row for row in session.query(Researcher).all()}
    finally:
        session.close()

    ids = [item["researcher_id"] for item in items]
    assert len(ids) == len(set(ids)), "duplicate researcher ids in response"

    for item in items:
        row = rows.get(item["researcher_id"])
        assert row is not None, f"unknown researcher id {item['researcher_id']}"
        assert item["name"] == row.name
        assert item["department"] == row.department

        explained_features = {
            entry["feature"]
            for entry in item["explanation"]["all_contributions"]
        }
        assert explained_features == set(recommendation.EXPECTED_FEATURES)
        assert len(item["explanation"]["all_contributions"]) == len(
            recommendation.EXPECTED_FEATURES
        )
