import logging
import secrets
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditEvent, AuthSession, User
from ..schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from ..services.audit import record_event
from ..services.groups import assign_role_group
from ..services.auth import (
    create_session,
    hash_password,
    normalize_email,
    revoke_session,
    verify_password,
)
from .deps import get_current_session
from ..services.rate_limit import (
    LOGIN_MAX,
    LOGIN_WINDOW_SECONDS,
    REGISTER_MAX,
    REGISTER_WINDOW_SECONDS,
    enforce_rate_limit,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

logger = logging.getLogger("researchtwin.auth")

INVALID_CREDENTIALS = "Invalid email or password"


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """A valid hash used only to keep unknown-email logins as slow as real ones."""
    return hash_password(secrets.token_hex(16))


def _login_failure_already_recorded(
    db: Session, *, user_id: int | None, since: int
) -> bool:
    query = db.query(AuditEvent.id).filter(
        AuditEvent.action == "auth.login_failed",
        AuditEvent.created_at >= since,
    )
    if user_id is None:
        query = query.filter(AuditEvent.target_id.is_(None))
    else:
        query = query.filter(AuditEvent.target_id == user_id)
    return query.first() is not None


def _enforce_login_failure_limit(db: Session, request, email: str) -> None:
    """Throttle failed logins only, so a correct password is never locked out."""
    enforce_rate_limit(
        db,
        request,
        scope="auth-login",
        identities=(("email", email),),
        limit=LOGIN_MAX,
        window_seconds=LOGIN_WINDOW_SECONDS,
    )


def _record_login_failure(
    db: Session, *, user: User | None, reason: str
) -> None:
    """Record at most one failure per identity per login window.

    Failed logins are already rate limited, but an attacker rotating source
    addresses could otherwise add one audit row per attempt. Unknown
    identities are deliberately not stored: a plain hash of an email is
    dictionary-reversible, and the rate limiter already keeps the HMAC'd
    per-email bucket needed for abuse control.
    """
    now = int(time.time())
    try:
        if _login_failure_already_recorded(
            db,
            user_id=user.id if user is not None else None,
            since=now - LOGIN_WINDOW_SECONDS,
        ):
            return
        record_event(
            db,
            actor=None,
            action="auth.login_failed",
            target_type="user" if user is not None else "login_identity",
            target_id=user.id if user is not None else None,
            detail={"reason": reason},
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning(
            "Could not record login failure audit event: %s",
            type(exc).__name__,
        )


def _auth_response(token: str, expires_at: int, user: User) -> AuthResponse:
    return AuthResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = normalize_email(payload.email)
    enforce_rate_limit(
        db,
        request,
        scope="auth-register",
        identities=(("email", email),),
        limit=REGISTER_MAX,
        window_seconds=REGISTER_WINDOW_SECONDS,
    )

    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    user = User(
        email=email,
        full_name=payload.full_name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=True,
        created_at=int(time.time()),
    )

    db.add(user)
    try:
        db.flush()
        assign_role_group(db, user)
        token, expires_at = create_session(db, user, commit=False)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Registration could not be completed",
        )

    db.refresh(user)
    return _auth_response(token, expires_at, user)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = normalize_email(payload.email)

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if user is None:
        verify_password(payload.password, _dummy_password_hash())
        _enforce_login_failure_limit(db, request, email)
        _record_login_failure(db, user=None, reason="unknown_account")
        raise HTTPException(
            status_code=401,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.password_hash):
        _enforce_login_failure_limit(db, request, email)
        _record_login_failure(db, user=user, reason="invalid_password")
        raise HTTPException(
            status_code=401,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        _record_login_failure(db, user=user, reason="inactive_account")
        raise HTTPException(
            status_code=403,
            detail="Account is inactive",
        )

    token, expires_at = create_session(db, user, commit=False)
    record_event(
        db,
        actor=user,
        action="auth.login_succeeded",
        target_type="user",
        target_id=user.id,
    )
    db.commit()

    return _auth_response(token, expires_at, user)


@router.post("/logout")
def logout(
    session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    revoke_session(db, session, commit=False)
    record_event(
        db,
        actor=db.get(User, session.user_id),
        action="auth.logout",
        target_type="auth_session",
        target_id=session.id,
    )
    db.commit()
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
def me(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    user = db.get(User, session.user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
