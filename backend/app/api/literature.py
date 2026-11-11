"""Private reference and literature review records."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LiteratureEntry, ProposalCitation, User
from ..schemas import LiteratureEntryCreate, LiteratureEntryUpdate
from ..services import research_outputs
from .deps import get_current_user

router = APIRouter(tags=["Literature"])


def _like_pattern(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _owned_entry(db: Session, user: User, entry_id: int) -> LiteratureEntry:
    entry = db.get(LiteratureEntry, entry_id)
    if entry is None or entry.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Literature entry not found")
    return entry


def _citation_count(db: Session, entry_id: int) -> int:
    return (
        db.query(ProposalCitation)
        .filter(ProposalCitation.literature_entry_id == entry_id)
        .count()
    )


@router.get("/literature")
def list_literature(
    q: str | None = Query(default=None, max_length=200),
    review_status: str | None = Query(default=None),
    tag: str | None = Query(default=None, max_length=50),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if review_status is not None and review_status not in {
        "to_read",
        "reading",
        "reviewed",
        "archived",
    }:
        raise HTTPException(status_code=422, detail="Unknown review status")

    query = db.query(LiteratureEntry).filter(
        LiteratureEntry.owner_user_id == user.id
    )
    if review_status is not None:
        query = query.filter(LiteratureEntry.review_status == review_status)
    if q:
        pattern = _like_pattern(q.strip())
        query = query.filter(
            or_(
                LiteratureEntry.title.ilike(pattern, escape="\\"),
                LiteratureEntry.authors.ilike(pattern, escape="\\"),
                LiteratureEntry.venue.ilike(pattern, escape="\\"),
                LiteratureEntry.abstract.ilike(pattern, escape="\\"),
                LiteratureEntry.notes.ilike(pattern, escape="\\"),
            )
        )
    if tag is not None:
        wanted = tag.strip().lower()
        if wanted:
            escaped = (
                wanted.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            query = query.filter(
                or_(
                    LiteratureEntry.tags == wanted,
                    LiteratureEntry.tags.like(f"{escaped}, %", escape="\\"),
                    LiteratureEntry.tags.like(f"%, {escaped}", escape="\\"),
                    LiteratureEntry.tags.like(
                        f"%, {escaped}, %", escape="\\"
                    ),
                )
            )
        else:
            query = query.filter(LiteratureEntry.id.is_(None))

    total = query.order_by(None).count()
    page = (
        query.order_by(
            LiteratureEntry.updated_at.desc(), LiteratureEntry.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    counts = research_outputs.literature_citation_counts(
        db, [entry.id for entry in page]
    )
    return {
        "entries": [
            research_outputs.literature_payload(
                entry, counts.get(entry.id, 0)
            )
            for entry in page
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/literature", status_code=201)
def create_literature_entry(
    payload: LiteratureEntryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    timestamp = research_outputs.now()
    entry = LiteratureEntry(
        owner_user_id=user.id,
        title=payload.title,
        authors=payload.authors,
        venue=payload.venue,
        year=payload.year,
        doi=payload.doi,
        url=payload.url,
        abstract=payload.abstract,
        notes=payload.notes,
        tags=research_outputs.serialize_tags(payload.tags),
        review_status=payload.review_status,
        citation_key=payload.citation_key,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That citation key already exists in your library",
        ) from exc
    db.refresh(entry)
    return research_outputs.literature_payload(entry)


@router.get("/literature/{entry_id}")
def get_literature_entry(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _owned_entry(db, user, entry_id)
    return research_outputs.literature_payload(
        entry, _citation_count(db, entry.id)
    )


@router.put("/literature/{entry_id}")
def update_literature_entry(
    entry_id: int,
    payload: LiteratureEntryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _owned_entry(db, user, entry_id)
    changes = payload.model_dump(exclude_unset=True)

    if "tags" in changes:
        entry.tags = research_outputs.serialize_tags(changes.pop("tags"))
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.updated_at = research_outputs.now()

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That citation key already exists in your library",
        ) from exc
    db.refresh(entry)
    return research_outputs.literature_payload(
        entry, _citation_count(db, entry.id)
    )


@router.delete("/literature/{entry_id}")
def delete_literature_entry(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _owned_entry(db, user, entry_id)
    # Explicit child delete keeps SQLite and PostgreSQL behaviour identical.
    db.query(ProposalCitation).filter(
        ProposalCitation.literature_entry_id == entry.id
    ).delete(synchronize_session=False)
    db.delete(entry)
    db.commit()
    return {"deleted": True}
