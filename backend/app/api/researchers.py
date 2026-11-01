import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Researcher
from ..schemas import ResearcherCreate, ResearcherResponse
from ..services.researcher_import import (
    ResearcherImportError,
    import_researchers,
)
from ..services.researcher_intelligence import get_researcher_profiles
from .deps import require_admin


router = APIRouter(
    prefix="/researchers",
    tags=["Researchers"]
)

logger = logging.getLogger("researchtwin.researchers")


def _contains(expression, term: str):
    """Case-insensitive substring match with the caller's wildcards escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return expression.ilike(f"%{escaped}%", escape="\\")


# --------------------------------------------------
# CREATE RESEARCHER
# --------------------------------------------------

@router.post("/", response_model=ResearcherResponse)
def create_researcher(
    researcher: ResearcherCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    new_researcher = Researcher(
        **researcher.model_dump()
    )

    db.add(new_researcher)
    db.commit()
    db.refresh(new_researcher)

    return new_researcher


# --------------------------------------------------
# GET / SEARCH RESEARCHERS
# --------------------------------------------------

@router.get("/", response_model=list[ResearcherResponse])
def get_researchers(
    search: str | None = Query(default=None, max_length=200),
    department: str | None = Query(default=None, max_length=150),
    research_area: str | None = Query(default=None, max_length=200),
    skill: str | None = Query(default=None, max_length=150),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Researcher)

    # Free-text search across the descriptive columns
    if search:
        term = search.strip()
        if term:
            query = query.filter(
                or_(
                    _contains(Researcher.name, term),
                    _contains(Researcher.department, term),
                    _contains(Researcher.designation, term),
                    _contains(Researcher.research_areas, term),
                    _contains(Researcher.expertise, term),
                    _contains(Researcher.skills, term),
                    _contains(Researcher.publications, term),
                    _contains(Researcher.projects, term),
                )
            )

    # Filter by department
    if department:
        query = query.filter(_contains(Researcher.department, department))

    # Filter by research area
    if research_area:
        query = query.filter(_contains(Researcher.research_areas, research_area))

    # Filter by skill
    if skill:
        query = query.filter(_contains(Researcher.skills, skill))

    return query.order_by(Researcher.id).offset(offset).limit(limit).all()


# --------------------------------------------------
# RESEARCHER INTELLIGENCE
# --------------------------------------------------

@router.get("/intelligence")
def researcher_intelligence(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_db)
):
    return get_researcher_profiles(db, offset=offset, limit=limit)


# --------------------------------------------------
# GET SINGLE RESEARCHER
# --------------------------------------------------

@router.get(
    "/{researcher_id}",
    response_model=ResearcherResponse
)
def get_researcher(
    researcher_id: int,
    db: Session = Depends(get_db)
):
    researcher = (
        db.query(Researcher)
        .filter(Researcher.id == researcher_id)
        .first()
    )

    if researcher is None:
        raise HTTPException(
            status_code=404,
            detail="Researcher not found"
        )

    return researcher


# --------------------------------------------------
# UPDATE RESEARCHER
# --------------------------------------------------

@router.put(
    "/{researcher_id}",
    response_model=ResearcherResponse
)
def update_researcher(
    researcher_id: int,
    researcher_data: ResearcherCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    researcher = (
        db.query(Researcher)
        .filter(Researcher.id == researcher_id)
        .first()
    )

    if researcher is None:
        raise HTTPException(
            status_code=404,
            detail="Researcher not found"
        )

    data = researcher_data.model_dump()

    for key, value in data.items():
        setattr(researcher, key, value)

    db.commit()
    db.refresh(researcher)

    return researcher


# --------------------------------------------------
# DELETE RESEARCHER
# --------------------------------------------------

@router.delete("/{researcher_id}")
def delete_researcher(
    researcher_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    researcher = (
        db.query(Researcher)
        .filter(Researcher.id == researcher_id)
        .first()
    )

    if researcher is None:
        raise HTTPException(
            status_code=404,
            detail="Researcher not found"
        )

    db.delete(researcher)
    db.commit()

    return {
        "message": "Researcher deleted successfully",
        "researcher_id": researcher_id
    }


# --------------------------------------------------
# IMPORT RESEARCHERS FROM CSV
# --------------------------------------------------

@router.post("/import")
def import_researcher_data(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    csv_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "researchers.csv"
    )

    try:
        count = import_researchers(
            str(csv_path),
            db
        )

        return {
            "message": "Researchers imported successfully",
            "imported_count": count
        }

    except ResearcherImportError as exc:
        db.rollback()
        logger.warning("Researcher import validation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=422,
            detail="Researcher import file is invalid",
        ) from exc
    except FileNotFoundError as exc:
        db.rollback()
        logger.error("Researcher import source is unavailable (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Researcher import source is unavailable",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Researcher import failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Researcher import failed",
        ) from exc
