"""Database-backed request limits shared by workers using the same database."""

import hashlib
import hmac
import ipaddress
import os
import time

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import RateLimitCounter


def _positive_setting(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


REGISTER_MAX = _positive_setting("RATE_LIMIT_REGISTER_MAX", 5)
REGISTER_WINDOW_SECONDS = _positive_setting(
    "RATE_LIMIT_REGISTER_WINDOW_SECONDS", 3600
)
LOGIN_MAX = _positive_setting("RATE_LIMIT_LOGIN_MAX", 10)
LOGIN_WINDOW_SECONDS = _positive_setting("RATE_LIMIT_LOGIN_WINDOW_SECONDS", 900)
RECOMMENDATION_MAX = _positive_setting("RATE_LIMIT_RECOMMENDATION_MAX", 8)
RECOMMENDATION_WINDOW_SECONDS = _positive_setting(
    "RATE_LIMIT_RECOMMENDATION_WINDOW_SECONDS", 300
)

_last_prune_day: int | None = None


def is_rate_limit_configured() -> bool:
    secret = os.getenv("RATE_LIMIT_HASH_SECRET", "")
    return len(secret.encode("utf-8")) >= 32


def is_rate_limit_ready(db: Session) -> bool:
    if not is_rate_limit_configured():
        return False
    if os.getenv("RATE_LIMIT_REQUIRE_SHARED_DATABASE", "").lower() == "true":
        return db.get_bind().dialect.name == "postgresql"
    return True


def client_ip_identity(request: Request) -> str:
    """Return a normalized client IP without trusting arbitrary forwarded headers."""
    if os.getenv("RATE_LIMIT_TRUST_CF_CONNECTING_IP", "").lower() == "true":
        candidate = request.headers.get("cf-connecting-ip", "").strip()
        try:
            return ipaddress.ip_address(candidate).compressed
        except ValueError:
            pass

    client = request.client
    candidate = client.host.strip() if client and client.host else "unknown"
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return candidate[:255] or "unknown"


def _bucket_hash(scope: str, principal_kind: str, principal: str) -> str:
    secret = os.getenv("RATE_LIMIT_HASH_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="Request protection is not configured",
        )
    payload = f"{scope}\0{principal_kind}\0{principal}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def enforce_rate_limit(
    db: Session,
    request: Request,
    *,
    scope: str,
    identities: tuple[tuple[str, str], ...],
    limit: int,
    window_seconds: int,
) -> None:
    """Atomically increment per-IP and per-account fixed-window counters."""
    if not is_rate_limit_configured():
        raise HTTPException(
            status_code=503,
            detail="Request protection is not configured",
        )

    now = int(time.time())
    window_start = now - (now % window_seconds)
    counter = RateLimitCounter.__table__
    dialect = db.get_bind().dialect.name

    if (
        os.getenv("RATE_LIMIT_REQUIRE_SHARED_DATABASE", "").lower() == "true"
        and dialect != "postgresql"
    ):
        raise HTTPException(
            status_code=503,
            detail="Shared request protection is unavailable",
        )

    if dialect == "postgresql":
        insert = postgresql_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise HTTPException(
            status_code=503,
            detail="Request protection is unavailable",
        )

    principals = (("ip", client_ip_identity(request)),) + identities
    exceeded = False

    try:
        global _last_prune_day
        day = now // 86_400
        if _last_prune_day != day:
            db.execute(
                delete(counter).where(counter.c.updated_at < now - 7 * 86_400)
            )
            _last_prune_day = day

        for principal_kind, principal in principals:
            key = _bucket_hash(scope, principal_kind, principal)
            statement = insert(counter).values(
                bucket_hash=key,
                window_start=window_start,
                count=1,
                updated_at=now,
            )
            next_count = case(
                (counter.c.window_start == window_start, counter.c.count + 1),
                else_=1,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[counter.c.bucket_hash],
                set_={
                    "window_start": window_start,
                    "count": next_count,
                    "updated_at": now,
                },
            ).returning(counter.c.count)
            count = db.execute(statement).scalar_one()
            exceeded = exceeded or count > limit

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Request protection is temporarily unavailable",
        ) from exc

    if exceeded:
        retry_after = max(1, window_start + window_seconds - now)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please retry later.",
            headers={"Retry-After": str(retry_after)},
        )
