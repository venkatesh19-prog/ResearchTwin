"""University and department research analytics for authenticated users."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services.research_analytics import department_rows, university_summary
from .deps import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/university")
def get_university_analytics(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return university_summary(db)


@router.get("/departments")
def get_department_analytics(
    department: str | None = Query(default=None, max_length=150),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return department_rows(
        db,
        department=department,
        offset=offset,
        limit=limit,
    )
