import re

from ..models import Researcher


def normalize_skills(text: str | None) -> set[str]:
    """
    Convert a comma-separated skill string into
    a normalized set of skills.
    """

    if not text:
        return set()

    skills = re.split(r",|;|\n", text)

    return {
        skill.strip().lower()
        for skill in skills
        if skill.strip()
    }


def calculate_skill_gap(
    student_skills: str,
    researcher: Researcher
) -> dict:
    """
    Compare student skills with researcher skills.
    """

    student_skill_set = normalize_skills(
        student_skills
    )

    researcher_skill_set = normalize_skills(
        researcher.skills
    )

    matched_skills = (
        student_skill_set
        & researcher_skill_set
    )

    missing_skills = (
        researcher_skill_set
        - student_skill_set
    )

    return {
        "researcher_id": researcher.id,
        "researcher_name": researcher.name,
        "matched_skills": sorted(
            matched_skills
        ),
        "skill_gap": sorted(
            missing_skills
        ),
        "student_skill_count": len(
            student_skill_set
        ),
        "researcher_skill_count": len(
            researcher_skill_set
        )
    }