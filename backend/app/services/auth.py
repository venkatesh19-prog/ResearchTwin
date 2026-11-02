"""Password hashing and opaque session-token handling.

Passwords are stored as PBKDF2-HMAC-SHA256 digests with a per-user salt.
Session tokens are random 256-bit values; only their SHA-256 digest is stored,
so a database leak does not expose usable bearer tokens.
"""

import hashlib
import hmac
import os
import secrets
import time

from sqlalchemy.orm import Session

from ..models import AuthSession, User

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
SALT_BYTES = 16
TOKEN_BYTES = 32
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(digest, expected)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_ttl_seconds() -> int:
    raw = os.getenv("AUTH_SESSION_TTL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SESSION_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS
    return value if value > 0 else DEFAULT_SESSION_TTL_SECONDS


def create_session(
    db: Session, user: User, *, commit: bool = True
) -> tuple[str, int]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = int(time.time())
    expires_at = now + session_ttl_seconds()

    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
        )
    )
    if commit:
        db.commit()

    return token, expires_at


def get_active_session(db: Session, token: str) -> AuthSession | None:
    if not token:
        return None

    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == hash_token(token))
        .first()
    )

    if session is None or session.revoked_at is not None:
        return None

    if session.expires_at <= int(time.time()):
        return None

    return session


def revoke_session(
    db: Session, session: AuthSession, *, commit: bool = True
) -> None:
    if session.revoked_at is None:
        session.revoked_at = int(time.time())
        if commit:
            db.commit()
