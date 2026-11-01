"""Provision an administrator from a trusted operator shell, never an API."""

import getpass
import os
import re
import sys
import time
from pathlib import Path


EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MIN_PASSWORD_LENGTH = 16
MAX_PASSWORD_LENGTH = 128


def validate_provisioning_configuration(database_url: str, enabled: str) -> None:
    if not database_url.strip():
        raise ValueError("DATABASE_URL must be set explicitly.")
    if enabled != "YES":
        raise ValueError(
            "Set RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING=YES to enable this CLI."
        )


def provision_admin(db, email: str, full_name: str, password: str):
    """Create a new admin; refuse to change any existing account's role."""
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    from app.models import User
    from app.services.auth import hash_password, normalize_email

    normalized_email = normalize_email(email)
    clean_name = full_name.strip()
    if not EMAIL_RE.fullmatch(normalized_email):
        raise ValueError("Enter a valid email address.")
    if not clean_name or len(clean_name) > 120:
        raise ValueError("Full name must contain 1 to 120 characters.")
    if (
        len(password) < MIN_PASSWORD_LENGTH
        or len(password) > MAX_PASSWORD_LENGTH
        or not password.strip()
    ):
        raise ValueError(
            f"Password must contain {MIN_PASSWORD_LENGTH} to "
            f"{MAX_PASSWORD_LENGTH} characters."
        )
    existing = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if existing is not None:
        raise ValueError(
            "That email already belongs to an account; role changes are refused."
        )

    user = User(
        email=normalized_email,
        full_name=clean_name,
        role="admin",
        password_hash=hash_password(password),
        is_active=True,
        created_at=int(time.time()),
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise ValueError("Administrator could not be created; no changes were saved.") from None
    except Exception:
        db.rollback()
        raise
    return user


def _safe_database_label(database_url: str) -> str:
    # Show enough context to catch an accidental target while hiding credentials
    # and the full local filesystem path.
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        database = Path(url.database or "local database").name
        return f"sqlite database {database}"
    target = url.hostname or "configured host"
    if url.port:
        target += f":{url.port}"
    if url.database:
        target += f"/{url.database}"
    return f"{url.get_backend_name()} database at {target}"


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    try:
        validate_provisioning_configuration(
            database_url,
            os.getenv("RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING", ""),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    print(f"Administrator target: {_safe_database_label(database_url)}")
    if input("Type CREATE ADMIN to continue: ") != "CREATE ADMIN":
        raise SystemExit("Confirmation did not match; no account was created.")

    email = input("Administrator email: ").strip()
    full_name = input("Administrator full name: ").strip()
    password = getpass.getpass("New administrator password (input hidden): ")
    confirmation = getpass.getpass("Confirm password (input hidden): ")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no account was created.")

    # Import the configured engine only after explicit opt-in and confirmation.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = provision_admin(db, email, full_name, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    finally:
        db.close()

    print(f"Administrator account created for {user.email} (user id {user.id}).")


if __name__ == "__main__":
    main()
