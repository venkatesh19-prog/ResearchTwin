"""Alembic revision consistency and disposable-database migration tests."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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


def _engine(url: str):
    engine = create_engine(url)
    database.enforce_sqlite_foreign_keys(engine)
    return engine


def _legacy_tables():
    """The pre-Alembic schema: current tables before audit_events existed."""
    later_tables = {
        "audit_events",
        "groups",
        "group_memberships",
        "researcher_verifications",
        "collaboration_workspaces",
        "workspace_members",
        "workspace_tasks",
        "workspace_comments",
        "workspace_milestones",
        "research_teams",
        "research_team_members",
        "research_team_invitations",
        "opportunities",
        "opportunity_applications",
        "research_cluster_runs",
        "research_cluster_assignments",
        "literature_entries",
        "research_proposals",
        "proposal_sections",
        "proposal_collaborators",
        "proposal_versions",
        "proposal_citations",
        "thesis_records",
        "thesis_milestones",
        "thesis_progress_events",
        "publication_submissions",
        "publication_revisions",
        "publication_status_events",
        "institutions",
        "institution_memberships",
        "research_labs",
        "research_lab_members",
        "interuniversity_collaborations",
        "search_history",
    }
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
    Base.metadata.create_all(_engine(metadata_url))

    assert _schema(_engine(migrated_url)) == _schema(_engine(metadata_url))


def test_head_revision_has_no_autogenerate_drift(tmp_path):
    url = _sqlite_url(tmp_path / "drift.db")

    command.upgrade(_config(url), "head")

    command.check(_config(url))


def test_documented_adoption_path_stamps_baseline_then_applies_audit_migration(
    tmp_path,
):
    url = _sqlite_url(tmp_path / "legacy.db")
    engine = _engine(url)
    Base.metadata.create_all(engine, tables=_legacy_tables())
    _seed_legacy_rows(engine)

    config = _config(url)
    head = _head(config)
    assert head == "0012_search_history"

    command.stamp(config, "0001_baseline")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0001_baseline"

    command.upgrade(config, "head")

    fresh_url = _sqlite_url(tmp_path / "fresh.db")
    command.upgrade(_config(fresh_url), "head")
    fresh_schema = _schema(_engine(fresh_url))
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


def test_alembic_migration_connection_enforces_sqlite_foreign_keys(
    tmp_path, monkeypatch
):
    versions = tmp_path / "probe_versions"
    versions.mkdir()
    (versions / "0013_fk_probe.py").write_text(
        '"""Probe the migration connection pragma."""\n\n'
        "import os\n\n"
        "from alembic import op\n\n"
        'revision = "0013_fk_probe"\n'
        'down_revision = "0012_search_history"\n'
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade() -> None:\n"
        "    value = op.get_bind().exec_driver_sql(\n"
        '        "PRAGMA foreign_keys"\n'
        "    ).scalar()\n"
        "    with open(os.environ[\"RT_FK_PROBE\"], \"w\", encoding=\"utf-8\") as handle:\n"
        "        handle.write(str(value))\n\n\n"
        "def downgrade() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    config = _config(_sqlite_url(tmp_path / "fk_probe.db"))
    config.set_main_option(
        "version_locations",
        os.pathsep.join(
            [
                str(BACKEND_DIR / "migrations" / "versions"),
                str(versions),
            ]
        ),
    )
    probe = tmp_path / "pragma.txt"
    monkeypatch.setenv("RT_FK_PROBE", str(probe))

    command.upgrade(config, "head")

    assert probe.read_text(encoding="utf-8") == "1"


def test_complete_migration_chain_keeps_foreign_keys_valid(tmp_path):
    url = _sqlite_url(tmp_path / "fk_chain.db")
    engine = _engine(url)
    config = _config(url)

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


def test_migration_test_engine_enforces_foreign_keys_on_writes(tmp_path):
    engine = _engine(_sqlite_url(tmp_path / "fk_write.db"))
    Base.metadata.create_all(engine)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO researcher_verifications "
                    "(researcher_id, status, evidence_reference, note, "
                    "review_note, submitted_at, created_at) "
                    "VALUES (9999, 'pending', '', '', '', 1, 1)"
                )
            )


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


REDUNDANT_SINGLE_COLUMN_INDEXES = {
    "ix_group_memberships_group_id",
    "ix_literature_entries_owner_user_id",
    "ix_research_labs_institution_id",
    "ix_roadmap_progress_user_id",
    "ix_proposal_collaborators_proposal_id",
    "ix_proposal_versions_proposal_id",
    "ix_publication_revisions_submission_id",
    "ix_research_cluster_assignments_run_id",
    "ix_research_lab_members_lab_id",
    "ix_research_team_members_team_id",
    "ix_proposal_citations_proposal_id",
    "ix_workspace_members_workspace_id",
}

PARTIAL_UNIQUE_INDEXES = {
    "collaboration_requests": "ix_collaboration_requests_student_user_id",
    "researcher_verifications": "ix_researcher_verifications_researcher_id",
    "opportunity_applications": "ix_opportunity_applications_opportunity_id",
    "research_team_invitations": "ix_research_team_invitations_team_id",
}


def test_metadata_declares_no_redundant_primary_key_indexes():
    for table in Base.metadata.sorted_tables:
        if [column.name for column in table.primary_key.columns] == ["id"]:
            assert not table.c.id.index
        indexed = {
            index.name
            for index in table.indexes
            if [column.name for column in index.columns] == ["id"]
        }
        assert indexed == set()

    declared = {
        index.name
        for table in Base.metadata.sorted_tables
        for index in table.indexes
    }
    assert declared.isdisjoint(REDUNDANT_SINGLE_COLUMN_INDEXES)
    assert set(PARTIAL_UNIQUE_INDEXES.values()) <= declared


def test_upgrade_head_drops_redundant_indexes_but_keeps_keys(tmp_path):
    url = _sqlite_url(tmp_path / "indexes.db")
    command.upgrade(_config(url), "head")
    engine = _engine(url)
    inspector = inspect(engine)

    for table in Base.metadata.sorted_tables:
        names = {index["name"] for index in inspector.get_indexes(table.name)}
        assert f"ix_{table.name}_id" not in names
        expected_pk = [
            column.name for column in table.primary_key.columns
        ]
        assert (
            inspector.get_pk_constraint(table.name)["constrained_columns"]
            == expected_pk
        )

    for table_name, index_name in PARTIAL_UNIQUE_INDEXES.items():
        names = {
            index["name"]
            for index in inspector.get_indexes(table_name)
        }
        assert index_name in names

    for table_name in (
        "group_memberships",
        "literature_entries",
        "research_labs",
        "roadmap_progress",
        "proposal_collaborators",
        "proposal_versions",
        "publication_revisions",
        "research_cluster_assignments",
        "research_lab_members",
        "research_team_members",
        "proposal_citations",
        "workspace_members",
    ):
        names = {
            index["name"] for index in inspector.get_indexes(table_name)
        }
        assert names.isdisjoint(REDUNDANT_SINGLE_COLUMN_INDEXES)

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, role, "
                "password_hash, is_active, created_at) VALUES "
                "(1, 'unique@example.edu', 'Unique', 'student', "
                "'hash', 1, 1)"
            )
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, full_name, role, "
                    "password_hash, is_active, created_at) VALUES "
                    "(1, 'other@example.edu', 'Other', 'student', "
                    "'hash', 1, 1)"
                )
            )


PENDING_INDEX = "uq_collaboration_requests_pending"
BEFORE_REPAIR_BATCH_2 = "0009_research_labs"


def _seed_request_actors(engine) -> None:
    now = 1_760_000_000
    with engine.begin() as connection:
        for user_id in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, full_name, role, "
                    "password_hash, is_active, created_at) VALUES "
                    "(:id, :email, 'Student', 'student', 'hash', 1, :now)"
                ),
                {
                    "id": user_id,
                    "email": f"student{user_id}@example.edu",
                    "now": now,
                },
            )
        connection.execute(
            text(
                "INSERT INTO researchers (id, name, department) "
                "VALUES (1, 'Dr. Paired', 'Computer Science')"
            )
        )


def _insert_request(engine, request_id, student_user_id, status) -> None:
    now = 1_760_000_000
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO collaboration_requests (id, student_user_id, "
                "researcher_id, message, status, faculty_response, "
                "created_at, updated_at) VALUES "
                "(:id, :student, 1, 'May I join?', :status, '', :now, :now)"
            ),
            {
                "id": request_id,
                "student": student_user_id,
                "status": status,
                "now": now,
            },
        )


def _pending_index_names(engine):
    return {
        index["name"] for index in inspect(engine).get_indexes(
            "collaboration_requests"
        )
    }


def test_0010_adds_the_pending_index_when_no_pair_is_duplicated(tmp_path):
    url = _sqlite_url(tmp_path / "unique-pending.db")
    config = _config(url)
    command.upgrade(config, BEFORE_REPAIR_BATCH_2)
    engine = _engine(url)
    _seed_request_actors(engine)
    _insert_request(engine, 1, 1, "pending")
    _insert_request(engine, 2, 1, "rejected")
    _insert_request(engine, 3, 2, "pending")

    command.upgrade(config, "0010_repair_batch_2")

    assert PENDING_INDEX in _pending_index_names(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM collaboration_requests")
        ).scalar_one() == 3


def test_0010_refuses_the_index_when_a_pending_pair_is_duplicated(tmp_path):
    url = _sqlite_url(tmp_path / "duplicate-pending.db")
    config = _config(url)
    command.upgrade(config, BEFORE_REPAIR_BATCH_2)
    engine = _engine(url)
    _seed_request_actors(engine)
    _insert_request(engine, 1, 1, "pending")
    _insert_request(engine, 2, 1, "pending")

    with pytest.raises(RuntimeError) as refused:
        command.upgrade(config, "0010_repair_batch_2")

    message = str(refused.value)
    assert "student 1" in message
    assert "researcher 1" in message
    assert "2 pending" in message
    assert "alembic upgrade head" in message

    assert PENDING_INDEX not in _pending_index_names(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == BEFORE_REPAIR_BATCH_2
        assert connection.execute(
            text(
                "SELECT id, status FROM collaboration_requests ORDER BY id"
            )
        ).fetchall() == [(1, "pending"), (2, "pending")]


def test_0010_proceeds_once_a_duplicated_pair_is_decided(tmp_path):
    url = _sqlite_url(tmp_path / "resolved-pending.db")
    config = _config(url)
    command.upgrade(config, BEFORE_REPAIR_BATCH_2)
    engine = _engine(url)
    _seed_request_actors(engine)
    _insert_request(engine, 1, 1, "pending")
    _insert_request(engine, 2, 1, "pending")

    with pytest.raises(RuntimeError):
        command.upgrade(config, "0010_repair_batch_2")

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE collaboration_requests SET status = 'rejected' "
                "WHERE id = 2"
            )
        )

    command.upgrade(config, "0010_repair_batch_2")

    assert PENDING_INDEX in _pending_index_names(engine)
