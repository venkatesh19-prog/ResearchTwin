"""Directory-wide expertise gap analysis for one student profile.

Terms are compared per kind (skill, expertise, research area) after the same
normalization the roadmap uses. Only terms the student has not already listed
become gaps, so an empty profile never looks like a total gap.
"""

from collections import defaultdict

from ..models import Researcher, ResearcherVerification, StudentProfile
from .skill_gap import normalize_skills
from .verification import effective_status

KINDS = (
    ("skill", "skills"),
    ("expertise", "expertise"),
    ("research_area", "research_areas"),
)


def _student_terms(profile: StudentProfile) -> dict[str, set[str]]:
    return {
        kind: normalize_skills(getattr(profile, attribute))
        for kind, attribute in KINDS
    }


def analyze(
    profile: StudentProfile,
    researchers: list[Researcher],
    verification_by_researcher: dict[int, ResearcherVerification],
    *,
    limit: int = 25,
    verified_only: bool = False,
) -> dict:
    student_terms = _student_terms(profile)
    student_skills_provided = bool(student_terms["skill"])

    result = {
        "student_skills_provided": student_skills_provided,
        "student_terms": {
            "skills": sorted(student_terms["skill"]),
            "expertise": sorted(student_terms["expertise"]),
            "research_areas": sorted(student_terms["research_area"]),
        },
        "gaps": [],
        "total_gaps": 0,
        "recommended_researchers": [],
        "limit": limit,
        "verified_only": verified_only,
    }

    if not student_skills_provided:
        return result

    eligible: list[tuple[Researcher, str]] = []
    for researcher in researchers:
        status = effective_status(
            verification_by_researcher.get(researcher.id)
        )
        if verified_only and status != "verified":
            continue
        eligible.append((researcher, status))

    known_terms: set[str] = set().union(*student_terms.values())
    contributors: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
    briefs: dict[int, dict] = {}

    for researcher, status in eligible:
        brief = {
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department,
            "verification_status": status,
        }
        briefs[researcher.id] = brief
        for kind, attribute in KINDS:
            for term in normalize_skills(getattr(researcher, attribute)):
                if term in known_terms:
                    continue
                contributors[(kind, term)][researcher.id] = brief

    rows = []
    for (kind, term), members in contributors.items():
        ordered = sorted(members.values(), key=lambda row: (row["name"], row["researcher_id"]))
        rows.append(
            {
                "term": term,
                "kind": kind,
                "researcher_count": len(members),
                "researchers": ordered[:3],
            }
        )
    rows.sort(key=lambda row: (-row["researcher_count"], row["term"], row["kind"]))

    covered: dict[int, list[str]] = defaultdict(list)
    for (kind, term), members in contributors.items():
        for researcher_id in members:
            covered[researcher_id].append(term)

    recommended = []
    for researcher_id, terms in covered.items():
        addressed = sorted(set(terms))
        if not addressed:
            continue
        recommended.append(
            {
                **briefs[researcher_id],
                "gap_coverage": len(addressed),
                "addressed_gaps": addressed,
            }
        )
    recommended.sort(
        key=lambda row: (
            -row["gap_coverage"],
            row["name"],
            row["researcher_id"],
        )
    )

    result["gaps"] = rows[:limit]
    result["total_gaps"] = len(rows)
    result["recommended_researchers"] = recommended[:10]
    return result
