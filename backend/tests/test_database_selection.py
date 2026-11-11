"""Fresh-process database selection regressions for the Neon opt-in gate.

Each test runs a separate interpreter so import-time side effects (environment
loading, engine creation) are exercised exactly as they are in production.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
ENV_FILE_VAR = "RESEARCHTWIN_ENV_FILE"

_SCRUBBED = ("DATABASE_URL", "RENDER", ENV_FILE_VAR)


def _fresh(expression: str, **env_overrides: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in _SCRUBBED}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", expression],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _resolve(**overrides: str) -> str:
    proc = _fresh(
        "from app.db_url import resolve_database_url;"
        "print(resolve_database_url())",
        **overrides,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _resolve_migration(**overrides: str) -> str:
    proc = _fresh(
        "from app.db_url import resolve_migration_url;"
        "print(resolve_migration_url(''))",
        **overrides,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_no_database_url_uses_sqlite_even_when_env_local_exists():
    if not (REPO_ROOT / ".env.local").is_file():
        pytest.skip("repository .env.local is absent in this checkout")

    url = _resolve()

    assert url.startswith("sqlite:///")
    assert url.endswith("/backend/researchtwin.db")


def test_render_injected_database_url_is_used():
    url = _resolve(
        RENDER="true",
        DATABASE_URL="postgres://rt:secret@render-db.example.com:5432/researchtwin",
    )

    assert url == (
        "postgresql+psycopg://rt:secret@render-db.example.com:5432/researchtwin"
    )


def test_render_without_database_url_still_refuses_to_start():
    proc = _fresh(
        "from app.db_url import resolve_database_url; resolve_database_url()",
        RENDER="true",
    )

    assert proc.returncode != 0
    assert "DATABASE_URL" in proc.stderr


def test_explicit_neon_opt_in_loads_the_named_env_file(tmp_path):
    env_file = tmp_path / "neon.local"
    env_file.write_text(
        "DATABASE_URL=postgres://neon:secret@neon.example.com:5432/neondb\n",
        encoding="utf-8",
    )

    url = _resolve(**{ENV_FILE_VAR: str(env_file)})

    assert url == "postgresql+psycopg://neon:secret@neon.example.com:5432/neondb"


def test_process_environment_beats_the_opt_in_env_file(tmp_path):
    env_file = tmp_path / "neon.local"
    env_file.write_text(
        "DATABASE_URL=postgres://neon:secret@neon.example.com:5432/neondb\n",
        encoding="utf-8",
    )

    url = _resolve(
        DATABASE_URL="sqlite:///C:/tmp/explicit.db",
        **{ENV_FILE_VAR: str(env_file)},
    )

    assert url == "sqlite:///C:/tmp/explicit.db"


def test_opt_in_pointing_at_a_missing_file_fails_loudly(tmp_path):
    proc = _fresh(
        "from app.db_url import resolve_database_url; resolve_database_url()",
        **{ENV_FILE_VAR: str(tmp_path / "absent.env")},
    )

    assert proc.returncode != 0
    assert "RESEARCHTWIN_ENV_FILE" in proc.stderr


def test_alembic_target_is_sqlite_without_opt_in():
    url = _resolve_migration()

    assert url.startswith("sqlite:///")
    assert url.endswith("/backend/researchtwin.db")


def test_alembic_target_uses_opt_in_env_file(tmp_path):
    env_file = tmp_path / "neon.local"
    env_file.write_text(
        "DATABASE_URL=postgres://neon:secret@neon.example.com:5432/neondb\n",
        encoding="utf-8",
    )

    url = _resolve_migration(**{ENV_FILE_VAR: str(env_file)})

    assert url == "postgresql+psycopg://neon:secret@neon.example.com:5432/neondb"


def test_alembic_explicit_configured_url_wins_over_environment():
    proc = _fresh(
        "from app.db_url import resolve_migration_url;"
        "print(resolve_migration_url("
        "'postgresql://rt:secret@db.example.com:5432/researchtwin'))",
        DATABASE_URL="sqlite:///C:/tmp/should-not-win.db",
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (
        "postgresql+psycopg://rt:secret@db.example.com:5432/researchtwin"
    )


def test_backup_utility_defaults_to_the_sqlite_demo_database():
    proc = _fresh(
        "import sys; sys.path.insert(0, 'scripts');"
        "import database_backup;"
        "print(database_backup.sqlite_path())"
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().replace("\\", "/").endswith(
        "/backend/researchtwin.db"
    )
