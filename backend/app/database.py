import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

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
        return "sqlite:///" + DEFAULT_DATABASE_PATH.replace("\\", "/")

    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]

    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]

    return url


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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
