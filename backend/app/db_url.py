"""Database URL resolution without creating an engine.

Offline tooling (backups, restore drills) imports this module so it can resolve
the configured database without opening a connection or failing on hosted
environment guards.

Local development uses SQLite unless ``DATABASE_URL`` is set. Loading a dotenv
file (for example the ``.env.local`` written by ``neon deploy``) is opt-in:
set ``RESEARCHTWIN_ENV_FILE`` to the file's path to enable it for that process
only. Nothing is loaded implicitly, so a stray ``.env.local`` can never redirect
ordinary startup, Alembic, or the backup utility away from SQLite or Render.
"""

import os
from pathlib import Path
from typing import Sequence

DEFAULT_DATABASE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "researchtwin.db")
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (".env.local", ".env")
ENV_FILE_OPT_IN = "RESEARCHTWIN_ENV_FILE"

_env_loaded = False


def load_env_files(root: Path = REPO_ROOT, names: Sequence[str] = ENV_FILES) -> None:
    """Load ``names`` from ``root`` into the process environment.

    Values already present in the environment always win, so hosted platforms
    that inject ``DATABASE_URL`` keep their own configuration. Earlier files in
    ``names`` win over later ones because ``.env.local`` is listed first.
    """

    for name in names:
        path = root / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key:
                os.environ.setdefault(key, value.strip().strip("\"'"))


def _opt_in_env_file() -> Path | None:
    """Return the explicitly requested dotenv file, if any.

    A relative path is resolved against the repository root so the documented
    ``RESEARCHTWIN_ENV_FILE=.env.local`` works from any working directory.
    """

    value = os.getenv(ENV_FILE_OPT_IN, "").strip()
    if not value:
        return None

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(
            f"{ENV_FILE_OPT_IN} points at a missing file: {path}"
        )
    return path


def resolve_database_url(raw_url: str | None = None) -> str:
    """Normalize a database URL for SQLAlchemy.

    Render exposes PostgreSQL URLs with the legacy ``postgres://`` scheme
    (or ``postgresql://``); both must be routed through psycopg 3, whose
    SQLAlchemy dialect is ``postgresql+psycopg``. Any other value, including
    an explicit SQLite URL, is returned unchanged.

    A dotenv file is read only when ``RESEARCHTWIN_ENV_FILE`` names one and
    ``raw_url`` is omitted, so an existing process environment always decides
    first and unconfigured local runs keep using SQLite.
    """

    global _env_loaded
    if raw_url is None and not _env_loaded:
        env_file = _opt_in_env_file()
        if env_file is not None:
            load_env_files(env_file.parent, (env_file.name,))
        _env_loaded = True

    url = (raw_url if raw_url is not None else os.getenv("DATABASE_URL")) or ""
    url = url.strip()

    if not url:
        if os.getenv("RENDER", "").strip().lower() == "true":
            raise RuntimeError(
                "DATABASE_URL must be configured in the hosted environment; "
                "refusing to fall back to local SQLite"
            )
        return "sqlite:///" + DEFAULT_DATABASE_PATH.replace("\\", "/")

    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]

    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]

    return url


def resolve_migration_url(configured_url: str | None = None) -> str:
    """Resolve the Alembic target: configured URL, then ``DATABASE_URL``.

    ``migrations/env.py`` passes ``alembic.ini``'s ``sqlalchemy.url`` here (an
    empty string in this repository), so migrations fall back to
    ``DATABASE_URL`` and finally to the SQLite demo database. Neon is reached
    only when ``RESEARCHTWIN_ENV_FILE`` explicitly opts in.
    """

    return resolve_database_url(configured_url or os.getenv("DATABASE_URL"))
