"""Research opportunities, funding discovery and application tracking."""

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Opportunity,
    OpportunityApplication,
    Researcher,
    StudentProfile,
    User,
)
from ..schemas import (
    FundingImportRequest,
    OpportunityApplicationCreate,
    OpportunityApplicationDecision,
    OpportunityCreate,
    OpportunityMatchRequest,
    OpportunityUpdate,
)
from ..services import funding_sources, opportunities
from ..services.audit import record_event
from ..services.rate_limit import (
    OPPORTUNITY_APPLY_MAX,
    OPPORTUNITY_APPLY_WINDOW_SECONDS,
    RECOMMENDATION_MAX,
    RECOMMENDATION_WINDOW_SECONDS,
    enforce_rate_limit,
)
from .deps import (
    get_optional_user,
    require_admin,
    require_role,
    require_student,
)

router = APIRouter(tags=["Opportunities"])

ACTIVE_APPLICATION_STATUSES = ("pending", "accepted", "rejected")


def _get_opportunity(db: Session, opportunity_id: int) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity


def _student_profile(
    db: Session, user_id: int, message: str
) -> StudentProfile:
    profile = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == user_id)
        .first()
    )
    if profile is None:
        raise HTTPException(status_code=400, detail=message)
    return profile


def _like_pattern(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _research_researcher_id(
    db: Session, payload: OpportunityCreate, user: User
) -> int | None:
    if user.role == "admin":
        if payload.researcher_id is not None:
            if db.get(Researcher, payload.researcher_id) is None:
                raise HTTPException(status_code=404, detail="Researcher not found")
        return payload.researcher_id

    linked = opportunities.linked_researcher_id(db, user.id)
    if linked is None:
        raise HTTPException(
            status_code=403,
            detail="Link your faculty account to a researcher record before creating opportunities",
        )
    if payload.researcher_id not in (None, linked):
        raise HTTPException(
            status_code=422,
            detail="Faculty can only create opportunities for their linked researcher",
        )
    return linked


# --------------------------------------------------
# SEARCH AND LISTING
# --------------------------------------------------

@router.get("/opportunities")
def search_opportunities(
    category: Literal["research", "funding"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    researcher_id: int | None = Query(default=None, ge=1),
    status: Literal["open", "closed"] | None = None,
    deadline_before: int | None = Query(default=None, ge=0),
    deadline_after: int | None = Query(default=None, ge=0),
    eligible_only: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if eligible_only and user is None:
        raise HTTPException(
            status_code=401,
            detail="Sign in to filter opportunities by eligibility",
        )

    query = db.query(Opportunity).filter(
        Opportunity.status.in_(("open", "closed"))
    )
    if category is not None:
        query = query.filter(Opportunity.category == category)
    if researcher_id is not None:
        query = query.filter(Opportunity.researcher_id == researcher_id)
    if status is not None:
        query = query.filter(Opportunity.status == status)
    if deadline_before is not None:
        query = query.filter(Opportunity.deadline_at <= deadline_before)
    if deadline_after is not None:
        query = query.filter(Opportunity.deadline_at >= deadline_after)
    if q:
        pattern = _like_pattern(q.strip())
        query = query.filter(
            or_(
                Opportunity.title.ilike(pattern, escape="\\"),
                Opportunity.description.ilike(pattern, escape="\\"),
                Opportunity.organization.ilike(pattern, escape="\\"),
                Opportunity.required_skills.ilike(pattern, escape="\\"),
                Opportunity.required_research_areas.ilike(pattern, escape="\\"),
                Opportunity.required_expertise.ilike(pattern, escape="\\"),
                Opportunity.eligibility.ilike(pattern, escape="\\"),
            )
        )

    order = (
        case((Opportunity.deadline_at.is_(None), 1), else_=0),
        Opportunity.deadline_at.asc(),
        Opportunity.id.desc(),
    )
    now = int(time.time())

    if eligible_only:
        profile = _student_profile(
            db,
            user.id,
            "Save your student profile before filtering opportunities by eligibility",
        )
        if not opportunities.profile_has_signal(profile):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Add research interests or skills to your student profile "
                    "before filtering opportunities by eligibility"
                ),
            )
        rows = query.order_by(*order).all()
        eligible_rows = [
            opportunity
            for opportunity in rows
            if opportunities.eligibility_for(profile, opportunity, now)["eligible"]
            is True
        ]
        total = len(eligible_rows)
        page = eligible_rows[offset : offset + limit]
    else:
        total = query.order_by(None).count()
        page = query.order_by(*order).offset(offset).limit(limit).all()

    return {
        "opportunities": [
            opportunities.opportunity_payload(opportunity, now)
            for opportunity in page
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/opportunities/mine")
def list_my_opportunities(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_role("faculty", "admin")),
    db: Session = Depends(get_db),
):
    query = db.query(Opportunity)
    if user.role != "admin":
        query = query.filter(Opportunity.created_by_user_id == user.id)

    total = query.order_by(None).count()
    rows = (
        query.order_by(Opportunity.updated_at.desc(), Opportunity.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    now = int(time.time())
    return {
        "opportunities": [
            opportunities.opportunity_payload(opportunity, now)
            for opportunity in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# --------------------------------------------------
# CRUD
# --------------------------------------------------

@router.post("/opportunities", status_code=201)
def create_opportunity(
    payload: OpportunityCreate,
    user: User = Depends(require_role("faculty", "admin")),
    db: Session = Depends(get_db),
):
    if payload.category == "funding":
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only administrators can publish funding opportunities",
            )
        if payload.researcher_id is not None:
            raise HTTPException(
                status_code=422,
                detail="Funding opportunities are institutional and cannot reference a researcher",
            )
        researcher_id = None
    else:
        researcher_id = _research_researcher_id(db, payload, user)

    now = int(time.time())
    opportunity = Opportunity(
        category=payload.category,
        title=payload.title,
        description=payload.description,
        organization=payload.organization,
        location=payload.location,
        url=payload.url,
        deadline_at=payload.deadline_at,
        status=payload.status,
        researcher_id=researcher_id,
        created_by_user_id=user.id,
        required_skills=payload.required_skills,
        required_research_areas=payload.required_research_areas,
        required_expertise=payload.required_expertise,
        eligibility=payload.eligibility,
        created_at=now,
        updated_at=now,
    )
    db.add(opportunity)
    db.flush()
    record_event(
        db,
        actor=user,
        action="opportunity.create",
        target_type="opportunity",
        target_id=opportunity.id,
        detail={"category": opportunity.category, "title": opportunity.title},
    )
    db.commit()
    db.refresh(opportunity)
    return opportunities.opportunity_payload(opportunity)


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    if opportunity.status == "draft" and not opportunities.can_manage(
        db, opportunity, user
    ):
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunities.opportunity_payload(opportunity)


@router.put("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    user: User = Depends(require_role("faculty", "admin")),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    if not opportunities.can_manage(db, opportunity, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage this opportunity",
        )

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(opportunity, field, value)
    opportunity.updated_at = int(time.time())
    record_event(
        db,
        actor=user,
        action="opportunity.update",
        target_type="opportunity",
        target_id=opportunity.id,
        detail={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(opportunity)
    return opportunities.opportunity_payload(opportunity)


@router.delete("/opportunities/{opportunity_id}")
def delete_opportunity(
    opportunity_id: int,
    user: User = Depends(require_role("faculty", "admin")),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    if not opportunities.can_manage(db, opportunity, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage this opportunity",
        )

    record_event(
        db,
        actor=user,
        action="opportunity.delete",
        target_type="opportunity",
        target_id=opportunity.id,
        detail={"title": opportunity.title},
    )
    # Explicit child deletes keep SQLite consistent with PostgreSQL cascades.
    db.query(OpportunityApplication).filter(
        OpportunityApplication.opportunity_id == opportunity.id
    ).delete(synchronize_session=False)
    db.delete(opportunity)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# ELIGIBILITY AND MATCHING
# --------------------------------------------------

@router.get("/opportunities/{opportunity_id}/eligibility")
def opportunity_eligibility(
    opportunity_id: int,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    if opportunity.status == "draft":
        raise HTTPException(status_code=404, detail="Opportunity not found")

    profile = _student_profile(
        db,
        user.id,
        "Save your student profile before evaluating eligibility",
    )
    return opportunities.eligibility_for(profile, opportunity)


@router.post("/students/me/opportunity-matches")
def match_opportunities(
    payload: OpportunityMatchRequest,
    http_request: Request,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _student_profile(
        db,
        user.id,
        "Save your student profile before requesting opportunity matches",
    )
    if not opportunities.profile_has_signal(profile):
        raise HTTPException(
            status_code=400,
            detail=(
                "Add research interests or skills to your student profile "
                "before requesting opportunity matches"
            ),
        )

    enforce_rate_limit(
        db,
        http_request,
        scope="opportunity-matches",
        identities=(("user", str(user.id)),),
        limit=RECOMMENDATION_MAX,
        window_seconds=RECOMMENDATION_WINDOW_SECONDS,
    )

    now = int(time.time())
    candidates = (
        db.query(Opportunity)
        .filter(
            Opportunity.category == payload.category,
            Opportunity.status == "open",
            or_(
                Opportunity.deadline_at.is_(None),
                Opportunity.deadline_at >= now,
            ),
        )
        .order_by(Opportunity.id)
        .all()
    )
    matches, scanned = opportunities.match_opportunities(
        profile,
        candidates,
        top_k=payload.top_k,
        eligible_only=payload.eligible_only,
        now=now,
    )
    return {
        "profile_used": {
            field: getattr(profile, field)
            for field in opportunities.PROFILE_FIELDS
        },
        "method": opportunities.MATCH_METHOD,
        "total_candidates": scanned,
        "matches": matches,
    }


# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------

@router.post("/opportunities/{opportunity_id}/applications", status_code=201)
def apply_to_opportunity(
    opportunity_id: int,
    payload: OpportunityApplicationCreate,
    request: Request,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        db,
        request,
        scope="opportunity-apply",
        identities=(("user", str(user.id)),),
        limit=OPPORTUNITY_APPLY_MAX,
        window_seconds=OPPORTUNITY_APPLY_WINDOW_SECONDS,
    )

    opportunity = _get_opportunity(db, opportunity_id)
    if opportunity.status == "draft":
        raise HTTPException(status_code=404, detail="Opportunity not found")

    now = int(time.time())
    if opportunity.status != "open" or (
        opportunity.deadline_at is not None and opportunity.deadline_at < now
    ):
        raise HTTPException(
            status_code=409,
            detail="This opportunity is not accepting applications",
        )

    existing = (
        db.query(OpportunityApplication)
        .filter(
            OpportunityApplication.opportunity_id == opportunity.id,
            OpportunityApplication.student_user_id == user.id,
            OpportunityApplication.status.in_(ACTIVE_APPLICATION_STATUSES),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="You already have an active application for this opportunity",
        )

    application = OpportunityApplication(
        opportunity_id=opportunity.id,
        student_user_id=user.id,
        message=payload.message,
        status="pending",
        decision_note="",
        created_at=now,
        updated_at=now,
    )
    db.add(application)
    db.flush()
    record_event(
        db,
        actor=user,
        action="opportunity.apply",
        target_type="opportunity",
        target_id=opportunity.id,
        detail={"application_id": application.id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You already have an active application for this opportunity",
        ) from exc
    db.refresh(application)
    return opportunities.application_payload(application)


@router.get("/students/me/opportunity-applications")
def list_my_applications(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    query = (
        db.query(OpportunityApplication, Opportunity)
        .join(Opportunity, Opportunity.id == OpportunityApplication.opportunity_id)
        .filter(OpportunityApplication.student_user_id == user.id)
    )
    total = query.order_by(None).count()
    rows = (
        query.order_by(OpportunityApplication.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    now = int(time.time())
    return {
        "applications": [
            {
                **opportunities.application_payload(application),
                "opportunity": opportunities.opportunity_payload(
                    opportunity, now
                ),
            }
            for application, opportunity in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/opportunities/{opportunity_id}/applications")
def list_opportunity_applications(
    opportunity_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(require_role("faculty", "admin")),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    if not opportunities.can_manage(db, opportunity, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage this opportunity",
        )

    query = db.query(OpportunityApplication).filter(
        OpportunityApplication.opportunity_id == opportunity.id
    )
    total = query.count()
    applications = (
        query.order_by(OpportunityApplication.created_at)
        .offset(offset)
        .limit(limit)
        .all()
    )
    student_ids = {application.student_user_id for application in applications}
    students = {
        student.id: student
        for student in db.query(User)
        .filter(User.id.in_(student_ids))
        .all()
    } if student_ids else {}

    return {
        "applications": [
            {
                **opportunities.application_payload(application),
                "student_full_name": (
                    students[application.student_user_id].full_name
                    if application.student_user_id in students
                    else "Unknown student"
                ),
                "student_email": (
                    students[application.student_user_id].email
                    if application.student_user_id in students
                    else ""
                ),
            }
            for application in applications
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.put("/opportunities/{opportunity_id}/applications/{application_id}")
def decide_application(
    opportunity_id: int,
    application_id: int,
    payload: OpportunityApplicationDecision,
    user: User = Depends(require_role("faculty", "admin")),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    if not opportunities.can_manage(db, opportunity, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage this opportunity",
        )

    application = (
        db.query(OpportunityApplication)
        .filter(
            OpportunityApplication.id == application_id,
            OpportunityApplication.opportunity_id == opportunity.id,
        )
        .first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="This application has already been answered",
        )

    now = int(time.time())
    result = db.execute(
        update(OpportunityApplication)
        .where(
            OpportunityApplication.id == application.id,
            OpportunityApplication.status == "pending",
        )
        .values(
            status="accepted" if payload.decision == "accept" else "rejected",
            decision_note=payload.note,
            reviewed_by_user_id=user.id,
            reviewed_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This application has already been answered",
        )

    record_event(
        db,
        actor=user,
        action="opportunity.decide",
        target_type="opportunity",
        target_id=opportunity.id,
        detail={
            "application_id": application.id,
            "decision": payload.decision,
        },
    )
    db.commit()
    db.refresh(application)
    return opportunities.application_payload(application)


@router.delete("/opportunities/{opportunity_id}/applications/me")
def withdraw_application(
    opportunity_id: int,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity(db, opportunity_id)
    application = (
        db.query(OpportunityApplication)
        .filter(
            OpportunityApplication.opportunity_id == opportunity.id,
            OpportunityApplication.student_user_id == user.id,
            OpportunityApplication.status == "pending",
        )
        .first()
    )
    if application is None:
        decided = (
            db.query(OpportunityApplication)
            .filter(
                OpportunityApplication.opportunity_id == opportunity.id,
                OpportunityApplication.student_user_id == user.id,
                OpportunityApplication.status.in_(("accepted", "rejected")),
            )
            .first()
        )
        if decided is not None:
            raise HTTPException(
                status_code=409,
                detail="Only pending applications can be withdrawn",
            )
        raise HTTPException(status_code=404, detail="Application not found")

    now = int(time.time())
    result = db.execute(
        update(OpportunityApplication)
        .where(
            OpportunityApplication.id == application.id,
            OpportunityApplication.status == "pending",
        )
        .values(status="withdrawn", updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Only pending applications can be withdrawn",
        )

    record_event(
        db,
        actor=user,
        action="opportunity.withdraw",
        target_type="opportunity",
        target_id=opportunity.id,
        detail={"application_id": application.id},
    )
    db.commit()
    db.refresh(application)
    return {
        "withdrawn": True,
        "application": opportunities.application_payload(application),
    }


# --------------------------------------------------
# EXTERNAL FUNDING SOURCES
# --------------------------------------------------

@router.get("/admin/opportunities/sources")
def list_funding_sources(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return funding_sources.sources_payload()


@router.post("/admin/opportunities/import")
def import_funding_opportunities(
    payload: FundingImportRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if payload.source != funding_sources.SOURCE_NAME:
        raise HTTPException(status_code=400, detail="Unknown funding source")
    if not funding_sources.is_enabled():
        raise HTTPException(
            status_code=400,
            detail="Grants.gov funding source is disabled",
        )

    try:
        records = funding_sources.fetch(payload.query, payload.limit)
    except funding_sources.FundingSourceError as exc:
        raise HTTPException(
            status_code=502, detail="Funding source unavailable"
        ) from exc

    now = int(time.time())
    imported: list[Opportunity] = []
    skipped = 0
    seen: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue
        external_id = str(record.get("external_id") or "").strip()
        title = str(record.get("title") or "").strip()
        if not external_id or not title or external_id in seen:
            continue
        seen.add(external_id)

        existing = (
            db.query(Opportunity)
            .filter(
                Opportunity.external_source == funding_sources.SOURCE_NAME,
                Opportunity.external_id == external_id[:200],
            )
            .first()
        )
        if existing is not None:
            skipped += 1
            continue

        deadline = record.get("deadline_at")
        if not isinstance(deadline, int) or isinstance(deadline, bool) or deadline < 0:
            deadline = None
        url = str(record.get("url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            url = ""
        elif len(url) > 300:
            url = ""

        opportunity = Opportunity(
            category="funding",
            title=title[:200],
            description=str(record.get("description") or ""),
            organization=str(record.get("organization") or "")[:200],
            location=str(record.get("location") or "")[:150],
            url=url,
            deadline_at=deadline,
            status="draft",
            researcher_id=None,
            created_by_user_id=user.id,
            required_skills=str(record.get("required_skills") or ""),
            required_research_areas=str(
                record.get("required_research_areas") or ""
            ),
            required_expertise=str(record.get("required_expertise") or ""),
            eligibility=str(record.get("eligibility") or ""),
            external_source=funding_sources.SOURCE_NAME,
            external_id=external_id[:200],
            created_at=now,
            updated_at=now,
        )
        db.add(opportunity)
        imported.append(opportunity)

    record_event(
        db,
        actor=user,
        action="opportunity.import",
        target_type="opportunity",
        target_id=None,
        detail={
            "source": funding_sources.SOURCE_NAME,
            "imported": len(imported),
            "skipped": skipped,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A funding record changed during import; retry",
        ) from exc

    for opportunity in imported:
        db.refresh(opportunity)

    return {
        "source": funding_sources.SOURCE_NAME,
        "imported": len(imported),
        "skipped": skipped,
        "opportunities": [
            opportunities.opportunity_payload(opportunity, now)
            for opportunity in imported
        ],
    }
