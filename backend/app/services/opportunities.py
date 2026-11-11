"""Shared opportunity visibility, eligibility and matching helpers.

Matching is intentionally transparent: it combines the existing profile
similarity helpers and exposes every signal it used. It never reuses the
seven-feature collaboration model's score as an opportunity match.
"""

import time

from sqlalchemy.orm import Session

from ..models import FacultyResearcherLink, Opportunity, StudentProfile, User
from .recommendation import (
    calculate_skill_overlap,
    calculate_tfidf_similarity,
    field_similarity,
)
from .semantic_matching import build_student_text
from .skill_gap import normalize_skills

PROFILE_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
)

ELIGIBILITY_PROFILE_FIELDS = ("research_areas", "expertise", "skills")

MATCH_METHOD = "transparent_similarity_v1"

SIGNAL_WEIGHTS = {
    "research_area_similarity": 0.3,
    "expertise_similarity": 0.2,
    "skill_overlap": 0.3,
    "text_similarity": 0.2,
}


def opportunity_payload(opportunity: Opportunity, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    deadline_passed = (
        opportunity.deadline_at is not None and opportunity.deadline_at < now
    )
    return {
        "id": opportunity.id,
        "category": opportunity.category,
        "title": opportunity.title,
        "description": opportunity.description,
        "organization": opportunity.organization,
        "location": opportunity.location,
        "url": opportunity.url,
        "deadline_at": opportunity.deadline_at,
        "deadline_passed": deadline_passed,
        "status": opportunity.status,
        "is_open": opportunity.status == "open" and not deadline_passed,
        "researcher_id": opportunity.researcher_id,
        "created_by_user_id": opportunity.created_by_user_id,
        "required_skills": opportunity.required_skills,
        "required_research_areas": opportunity.required_research_areas,
        "required_expertise": opportunity.required_expertise,
        "eligibility": opportunity.eligibility,
        "external_source": opportunity.external_source,
        "external_id": opportunity.external_id,
        "created_at": opportunity.created_at,
        "updated_at": opportunity.updated_at,
    }


def application_payload(application) -> dict:
    return {
        "id": application.id,
        "opportunity_id": application.opportunity_id,
        "student_user_id": application.student_user_id,
        "message": application.message,
        "status": application.status,
        "decision_note": application.decision_note,
        "reviewed_by_user_id": application.reviewed_by_user_id,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
        "reviewed_at": application.reviewed_at,
    }


def linked_researcher_id(db: Session, user_id: int) -> int | None:
    link = (
        db.query(FacultyResearcherLink)
        .filter(FacultyResearcherLink.faculty_user_id == user_id)
        .first()
    )
    return link.researcher_id if link is not None else None


def can_manage(db: Session, opportunity: Opportunity, user: User | None) -> bool:
    """Admins, creators and the linked faculty owner can manage an opportunity."""
    if user is None:
        return False
    if user.role == "admin":
        return True
    if opportunity.created_by_user_id == user.id:
        return True
    if opportunity.category == "research" and opportunity.researcher_id is not None:
        return linked_researcher_id(db, user.id) == opportunity.researcher_id
    return False


def profile_has_signal(profile: StudentProfile | None) -> bool:
    if profile is None:
        return False
    return any(
        str(getattr(profile, field) or "").strip() for field in PROFILE_FIELDS
    )


def eligibility_for(
    profile: StudentProfile,
    opportunity: Opportunity,
    now: int | None = None,
) -> dict:
    """Evaluate eligibility from stored profile data only.

    A student who has not listed skills has an unknown skills position, not a
    confirmed gap, so ``eligible`` stays ``null`` rather than inventing
    missing skills.
    """
    now = int(time.time()) if now is None else now
    deadline_passed = (
        opportunity.deadline_at is not None and opportunity.deadline_at < now
    )
    student_skills = normalize_skills(profile.skills)
    required_skills = normalize_skills(opportunity.required_skills)
    profile_ready = any(
        str(getattr(profile, field) or "").strip()
        for field in ELIGIBILITY_PROFILE_FIELDS
    )

    reasons: list[str] = []
    if opportunity.status != "open":
        reasons.append("This opportunity is not open.")
    if deadline_passed:
        reasons.append("The application deadline has passed.")

    if required_skills and not student_skills:
        reasons.append(
            "Add skills to your student profile to evaluate the skill requirements."
        )
        return {
            "opportunity_id": opportunity.id,
            "status": opportunity.status,
            "deadline_passed": deadline_passed,
            "profile_ready": profile_ready,
            "student_skills_provided": False,
            # A closed or expired opportunity is ineligible regardless of the
            # unknown skills position.
            "eligible": False if reasons[:-1] else None,
            "matched_skills": [],
            "missing_skills": [],
            "reasons": reasons,
        }

    matched = sorted(required_skills & student_skills)
    missing = sorted(required_skills - student_skills)
    if reasons:
        eligible: bool | None = False
    elif required_skills:
        eligible = not missing
        if missing:
            reasons.append("Missing required skills: " + ", ".join(missing) + ".")
    else:
        eligible = True
        reasons.append("No required skills are listed for this opportunity.")

    return {
        "opportunity_id": opportunity.id,
        "status": opportunity.status,
        "deadline_passed": deadline_passed,
        "profile_ready": profile_ready,
        "student_skills_provided": bool(student_skills),
        "eligible": eligible,
        "matched_skills": matched,
        "missing_skills": missing,
        "reasons": reasons,
    }


def _opportunity_text(opportunity: Opportunity) -> str:
    return " ".join(
        part
        for part in (
            opportunity.title,
            opportunity.description,
            opportunity.organization,
            opportunity.required_research_areas,
            opportunity.required_expertise,
            opportunity.required_skills,
            opportunity.eligibility,
        )
        if str(part or "").strip()
    )


def _signals(profile: StudentProfile, opportunity: Opportunity) -> dict:
    signals: dict[str, float] = {}
    if (
        str(opportunity.required_research_areas or "").strip()
        and str(profile.research_areas or "").strip()
    ):
        signals["research_area_similarity"] = round(
            float(
                field_similarity(
                    profile.research_areas,
                    opportunity.required_research_areas,
                )
            ),
            4,
        )
    if (
        str(opportunity.required_expertise or "").strip()
        and str(profile.expertise or "").strip()
    ):
        signals["expertise_similarity"] = round(
            float(field_similarity(profile.expertise, opportunity.required_expertise)),
            4,
        )
    if str(opportunity.required_skills or "").strip():
        signals["skill_overlap"] = round(
            float(
                calculate_skill_overlap(
                    profile.skills, opportunity.required_skills
                )
            ),
            4,
        )
    student_text = build_student_text(
        {field: getattr(profile, field) for field in PROFILE_FIELDS}
    )
    opportunity_text = _opportunity_text(opportunity)
    if student_text.strip() and opportunity_text.strip():
        signals["text_similarity"] = round(
            float(calculate_tfidf_similarity(student_text, opportunity_text)),
            4,
        )
    return signals


def _score(signals: dict[str, float]) -> float:
    weights = {
        name: SIGNAL_WEIGHTS[name]
        for name in signals
        if name in SIGNAL_WEIGHTS
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return 0.0
    return round(
        sum(signals[name] * weights[name] for name in weights) / total_weight,
        4,
    )


def match_opportunities(
    profile: StudentProfile,
    opportunities: list[Opportunity],
    *,
    top_k: int,
    eligible_only: bool,
    now: int | None = None,
) -> tuple[list[dict], int]:
    """Return positive-signal matches and the number of candidates scanned.

    Candidates with no positive signal are omitted instead of being surfaced
    as zero-score matches.
    """
    now = int(time.time()) if now is None else now
    matches = []
    for opportunity in opportunities:
        eligibility = eligibility_for(profile, opportunity, now)
        if eligible_only and eligibility["eligible"] is not True:
            continue
        signals = _signals(profile, opportunity)
        score = _score(signals)
        if score <= 0:
            continue
        matches.append(
            {
                "opportunity": opportunity_payload(opportunity, now),
                "match_score": score,
                "signals": signals,
                "eligibility": eligibility,
            }
        )

    matches.sort(key=lambda item: (-item["match_score"], item["opportunity"]["id"]))
    return matches[:top_k], len(opportunities)
