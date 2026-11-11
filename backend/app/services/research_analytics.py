"""Aggregate research analytics derived only from stored records."""

import time
from collections import Counter, defaultdict

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from ..models import (
    CollaborationRequest,
    FacultyProfile,
    FacultyResearcherLink,
    Researcher,
    ResearcherVerification,
    User,
)
from .skill_gap import normalize_skills
from .verification import effective_status, latest_by_researcher


def _average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _average_of(total: int | None, count: int) -> float | None:
    if total is None or not count:
        return None
    return round(total / count, 1)


def _research_areas(researchers: list[Researcher]) -> Counter:
    counts = Counter()
    for researcher in researchers:
        counts.update(normalize_skills(researcher.research_areas))
    return counts


def _top_areas(counts: Counter) -> list[dict]:
    return [
        {"area": area, "researcher_count": count}
        for area, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def university_summary(db: Session) -> dict:
    researchers = db.query(Researcher).order_by(Researcher.id).all()
    verification = latest_by_researcher(db, [researcher.id for researcher in researchers])
    statuses = [
        effective_status(verification.get(researcher.id)) for researcher in researchers
    ]

    departments = {
        researcher.department.strip().lower()
        for researcher in researchers
        if (researcher.department or "").strip()
    }
    experiences = [
        researcher.experience
        for researcher in researchers
        if researcher.experience is not None
    ]

    area_counts = _research_areas(researchers)

    collaboration_counts = dict(
        db.query(CollaborationRequest.status, func.count(CollaborationRequest.id))
        .group_by(CollaborationRequest.status)
        .all()
    )
    total = sum(collaboration_counts.values())
    accepted = collaboration_counts.get("accepted", 0)
    rejected = collaboration_counts.get("rejected", 0)
    reviewed = accepted + rejected

    account_counts = dict(
        db.query(User.role, func.count(User.id)).group_by(User.role).all()
    )
    active_links = (
        db.query(func.count(FacultyResearcherLink.id))
        .join(User, User.id == FacultyResearcherLink.faculty_user_id)
        .filter(User.is_active.is_(True))
        .scalar()
    )

    return {
        "researchers": {
            "total": len(researchers),
            "departments": len(departments),
            "verified": statuses.count("verified"),
            "pending_verification": statuses.count("pending"),
            "expired_verification": statuses.count("expired"),
            "with_publications": sum(
                1 for researcher in researchers if (researcher.publications or "").strip()
            ),
            "with_projects": sum(
                1 for researcher in researchers if (researcher.projects or "").strip()
            ),
            "average_experience_years": _average(experiences),
        },
        "collaboration": {
            "total": total,
            "pending": collaboration_counts.get("pending", 0),
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": round(accepted / reviewed, 4) if reviewed else None,
        },
        "research_areas": {
            "distinct": len(area_counts),
            "top": _top_areas(area_counts)[:10],
        },
        "accounts": {
            "students": account_counts.get("student", 0),
            "faculty": account_counts.get("faculty", 0),
            "admins": account_counts.get("admin", 0),
            "active_faculty_links": active_links or 0,
        },
    }


def department_rows(
    db: Session,
    *,
    department: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict:
    department_key = func.lower(func.trim(Researcher.department))
    named_department = func.trim(Researcher.department) != ""
    filters = [named_department]
    if department:
        filters.append(department_key == department.strip().lower())

    total = (
        db.query(func.count(func.distinct(department_key)))
        .filter(*filters)
        .scalar()
        or 0
    )

    # The database selects and pages the department keys; only the requested
    # page is expanded into per-researcher detail below.
    page = (
        db.query(
            department_key.label("department_key"),
            func.min(Researcher.id).label("first_id"),
        )
        .filter(*filters)
        .group_by(department_key)
        .order_by(department_key)
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not page:
        return {
            "departments": [],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    page_keys = [row.department_key for row in page]
    first_departments = dict(
        db.query(Researcher.id, Researcher.department)
        .filter(Researcher.id.in_([row.first_id for row in page]))
        .all()
    )
    display_names = {
        row.department_key: (first_departments.get(row.first_id) or "").strip()
        for row in page
    }

    now = int(time.time())
    aggregates = {
        row.department_key: row
        for row in db.query(
            department_key.label("department_key"),
            func.count(Researcher.id).label("researcher_count"),
            func.sum(Researcher.experience).label("experience_total"),
            func.count(Researcher.experience).label("experience_count"),
            func.sum(
                case((func.trim(Researcher.publications) != "", 1), else_=0)
            ).label("with_publications"),
            func.sum(
                case((func.trim(Researcher.projects) != "", 1), else_=0)
            ).label("with_projects"),
        )
        .filter(department_key.in_(page_keys))
        .group_by(department_key)
        .all()
    }

    latest_verification = (
        db.query(
            ResearcherVerification.researcher_id.label("researcher_id"),
            func.max(ResearcherVerification.id).label("verification_id"),
        )
        .group_by(ResearcherVerification.researcher_id)
        .subquery()
    )
    status = case(
        (
            and_(
                ResearcherVerification.status == "verified",
                ResearcherVerification.expires_at.is_not(None),
                ResearcherVerification.expires_at <= now,
            ),
            "expired",
        ),
        (
            and_(
                ResearcherVerification.status == "verified",
                or_(
                    ResearcherVerification.expires_at.is_(None),
                    ResearcherVerification.expires_at > now,
                ),
            ),
            "verified",
        ),
        else_=ResearcherVerification.status,
    )
    status_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for row in (
        db.query(
            department_key.label("department_key"),
            status.label("status"),
            func.count(Researcher.id).label("researcher_count"),
        )
        .select_from(Researcher)
        .outerjoin(
            latest_verification,
            latest_verification.c.researcher_id == Researcher.id,
        )
        .outerjoin(
            ResearcherVerification,
            ResearcherVerification.id == latest_verification.c.verification_id,
        )
        .filter(department_key.in_(page_keys))
        .group_by(department_key, status)
        .all()
    ):
        status_counts[row.department_key][row.status] = row.researcher_count

    designation = func.trim(Researcher.designation)
    designations: dict[str, list[dict]] = defaultdict(list)
    for row in (
        db.query(
            department_key.label("department_key"),
            designation.label("designation"),
            func.count(Researcher.id).label("researcher_count"),
        )
        .filter(department_key.in_(page_keys), designation != "")
        .group_by(department_key, designation)
        .all()
    ):
        designations[row.department_key].append(
            {"designation": row.designation, "count": row.researcher_count}
        )
    for entries in designations.values():
        entries.sort(key=lambda entry: (-entry["count"], entry["designation"]))

    collaboration: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "accepted": 0}
    )
    for row in (
        db.query(
            department_key.label("department_key"),
            CollaborationRequest.status.label("status"),
            func.count(CollaborationRequest.id).label("request_count"),
        )
        .select_from(CollaborationRequest)
        .join(Researcher, Researcher.id == CollaborationRequest.researcher_id)
        .filter(department_key.in_(page_keys))
        .group_by(department_key, CollaborationRequest.status)
        .all()
    ):
        collaboration[row.department_key]["total"] += row.request_count
        if row.status == "accepted":
            collaboration[row.department_key]["accepted"] += row.request_count

    faculty_key = func.lower(func.trim(FacultyProfile.department))
    faculty_accounts = dict(
        db.query(faculty_key, func.count(FacultyProfile.id))
        .join(User, User.id == FacultyProfile.user_id)
        .filter(User.is_active.is_(True), faculty_key.in_(page_keys))
        .group_by(faculty_key)
        .all()
    )

    areas: dict[str, Counter] = {}
    for row in (
        db.query(
            Researcher.id,
            department_key.label("department_key"),
            Researcher.research_areas,
        )
        .filter(department_key.in_(page_keys))
        .order_by(Researcher.id)
        .all()
    ):
        areas.setdefault(row.department_key, Counter()).update(
            normalize_skills(row.research_areas)
        )

    rows = []
    for page_row in page:
        key = page_row.department_key
        aggregate = aggregates[key]
        counts = status_counts.get(key, {})
        rows.append(
            {
                "department": display_names[key],
                "researcher_count": aggregate.researcher_count,
                "average_experience_years": _average_of(
                    aggregate.experience_total, aggregate.experience_count
                ),
                "verified_researcher_count": counts.get("verified", 0),
                "pending_verification_count": counts.get("pending", 0),
                "expired_verification_count": counts.get("expired", 0),
                "researchers_with_publications": aggregate.with_publications or 0,
                "researchers_with_projects": aggregate.with_projects or 0,
                "faculty_account_count": faculty_accounts.get(key, 0),
                "designations": designations.get(key, []),
                "top_research_areas": _top_areas(areas.get(key, Counter()))[:10],
                "collaboration": collaboration.get(
                    key, {"total": 0, "accepted": 0}
                ),
            }
        )

    return {
        "departments": rows,
        "total": total,
        "offset": offset,
        "limit": limit,
    }
