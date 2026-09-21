from sqlalchemy.orm import Session

from ..models import Researcher


def clean_text(value) -> str:
    """
    Convert a database field into clean text.
    """

    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def build_research_profile(researcher: Researcher) -> str:
    """
    Build one combined research profile.
    """

    parts = [
        researcher.research_areas,
        researcher.expertise,
        researcher.skills,
        researcher.publications,
        researcher.projects,
    ]

    cleaned_parts = [
        clean_text(part)
        for part in parts
        if clean_text(part)
    ]

    return " ".join(cleaned_parts)


def build_structured_profile(researcher: Researcher) -> dict:
    """
    Build a structured researcher representation.

    Each research dimension is kept separately so that
    the recommendation engine can later calculate
    different similarity signals.
    """

    return {
        "research_areas": clean_text(
            researcher.research_areas
        ),

        "expertise": clean_text(
            researcher.expertise
        ),

        "skills": clean_text(
            researcher.skills
        ),

        "publications": clean_text(
            researcher.publications
        ),

        "projects": clean_text(
            researcher.projects
        ),

        "combined_profile": build_research_profile(
            researcher
        ),
    }


def get_researcher_profiles(db: Session):
    """
    Return structured research profiles for all researchers.
    """

    researchers = db.query(Researcher).all()

    results = []

    for researcher in researchers:

        profile = build_structured_profile(
            researcher
        )

        results.append(
            {
                "id": researcher.id,
                "name": researcher.name,
                "department": researcher.department,
                "designation": researcher.designation,
                "experience": researcher.experience,
                **profile,
            }
        )

    return results