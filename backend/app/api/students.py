from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.recommendation import generate_recommendations


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