from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..services.matching import rank_researchers


router = APIRouter(
    prefix="/students",
    tags=["Students"]
)


class StudentProfile(BaseModel):
    profile: str
    top_k: int = 5


@router.post("/recommendations")
def get_recommendations(
    student: StudentProfile,
    db: Session = Depends(get_db)
):
    results = rank_researchers(
        student_profile=student.profile,
        db=db,
        top_k=student.top_k
    )

    return {
        "student_profile": student.profile,
        "recommendations": results
    }