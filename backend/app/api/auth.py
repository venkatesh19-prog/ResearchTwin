import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuthSession, User
from ..schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
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
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        ) from exc

    db.refresh(user)
    token, expires_at = create_session(db, user)

    return _auth_response(token, expires_at, user)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = normalize_email(payload.email)
    enforce_rate_limit(
        db,
        request,
        scope="auth-login",
        identities=(("email", email),),
        limit=LOGIN_MAX,
        window_seconds=LOGIN_WINDOW_SECONDS,
    )

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is inactive",
        )

    token, expires_at = create_session(db, user)

    return _auth_response(token, expires_at, user)


@router.post("/logout")
def logout(
    session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    revoke_session(db, session)
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
