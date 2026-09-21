from sqlalchemy.orm import Session

from ..models import Researcher
from .researcher_similarity import rank_researchers_weighted
from .recommendation_explanation import explain_match
from .skill_gap import calculate_skill_gap


def generate_recommendations(
    student_profile: dict,
    db: Session,
    top_k: int = 5
):
    """
    Generate complete ResearchTwin recommendations.

    Pipeline:
    Student Profile
        ↓
    Weighted Similarity
        ↓
    Explanation
        ↓
    Skill Gap
        ↓
    Final Recommendations
    """

    researchers = db.query(Researcher).all()

    if not researchers:
        return []

    # ---------------------------------------------
    # STEP 1: Calculate weighted similarity
    # ---------------------------------------------

    ranked_results = rank_researchers_weighted(
        student_profile=student_profile,
        researchers=researchers,
        top_k=top_k
    )

    final_results = []

    # ---------------------------------------------
    # STEP 2: Add explanation + skill gap
    # ---------------------------------------------

    for result in ranked_results:

        researcher = next(
            (
                r
                for r in researchers
                if r.id == result["researcher_id"]
            ),
            None
        )

        if researcher is None:
            continue

        explanation = explain_match(
            result
        )

        skill_gap = calculate_skill_gap(
            student_profile.get("skills", ""),
            researcher
        )

        final_results.append(
            {
                "researcher_id": result["researcher_id"],
                "name": result["name"],
                "department": result["department"],
                "match_score": explanation["match_score"],

                "component_scores": result[
                    "component_scores"
                ],

                "why_recommended": explanation[
                    "why_recommended"
                ],

                "matched_skills": skill_gap[
                    "matched_skills"
                ],

                "skill_gap": skill_gap[
                    "skill_gap"
                ]
            }
        )

    return final_results