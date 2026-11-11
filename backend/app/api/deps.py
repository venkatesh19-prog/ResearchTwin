"""Authentication dependencies shared by protected routes."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuthSession, User
from ..services.auth import get_active_session

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthSession:
    token = credentials.credentials if credentials is not None else ""
    session = get_active_session(db, token)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return session


def get_current_user(
    session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, session.user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve a bearer token when present, otherwise stay anonymous."""
    if credentials is None:
        return None

    session = get_active_session(db, credentials.credentials)
    if session is None:
        return None

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None

    return user


def require_role(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action",
            )
        return user

    return dependency


require_student = require_role("student")
require_faculty = require_role("faculty")
require_admin = require_role("admin")
