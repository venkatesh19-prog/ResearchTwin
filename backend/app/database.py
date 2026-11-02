from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .db_url import resolve_database_url

BACKEND_DIR = Path(__file__).resolve().parents[1]

DATABASE_URL = resolve_database_url()

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class SchemaRevisionError(RuntimeError):
    """The database cannot prove it is at the reviewed Alembic revision."""


@lru_cache(maxsize=1)
def expected_schema_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise SchemaRevisionError("No Alembic head revision is available")
    return head


def verify_schema_revision(db: Session) -> None:
    """Require PostgreSQL to be stamped at the reviewed migration head.

    SQLite keeps ``create_all`` for local development and tests, so it is not
    subjected to the Alembic revision requirement. Migrations are never run
    automatically here.
    """
    if db.get_bind().dialect.name != "postgresql":
        return

    try:
        current = db.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise SchemaRevisionError("Database migration state is unavailable") from exc

    expected = expected_schema_revision()
    if current != expected:
        raise SchemaRevisionError(
            "Database is not at the reviewed migration head; apply reviewed "
            "Alembic migrations before serving traffic"
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
