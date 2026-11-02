"""Consistent backups, verification, and restore drills for ResearchTwin data.

SQLite backups use the sqlite3 online-backup API, so they are safe while the
application is running. PostgreSQL backups shell out to ``pg_dump`` and never
connect through the application. Restores always write to a new path; this tool
refuses to overwrite an existing database. PostgreSQL restores stay a reviewed
manual operation (see ``DISASTER_RECOVERY.md``).

Usage (run from ``backend``):

    python scripts/database_backup.py status --source researchtwin-demo.db
    python scripts/database_backup.py backup --source researchtwin-demo.db \
        --destination ../backups/researchtwin-demo-$(date +%F).db
    python scripts/database_backup.py verify --backup ../backups/researchtwin-demo-$(date +%F).db
    python scripts/database_backup.py restore --backup ../backups/researchtwin-demo-$(date +%F).db \
        --target ../restore-drill.db
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.engine import make_url  # noqa: E402

from app.db_url import resolve_database_url  # noqa: E402


class BackupError(RuntimeError):
    """A backup or restore step could not be completed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(backup: Path) -> Path:
    return backup.with_name(backup.name + ".manifest.json")


def _readonly_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro"


def sqlite_path(source: str | os.PathLike[str] | None = None) -> Path:
    """Resolve a SQLite file path from an explicit path or the configured URL."""
    if source is not None:
        return Path(source).expanduser().resolve()

    parsed = make_url(resolve_database_url())
    if parsed.drivername != "sqlite":
        raise BackupError(
            "The configured database is PostgreSQL; pass --database-url for a "
            "pg_dump backup or review DISASTER_RECOVERY.md"
        )
    if not parsed.database:
        raise BackupError("The SQLite URL does not include a file path")
    return Path(parsed.database).resolve()


def inspect_sqlite(path: Path) -> dict:
    """Read-only integrity, size, row-count, and session-age snapshot."""
    if not path.is_file():
        raise BackupError(f"Database file not found: {path}")

    try:
        connection = sqlite3.connect(_readonly_uri(path), uri=True)
        connection.execute("PRAGMA schema_version").fetchone()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Not a valid SQLite database: {path}") from exc

    try:
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        integrity = "; ".join(row[0] for row in integrity_rows)
        foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        freelist_count = connection.execute("PRAGMA freelist_count").fetchone()[0]

        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]

        version = None
        if "alembic_version" in tables:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            version = row[0] if row else None

        now = int(time.time())
        active_sessions = None
        expired_sessions = None
        if "auth_sessions" in tables:
            active_sessions = connection.execute(
                "SELECT COUNT(*) FROM auth_sessions "
                "WHERE revoked_at IS NULL AND expires_at > ?",
                (now,),
            ).fetchone()[0]
            expired_sessions = connection.execute(
                "SELECT COUNT(*) FROM auth_sessions WHERE expires_at <= ?",
                (now,),
            ).fetchone()[0]

        oldest_event = None
        newest_event = None
        if "audit_events" in tables:
            oldest_event, newest_event = connection.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM audit_events"
            ).fetchone()
    finally:
        connection.close()

    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "integrity": integrity,
        "integrity_ok": integrity == "ok",
        "foreign_key_violations": foreign_key_violations,
        "page_count": page_count,
        "freelist_pages": freelist_count,
        "alembic_version": version,
        "table_counts": counts,
        "active_sessions": active_sessions,
        "expired_sessions": expired_sessions,
        "oldest_audit_event_at": oldest_event,
        "newest_audit_event_at": newest_event,
    }


