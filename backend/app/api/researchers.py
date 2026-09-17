from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Researcher
from ..schemas import ResearcherCreate, ResearcherResponse
from ..services.researcher_import import import_researchers
from ..services.researcher_intelligence import get_researcher_profiles


router = APIRouter(
    prefix="/researchers",
    tags=["Researchers"]
)


# --------------------------------------------------
# CREATE RESEARCHER
# --------------------------------------------------

@router.post("/", response_model=ResearcherResponse)
def create_researcher(
    researcher: ResearcherCreate,
    db: Session = Depends(get_db)
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
    department: str | None = None,
    research_area: str | None = None,
    skill: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(Researcher)

    # Filter by department
    if department:
        query = query.filter(
            Researcher.department.ilike(
                f"%{department}%"
            )
        )

    # Filter by research area
    if research_area:
        query = query.filter(
            Researcher.research_areas.ilike(
                f"%{research_area}%"
            )
        )

    # Filter by skill
    if skill:
        query = query.filter(
            Researcher.skills.ilike(
                f"%{skill}%"
            )
        )

    return query.all()


# --------------------------------------------------
# RESEARCHER INTELLIGENCE
# --------------------------------------------------

@router.get("/intelligence")
def researcher_intelligence(
    db: Session = Depends(get_db)
):
    return get_researcher_profiles(db)


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
    db: Session = Depends(get_db)
):
    csv_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "researchers.csv"
    )

    if not csv_path.exists():
        raise HTTPException(
            status_code=404,
            detail="researchers.csv not found"
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

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )