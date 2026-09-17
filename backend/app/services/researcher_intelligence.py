from sqlalchemy.orm import Session

from ..models import Researcher


def build_research_profile(researcher: Researcher) -> str:
    """
    Combine all important researcher information
    into one ML-ready research profile.
    """

    parts = [
        researcher.research_areas,
        researcher.expertise,
        researcher.skills,
        researcher.publications,
        researcher.projects,
    ]

    # Remove empty values
    parts = [
        str(part).strip()
        for part in parts
        if part is not None and str(part).strip()
    ]

    return " ".join(parts)


def get_researcher_profiles(db: Session):
    """
    Return all researchers with their combined
    research profile.
    """

    researchers = db.query(Researcher).all()

    results = []

    for researcher in researchers:
        profile = build_research_profile(researcher)

        results.append(
            {
                "id": researcher.id,
                "name": researcher.name,
                "department": researcher.department,
                "research_profile": profile,
            }
        )

    return results