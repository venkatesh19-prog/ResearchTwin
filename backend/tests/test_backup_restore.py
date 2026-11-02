"""Backup, verification, and restore drills run only on disposable databases."""

import json
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    AuditEvent,
    AuthSession,
    CollaborationRequest,
    Researcher,
    StudentProfile,
    User,
)
from scripts.database_backup import (
    BackupError,
    _sha256,
    create_sqlite_backup,
    main,
    restore_sqlite_backup,
    verify_backup,
)


@pytest.fixture()
def populated_db(tmp_path):
    path = tmp_path / "source.db"
    engine = create_engine("sqlite:///" + path.as_posix())
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = int(time.time())
    try:
        student = User(
            email="student@example.edu",
            full_name="Student One",
            role="student",
            password_hash="hashed",
            is_active=True,
            created_at=now,
        )
        researcher = Researcher(name="Dr. Ada Lovelace", department="CS")
        session.add_all([student, researcher])
        session.flush()
        session.add(StudentProfile(user_id=student.id, research_areas="ML", updated_at=now))
        session.add(
            AuthSession(
                user_id=student.id,
                token_hash="a" * 64,
                created_at=now - 60,
                expires_at=now + 3600,
            )
        )
        session.add(
            AuthSession(
                user_id=student.id,
                token_hash="b" * 64,
                created_at=now - 7200,
                expires_at=now - 3600,
            )
        )
        session.add(
            CollaborationRequest(
                student_user_id=student.id,
                researcher_id=researcher.id,
                message="Happy to help",
                status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AuditEvent(
                actor_user_id=student.id,
                action="account.deactivate",
                target_type="user",
                target_id=student.id,
                detail="{}",
                created_at=now,
            )
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()
    return path


def test_backup_copies_data_without_touching_the_source(populated_db, tmp_path):
    source_hash = _sha256(populated_db)
    destination = tmp_path / "backups" / "snapshot.db"

    manifest = create_sqlite_backup(populated_db, destination)

    assert source_hash == _sha256(populated_db)
    assert destination.is_file()
    assert manifest["integrity_ok"] is True
    assert manifest["sha256"] == _sha256(destination)
    assert manifest["table_counts"]["users"] == 1
    assert manifest["table_counts"]["collaboration_requests"] == 1
    assert manifest["active_sessions"] == 1
    assert manifest["expired_sessions"] == 1
    manifest_file = destination.with_name(destination.name + ".manifest.json")
    assert json.loads(manifest_file.read_text(encoding="utf-8"))["sha256"] == manifest["sha256"]


def test_backup_refuses_to_overwrite_or_alias_the_source(populated_db, tmp_path):
    existing = tmp_path / "existing.db"
    existing.write_bytes(b"keep me")

    with pytest.raises(BackupError, match="overwrite"):
        create_sqlite_backup(populated_db, existing)
    with pytest.raises(BackupError, match="differ"):
        create_sqlite_backup(populated_db, populated_db)
    assert existing.read_bytes() == b"keep me"


def test_restore_drill_uses_a_new_path_and_matches_counts(populated_db, tmp_path):
    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)

    target = tmp_path / "restore-drill.db"
    restored = restore_sqlite_backup(backup, target)

    assert restored["integrity_ok"] is True
    assert restored["table_counts"]["users"] == 1
    assert restored["table_counts"]["auth_sessions"] == 2
    with pytest.raises(BackupError, match="existing"):
        restore_sqlite_backup(backup, target)


def test_corrupted_backup_is_rejected_before_restore(populated_db, tmp_path):
    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)
    with backup.open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(BackupError, match="checksum"):
        verify_backup(backup)
    with pytest.raises(BackupError, match="checksum"):
        restore_sqlite_backup(backup, tmp_path / "restore.db")


def test_non_database_file_is_rejected(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a sqlite database")

    with pytest.raises(BackupError, match="Not a valid SQLite database"):
        verify_backup(junk)


def test_manifestless_backup_verifies_but_restore_requires_opt_in(
    populated_db, tmp_path
):
    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)
    backup.with_name(backup.name + ".manifest.json").unlink()

    verified = verify_backup(backup)

    assert verified["integrity_ok"] is True
    assert verified["manifest"] is None

    refused_target = tmp_path / "refused.db"
    with pytest.raises(BackupError, match="manifest"):
        restore_sqlite_backup(backup, refused_target)
    assert not refused_target.exists()

    target = tmp_path / "legacy-restore.db"
    restored = restore_sqlite_backup(backup, target, allow_manifestless=True)

    assert restored["integrity_ok"] is True
    assert restored["table_counts"]["users"] == 1


def test_restore_cli_requires_the_manifest_opt_in(populated_db, tmp_path, capsys):
    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)
    backup.with_name(backup.name + ".manifest.json").unlink()
    target = tmp_path / "legacy-cli.db"

    assert main(["restore", "--backup", str(backup), "--target", str(target)]) == 2
    assert "manifest" in capsys.readouterr().err
    assert not target.exists()

    assert (
        main(
            [
                "restore",
                "--backup",
                str(backup),
                "--target",
                str(target),
                "--allow-manifestless",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["integrity_ok"] is True


def test_status_cli_reports_capacity(populated_db, capsys):
    exit_code = main(["status", "--source", str(populated_db)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["integrity_ok"] is True
    assert output["size_bytes"] > 0
    assert output["table_counts"]["users"] == 1


def test_postgresql_archive_is_rejected_before_target_creation(populated_db, tmp_path):
    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)
    manifest_file = backup.with_name(backup.name + ".manifest.json")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest["format"] = "pg_dump-custom"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    target = tmp_path / "restore-pg.db"

    with pytest.raises(BackupError, match="PostgreSQL"):
        restore_sqlite_backup(backup, target)

    assert not target.exists()


def test_non_sqlite_archive_is_rejected_before_target_creation(tmp_path):
    archive = tmp_path / "pg.dump"
    archive.write_bytes(b"PGDMP" + b"\x00" * 64)
    target = tmp_path / "restore-junk.db"

    with pytest.raises(BackupError, match="Unsupported backup format"):
        restore_sqlite_backup(archive, target)

    assert not target.exists()


def test_restore_cli_rejects_a_postgresql_archive(populated_db, tmp_path, capsys):
    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)
    backup.with_name(backup.name + ".manifest.json").write_text(
        json.dumps({"format": "pg_dump-custom", "sha256": _sha256(backup)}),
        encoding="utf-8",
    )
    target = tmp_path / "restore-cli.db"

    exit_code = main(["restore", "--backup", str(backup), "--target", str(target)])
    stderr = capsys.readouterr().err

    assert exit_code == 2
    assert "SQLite backups only" in stderr
    assert not target.exists()


def test_failed_restore_removes_the_partial_target(populated_db, tmp_path, monkeypatch):
    from scripts import database_backup

    backup = tmp_path / "snapshot.db"
    create_sqlite_backup(populated_db, backup)
    target = tmp_path / "restore-failure.db"
    real_inspect = database_backup.inspect_sqlite

    def failing_inspect(path):
        if path == target:
            raise RuntimeError("simulated post-copy failure")
        return real_inspect(path)

    monkeypatch.setattr(database_backup, "inspect_sqlite", failing_inspect)

    with pytest.raises(RuntimeError, match="simulated"):
        restore_sqlite_backup(backup, target)

    assert not target.exists()