def create_sqlite_backup(source: Path, destination: Path) -> dict:
    if not source.is_file():
        raise BackupError(f"Database file not found: {source}")
    if source.resolve() == destination.resolve():
        raise BackupError("Backup destination must differ from the source database")
    if destination.exists():
        raise BackupError(f"Refusing to overwrite existing file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_readonly_uri(source), uri=True) as source_db:
        with sqlite3.connect(str(destination)) as destination_db:
            source_db.backup(destination_db)

    snapshot = inspect_sqlite(destination)
    if not snapshot["integrity_ok"]:
        destination.unlink(missing_ok=True)
        raise BackupError(f"Backup failed integrity check: {snapshot['integrity']}")

    manifest = {
        "format": "sqlite-backup",
        "created_at": int(time.time()),
        "source": str(source),
        "sha256": _sha256(destination),
        **snapshot,
    }
    _manifest_path(destination).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def _pg_tools() -> tuple[str, str | None]:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        raise BackupError(
            "pg_dump was not found on PATH. Install the PostgreSQL client tools "
            "or run the dump from a managed database console"
        )
    return pg_dump, shutil.which("pg_restore")


def _pg_safe_url(database_url: str):
    parsed = make_url(resolve_database_url(database_url))
    if parsed.drivername.split("+")[0] != "postgresql":
        raise BackupError("pg_dump backups require a PostgreSQL database URL")
    password = parsed.password
    safe = parsed.set(drivername="postgresql", password=None)
    return safe.render_as_string(hide_password=False), password


def create_postgres_backup(database_url: str, destination: Path) -> dict:
    if destination.exists():
        raise BackupError(f"Refusing to overwrite existing file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    pg_dump, pg_restore = _pg_tools()
    safe_url, password = _pg_safe_url(database_url)
    environment = dict(os.environ)
    if password:
        environment["PGPASSWORD"] = password

    result = subprocess.run(
        [
            pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={destination}",
            f"--dbname={safe_url}",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        message = (result.stderr or "").strip().splitlines()
        raise BackupError(
            f"pg_dump failed with exit code {result.returncode}: "
            f"{message[-1] if message else 'no error output'}"
        )

    if not destination.is_file() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise BackupError("pg_dump produced no output")

    if pg_restore is not None:
        listed = subprocess.run(
            [pg_restore, "--list", str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0:
            destination.unlink(missing_ok=True)
            raise BackupError("The pg_dump archive failed pg_restore --list verification")

    manifest = {
        "format": "pg_dump-custom",
        "created_at": int(time.time()),
        "database": safe_url.split("?", 1)[0].rsplit("/", 1)[-1],
        "sha256": _sha256(destination),
        "size_bytes": destination.stat().st_size,
        "restore_format": "pg_restore --dbname=<reviewed target> <file>",
        "toc_verified": pg_restore is not None,
    }
    _manifest_path(destination).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def verify_backup(backup: Path) -> dict:
    if not backup.is_file():
        raise BackupError(f"Backup file not found: {backup}")

    manifest_file = _manifest_path(backup)
    manifest = None
    if manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        actual = _sha256(backup)
        if manifest.get("sha256") != actual:
            raise BackupError("Backup checksum does not match its manifest")
    else:
        actual = _sha256(backup)

    if manifest and manifest.get("format") == "pg_dump-custom":
        _, pg_restore = _pg_tools()
        if pg_restore is not None:
            listed = subprocess.run(
                [pg_restore, "--list", str(backup)],
                capture_output=True,
                text=True,
                check=False,
            )
            if listed.returncode != 0:
                raise BackupError("The pg_dump archive failed pg_restore --list verification")
        return {"format": "pg_dump-custom", "sha256": actual, "manifest": manifest}

    snapshot = inspect_sqlite(backup)
    if not snapshot["integrity_ok"]:
        raise BackupError(f"Backup failed integrity check: {snapshot['integrity']}")
    if manifest and manifest.get("table_counts") != snapshot["table_counts"]:
        raise BackupError("Backup table counts do not match its manifest")
    return {**snapshot, "sha256": actual, "manifest": manifest}


def _require_sqlite_archive(backup: Path) -> None:
    """Reject non-SQLite backups before any restore target is created."""
    manifest_file = _manifest_path(backup)
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BackupError("Backup manifest is unreadable") from exc
        if manifest.get("format") != "sqlite-backup":
            raise BackupError(
                "This restore command accepts SQLite backups only. PostgreSQL "
                "archives are restored manually with pg_restore after review; "
                "see DISASTER_RECOVERY.md"
            )

    try:
        with backup.open("rb") as handle:
            header = handle.read(16)
    except OSError as exc:
        raise BackupError(f"Backup file cannot be read: {backup}") from exc

    if header != b"SQLite format 3\x00":
        raise BackupError(
            "Unsupported backup format: the file is not a SQLite database"
        )


def restore_sqlite_backup(
    backup: Path, target: Path, *, allow_manifestless: bool = False
) -> dict:
    if target.exists():
        raise BackupError(
            f"Refusing to restore over an existing file: {target}. Restore drills "
            "must use a new path"
        )

    _require_sqlite_archive(backup)

    if not _manifest_path(backup).is_file() and not allow_manifestless:
        raise BackupError(
            "This backup has no manifest. Run the verify command for a read-only "
            "check, or pass --allow-manifestless after reviewing a legacy backup"
        )

    verified = verify_backup(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False

    try:
        with sqlite3.connect(_readonly_uri(backup), uri=True) as backup_db:
            target_db = sqlite3.connect(str(target))
            created = True
            try:
                with target_db:
                    backup_db.backup(target_db)
            finally:
                target_db.close()

        restored = inspect_sqlite(target)
        if not restored["integrity_ok"]:
            raise BackupError(
                f"Restored copy failed integrity check: {restored['integrity']}"
            )
        expected_counts = verified.get("table_counts")
        if expected_counts is not None and restored["table_counts"] != expected_counts:
            raise BackupError("Restored copy does not match the backup's table counts")
        return restored
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="read-only size and retention snapshot")
    status_parser.add_argument("--source", help="SQLite database path")

    backup_parser = subparsers.add_parser("backup", help="create a verified backup")
    backup_parser.add_argument("--source", help="SQLite database path")
    backup_parser.add_argument("--database-url", help="PostgreSQL URL for a pg_dump backup")
    backup_parser.add_argument("--destination", required=True, help="new backup file path")

    verify_parser = subparsers.add_parser("verify", help="verification-only check of a backup")
    verify_parser.add_argument("--backup", required=True)

    restore_parser = subparsers.add_parser("restore", help="restore to a NEW SQLite path")
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--target", required=True)
    restore_parser.add_argument(
        "--allow-manifestless",
        action="store_true",
        help="restore a reviewed legacy SQLite backup that has no manifest",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            _print(inspect_sqlite(sqlite_path(args.source)))
        elif args.command == "backup":
            destination = Path(args.destination).expanduser().resolve()
            if args.database_url:
                _print(create_postgres_backup(args.database_url, destination))
            else:
                _print(create_sqlite_backup(sqlite_path(args.source), destination))
        elif args.command == "verify":
            _print(verify_backup(Path(args.backup).expanduser().resolve()))
        elif args.command == "restore":
            _print(
                restore_sqlite_backup(
                    Path(args.backup).expanduser().resolve(),
                    Path(args.target).expanduser().resolve(),
                    allow_manifestless=args.allow_manifestless,
                )
            )
    except (BackupError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
