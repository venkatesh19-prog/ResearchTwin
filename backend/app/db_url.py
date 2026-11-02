"""Database URL resolution without creating an engine.

Offline tooling (backups, restore drills) imports this module so it can resolve
the configured database without opening a connection or failing on hosted
environment guards.
"""

import os

DEFAULT_DATABASE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "researchtwin.db")
)


def resolve_database_url(raw_url: str | None = None) -> str:
    """Normalize a database URL for SQLAlchemy.

    Render exposes PostgreSQL URLs with the legacy ``postgres://`` scheme
    (or ``postgresql://``); both must be routed through psycopg 3, whose
    SQLAlchemy dialect is ``postgresql+psycopg``. Any other value, including
    an explicit SQLite URL, is returned unchanged.
    """

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
