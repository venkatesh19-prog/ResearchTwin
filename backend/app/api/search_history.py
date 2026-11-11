"""Per-user researcher directory search history."""

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SearchHistory, User
from ..schemas import SearchHistoryCreate, SearchHistoryResponse
from .deps import get_current_user

router = APIRouter(prefix="/search-history", tags=["Search History"])

MAX_ENTRIES_PER_USER = 20


@router.get("", response_model=list[SearchHistoryResponse])
def list_search_history(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
        .limit(limit)
        .all()
    )


@router.post("", response_model=SearchHistoryResponse)
def record_search(
    payload: SearchHistoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    latest = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
        .first()
    )
    if latest is not None and latest.query.lower() == payload.query.lower():
        return latest

    entry = SearchHistory(
        user_id=user.id,
        query=payload.query,
        created_at=int(time.time()),
    )
    db.add(entry)
    db.flush()

    stale_ids = [
        row.id
        for row in db.query(SearchHistory.id)
        .filter(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
        .offset(MAX_ENTRIES_PER_USER)
        .all()
    ]
    if stale_ids:
        db.query(SearchHistory).filter(SearchHistory.id.in_(stale_ids)).delete(
            synchronize_session=False
        )

    db.commit()
    db.refresh(entry)
    return entry
