"""Alembic environment.

The URL comes from ``-x``/``alembic.ini`` when set (used by tests), otherwise
from ``DATABASE_URL``. ``app.db_url.resolve_migration_url`` keeps the legacy
Render ``postgres://`` scheme routed through psycopg 3 and only reads a dotenv
file when ``RESEARCHTWIN_ENV_FILE`` explicitly opts in.
"""

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: E402,F401
from app.database import (  # noqa: E402
    Base,
    enforce_sqlite_foreign_keys,
)
from app.db_url import resolve_migration_url  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    return resolve_migration_url(config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    enforce_sqlite_foreign_keys(connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
