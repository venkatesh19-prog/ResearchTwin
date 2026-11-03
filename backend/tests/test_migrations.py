"""Alembic revision consistency and disposable-database migration tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import database
from app.database import Base, SchemaRevisionError, verify_schema_revision

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _head(config: Config) -> str:
    return ScriptDirectory.from_config(config).get_current_head()


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.as_posix()


def _legacy_tables():
    """The pre-Alembic schema: current tables before audit_events existed."""
    later_tables = {"audit_events", "groups", "group_memberships"}
    return [
        table
        for name, table in Base.metadata.tables.items()
        if name not in later_tables
    ]


def _seed_legacy_rows(engine) -> None:
    now = 1_760_000_000
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, role, "
                "password_hash, is_active, created_at) VALUES "
                "(1, 'legacy@example.edu', 'Legacy Student', 'student', "
                "'legacy-hash', 1, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO researchers (id, name, department) "
                "VALUES (1, 'Dr. Legacy', 'Computer Science')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO auth_sessions (id, user_id, token_hash, "
                "created_at, expires_at) VALUES "
                "(1, 1, 'legacy-token-hash', :now, :expires)"
            ),
            {"now": now, "expires": now + 3600},
        )
        connection.execute(
            text(
                "INSERT INTO student_profiles (id, user_id, research_areas, "
                "expertise, skills, projects, publications, courses, "
                "academic_details, updated_at) VALUES "
                "(1, 1, 'AI', 'ML', 'Python', '', '', '', '', :now)"
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO collaboration_requests (id, student_user_id, "
                "researcher_id, message, status, faculty_response, "
                "created_at, updated_at) VALUES "
                "(1, 1, 1, 'Legacy collaboration request', 'pending', '', "
                ":now, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO roadmap_progress (id, user_id, researcher_id, "
                "skill, milestone_index, is_completed, updated_at) VALUES "
                "(1, 1, 1, 'Python', 0, 0, :now)"
            ),
            {"now": now},
        )


def _schema(engine) -> dict:
    inspector = inspect(engine)
    return {
        table: {
            "columns": [
                (column["name"], str(column["type"]), column["nullable"])
                for column in inspector.get_columns(table)
            ],
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]), index["unique"])
                for index in inspector.get_indexes(table)
            ),
            "unique": sorted(
                (constraint["name"], tuple(constraint["column_names"]))
                for constraint in inspector.get_unique_constraints(table)
            ),
        }
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


def test_upgrade_head_matches_model_metadata(tmp_path):
    migrated_url = _sqlite_url(tmp_path / "migrated.db")
    metadata_url = _sqlite_url(tmp_path / "metadata.db")

    command.upgrade(_config(migrated_url), "head")
    Base.metadata.create_all(create_engine(metadata_url))

    assert _schema(create_engine(migrated_url)) == _schema(
        create_engine(metadata_url)
    )


def test_head_revision_has_no_autogenerate_drift(tmp_path):
    url = _sqlite_url(tmp_path / "drift.db")

    command.upgrade(_config(url), "head")

    command.check(_config(url))


def test_documented_adoption_path_stamps_baseline_then_applies_audit_migration(
    tmp_path,
):
    url = _sqlite_url(tmp_path / "legacy.db")
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=_legacy_tables())
    _seed_legacy_rows(engine)

    config = _config(url)
    head = _head(config)
    assert head == "0003_groups"

    command.stamp(config, "0001_baseline")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0001_baseline"

    command.upgrade(config, "head")

    fresh_url = _sqlite_url(tmp_path / "fresh.db")
    command.upgrade(_config(fresh_url), "head")
    fresh_schema = _schema(create_engine(fresh_url))
    migrated_schema = _schema(engine)

    assert migrated_schema == fresh_schema
    assert "audit_events" in migrated_schema

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == head
        assert connection.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT email FROM users")
        ).scalar_one() == "legacy@example.edu"
        assert connection.execute(
            text("SELECT name FROM researchers")
        ).scalar_one() == "Dr. Legacy"
        assert connection.execute(
            text("SELECT token_hash FROM auth_sessions")
        ).scalar_one() == "legacy-token-hash"
        assert connection.execute(
            text("SELECT message FROM collaboration_requests")
        ).scalar_one() == "Legacy collaboration request"
        assert connection.execute(
            text("SELECT skill FROM roadmap_progress")
        ).scalar_one() == "Python"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM researchers")
        ).scalar_one() == 1


def test_downgrade_base_on_disposable_database_removes_schema(tmp_path):
    url = _sqlite_url(tmp_path / "downgrade.db")

    command.upgrade(_config(url), "head")
    command.downgrade(_config(url), "base")

    assert inspect(create_engine(url)).get_table_names() == ["alembic_version"]


def test_unstamped_existing_database_fails_loudly(tmp_path):
    url = _sqlite_url(tmp_path / "unstamped.db")
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    with pytest.raises(Exception) as excinfo:
        command.upgrade(_config(url), "head")

    assert "already exists" in str(excinfo.value).lower()
    assert "researchers" in inspect(engine).get_table_names()


class FakePostgresSession:
    """Stand-in for a PostgreSQL session without opening a connection."""

    def __init__(self, version=None, error=None):
        self.version = version
        self.error = error

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def execute(self, statement):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(scalar_one_or_none=lambda: self.version)


def test_expected_revision_matches_the_alembic_head():
    head = _head(_config("sqlite:///" + (BACKEND_DIR / "unused.db").as_posix()))

    assert database.expected_schema_revision() == head


def test_sqlite_is_not_subject_to_the_revision_requirement(db):
    # The SQLite test database is created with create_all and is never stamped.
    assert verify_schema_revision(db) is None


def test_postgresql_at_the_reviewed_head_is_ready():
    session = FakePostgresSession(version=database.expected_schema_revision())

    assert verify_schema_revision(session) is None


@pytest.mark.parametrize("version", [None, "000000000000"])
def test_postgresql_missing_or_outdated_revision_is_rejected(version):
    with pytest.raises(SchemaRevisionError, match="migration head"):
        verify_schema_revision(FakePostgresSession(version=version))


def test_postgresql_revision_lookup_failure_is_rejected():
    session = FakePostgresSession(error=SQLAlchemyError("connection lost"))

    with pytest.raises(SchemaRevisionError, match="unavailable"):
        verify_schema_revision(session)


def test_readiness_fails_closed_when_the_revision_check_fails(client, monkeypatch):
    def fail(_db):
        raise SchemaRevisionError("not at head")

    monkeypatch.setattr("app.main.verify_schema_revision", fail)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
