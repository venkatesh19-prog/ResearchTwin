"""Database URL normalization and session lifecycle tests."""

import pytest
from sqlalchemy import text

from app import database
from app.models import Researcher


def test_default_url_points_at_backend_sqlite_file(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url = database.resolve_database_url(None)

    assert url.startswith("sqlite:///")
    assert url.endswith("/backend/researchtwin.db")


def test_legacy_postgres_scheme_is_routed_through_psycopg3():
    url = database.resolve_database_url(
        "postgres://rt:secret@db.example.com:5432/researchtwin"
    )

    assert url == (
        "postgresql+psycopg://rt:secret@db.example.com:5432/researchtwin"
    )


def test_postgresql_scheme_is_routed_through_psycopg3():
    url = database.resolve_database_url(
        "postgresql://rt:secret@db.example.com:5432/researchtwin"
    )

    assert url == (
        "postgresql+psycopg://rt:secret@db.example.com:5432/researchtwin"
    )


def test_existing_psycopg_scheme_is_left_unchanged():
    raw = "postgresql+psycopg://rt:secret@db.example.com:5432/researchtwin"

    assert database.resolve_database_url(raw) == raw


def test_sqlite_url_is_left_unchanged():
    raw = "sqlite:///C:/tmp/researchtwin.db"

    assert database.resolve_database_url(raw) == raw


def test_surrounding_whitespace_is_removed():
    assert (
        database.resolve_database_url("  sqlite:///tmp/x.db \n")
        == "sqlite:///tmp/x.db"
    )


def test_empty_string_falls_back_to_default_file(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert database.resolve_database_url("   ") == (
        database.resolve_database_url(None)
    )


def test_engine_under_test_uses_sqlite(engine_under_test):
    assert engine_under_test.dialect.name == "sqlite"


def test_engine_has_pre_ping_enabled(engine_under_test):
    assert engine_under_test.pool._pre_ping is True


def test_get_db_yields_a_usable_session_and_closes_it():
    generator = database.get_db()

    session = next(generator)
    assert session.execute(text("SELECT 1")).scalar() == 1
    assert session.is_active is True

    with pytest.raises(StopIteration):
        next(generator)

    assert session.in_transaction() is False


def test_session_round_trip(db):
    researcher = Researcher(name="Temporary Test Researcher", department="CS")
    db.add(researcher)
    db.commit()
    db.refresh(researcher)

    assert researcher.id is not None

    loaded = (
        db.query(Researcher)
        .filter(Researcher.name == "Temporary Test Researcher")
        .one()
    )
    assert loaded.id == researcher.id

    db.delete(loaded)
    db.commit()

    assert (
        db.query(Researcher)
        .filter(Researcher.name == "Temporary Test Researcher")
        .count()
        == 0
    )


def test_sqlite_rejects_orphaned_progress(db):
    from sqlalchemy.exc import IntegrityError
    from app.models import RoadmapProgress

    db.add(RoadmapProgress(
        user_id=987654321, researcher_id=987654321, skill="python",
        milestone_index=0, is_completed=True, updated_at=1,
    ))
    try:
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()


def test_researcher_delete_cascades_owned_workflow_rows(db, client, seeded_db):
    from app.models import CollaborationRequest, FacultyResearcherLink, RoadmapProgress
    from conftest import register_test_account

    _, student = register_test_account(client)
    _, faculty = register_test_account(client, role="faculty")
    researcher = db.query(Researcher).first()
    researcher_id = researcher.id
    db.add_all([
        CollaborationRequest(student_user_id=student["id"], researcher_id=researcher_id,
                             message="Research interest", created_at=1, updated_at=1),
        FacultyResearcherLink(faculty_user_id=faculty["id"], researcher_id=researcher_id,
                              created_at=1),
        RoadmapProgress(user_id=student["id"], researcher_id=researcher_id,
                        skill="pytorch", milestone_index=0, updated_at=1),
    ])
    db.commit()
    db.delete(researcher)
    db.commit()
    for model in (CollaborationRequest, FacultyResearcherLink, RoadmapProgress):
        assert db.query(model).filter(model.researcher_id == researcher_id).count() == 0
