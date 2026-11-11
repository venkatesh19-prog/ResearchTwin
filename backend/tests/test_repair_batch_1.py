"""Regression tests for Repair Batch 1 (integrity, deletion, locking, transactions)."""

import json
import time
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.requests import Request

from app.database import SessionLocal, get_db
from app.main import app
from app.models import AuditEvent, RoadmapProgress
from app.services import rate_limit, research_outputs

from conftest import register_test_account


RESEARCHER = {
    "name": "Dr. Repair Batch",
    "department": "Computer Science",
    "designation": "Professor",
    "experience": 7,
    "research_areas": "Reliability",
    "expertise": "Databases",
    "skills": "Python, SQL",
    "publications": "Repair batch testing",
    "projects": "Integrity guards",
    "profile_url": "https://example.edu/repair-batch",
}


def _override_commit(error):
    def _dependency():
        session = SessionLocal()

        def fail():
            raise error

        session.commit = fail
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _dependency


def _clear_override():
    app.dependency_overrides.pop(get_db, None)


def test_integrity_error_maps_to_conflict_without_leaking_internals(
    client, admin_headers
):
    _override_commit(
        IntegrityError(
            "INSERT INTO researchers (name) VALUES ('leaked-value')",
            {},
            Exception("UNIQUE constraint failed: researchers.name"),
        )
    )
    try:
        response = client.post("/researchers/", json=RESEARCHER, headers=admin_headers)
    finally:
        _clear_override()

    assert response.status_code == 409
    assert response.json() == {"detail": "Request conflicts with existing data"}
    lowered = response.text.lower()
    for token in ("insert into", "unique constraint", "researchers.name", "sqlite"):
        assert token not in lowered


def test_operational_error_remains_a_database_availability_failure(
    client, admin_headers
):
    _override_commit(OperationalError("SELECT 1", {}, Exception("connection refused")))
    try:
        response = client.post("/researchers/", json=RESEARCHER, headers=admin_headers)
    finally:
        _clear_override()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "select 1" not in response.text.lower()
    assert "connection refused" not in response.text.lower()


def test_researcher_with_dependent_records_is_not_deleted(
    client, seeded_db, admin_headers, db
):
    _, student = register_test_account(client)
    researcher_id = client.get("/researchers/").json()[0]["id"]
    db.add(
        RoadmapProgress(
            user_id=student["id"],
            researcher_id=researcher_id,
            skill="Python",
            milestone_index=0,
            is_completed=False,
            updated_at=int(time.time()),
        )
    )
    db.commit()

    response = client.delete(f"/researchers/{researcher_id}", headers=admin_headers)

    assert response.status_code == 409
    assert "dependent" in response.json()["detail"].lower()
    assert client.get(f"/researchers/{researcher_id}").status_code == 200
    db.expire_all()
    assert db.query(RoadmapProgress).filter_by(researcher_id=researcher_id).count() == 1


def test_researcher_delete_without_dependents_records_an_admin_audit_event(
    client, seeded_db, admin_headers, db
):
    target = client.get("/researchers/").json()[-1]
    researcher_id = target["id"]

    response = client.delete(f"/researchers/{researcher_id}", headers=admin_headers)

    assert response.status_code == 200
    db.expire_all()
    event = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == "researcher.delete",
            AuditEvent.target_type == "researcher",
            AuditEvent.target_id == researcher_id,
        )
        .one()
    )
    assert event.actor_user_id is not None
    assert json.loads(event.detail)["name"] == target["name"]
    assert client.get(f"/researchers/{researcher_id}").status_code == 404


def test_proposal_version_lock_statement_uses_a_row_lock():
    statement = research_outputs.proposal_version_lock_statement(42)
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "proposal" in sql.lower()
    assert "for update" in sql.lower()


def test_publication_revision_lock_statement_uses_a_row_lock():
    statement = research_outputs.publication_revision_lock_statement(7)
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "publication_submissions" in sql.lower()
    assert "for update" in sql.lower()


class _FakeLimiterSession:
    instances = []

    def __init__(self, bind=None):
        self.bind = bind
        self.committed = False
        self.closed = False
        self.statements = []
        _FakeLimiterSession.instances.append(self)

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(scalar_one=lambda: 1)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class _FakeRequestSession:
    def __init__(self):
        self.commits = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def get_bind(self):
        return self.bind

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_postgresql_rate_limit_uses_an_independent_transaction(monkeypatch):
    _FakeLimiterSession.instances.clear()
    monkeypatch.setattr(rate_limit, "Session", _FakeLimiterSession)
    request_session = _FakeRequestSession()

    rate_limit.enforce_rate_limit(
        request_session,
        _request(),
        scope="repair-batch",
        identities=(("user", "1"),),
        limit=10,
        window_seconds=60,
    )

    assert request_session.commits == 0
    limiter = _FakeLimiterSession.instances[-1]
    assert limiter.bind is request_session.bind
    assert limiter.committed is True
    assert limiter.closed is True


def test_rate_limit_still_rejects_requests_over_the_limit(monkeypatch):
    class _ExceededSession(_FakeLimiterSession):
        def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(scalar_one=lambda: 11)

    monkeypatch.setattr(rate_limit, "Session", _ExceededSession)
    request_session = _FakeRequestSession()

    with pytest.raises(rate_limit.HTTPException) as excinfo:
        rate_limit.enforce_rate_limit(
            request_session,
            _request(),
            scope="repair-batch",
            identities=(("user", "1"),),
            limit=10,
            window_seconds=60,
        )

    assert excinfo.value.status_code == 429
    assert int(excinfo.value.headers["Retry-After"]) >= 1
    assert request_session.commits == 0
