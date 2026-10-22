from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.recommendation import generate_recommendations
from ..services.readiness_roadmap import generate_readiness_roadmap

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"]
)


class StudentProfile(BaseModel):
    research_areas: str = ""
    expertise: str = ""
    skills: str = ""
    projects: str = ""
    publications: str = ""
    top_k: int = 5


@router.post("/researchers")
def recommend_researchers(
    student: StudentProfile,
    db: Session = Depends(get_db)
):

    student_profile = {
        "research_areas": student.research_areas,
        "expertise": student.expertise,
        "skills": student.skills,
        "projects": student.projects,
        "publications": student.publications
    }

    recommendations = generate_recommendations(
        student_profile=student_profile,
        db=db,
        top_k=student.top_k
    )

    return {
        "student_profile": student_profile,
        "recommendations": recommendations
    }

from pydantic import Field


class RoadmapRequest(BaseModel):
    researcher_id: int
    matched_skills: list[str] = Field(default_factory=list)
    skill_gap: list[str] = Field(default_factory=list)


@router.post("/roadmap/researcher")
def create_researcher_roadmap(
    request: RoadmapRequest,
    db: Session = Depends(get_db)
):
    from ..models import Researcher

    researcher = db.query(Researcher).filter(
        Researcher.id == request.researcher_id
    ).first()

    if researcher is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail="Researcher not found"
        )

    # Derive skill data from the actual database record.
    # Do not trust client-submitted skill lists as authoritative.
    from ..services.skill_gap import calculate_skill_gap

    skill_data = calculate_skill_gap("", researcher)

    return generate_readiness_roadmap(
        researcher={
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department
        },
        matched_skills=request.matched_skills,
        skill_gap=skill_data["skill_gap"]
    )
