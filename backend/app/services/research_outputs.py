"""Shared serialisation and history helpers for research output records."""

import json
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    LiteratureEntry,
    ProposalCitation,
    ProposalCollaborator,
    ProposalSection,
    ProposalVersion,
    PublicationRevision,
    PublicationStatusEvent,
    PublicationSubmission,
    ResearchProposal,
    ThesisMilestone,
    ThesisProgressEvent,
    ThesisRecord,
    User,
)

THESIS_STATUS_TRANSITIONS = {
    "proposed": {"in_progress", "withdrawn"},
    "in_progress": {"submitted", "withdrawn"},
    "submitted": {"defended", "in_progress", "withdrawn"},
    "defended": {"completed", "in_progress"},
    "completed": set(),
    "withdrawn": set(),
}

PUBLICATION_STATUS_TRANSITIONS = {
    "draft": {"submitted", "withdrawn"},
    "submitted": {"under_review", "rejected", "withdrawn"},
    "under_review": {"revision_requested", "accepted", "rejected", "withdrawn"},
    "revision_requested": {"submitted", "withdrawn"},
    "accepted": {"published", "withdrawn"},
    "rejected": set(),
    "published": set(),
    "withdrawn": set(),
}

PUBLICATION_REVISION_STATUSES = {
    "submitted",
    "under_review",
    "revision_requested",
    "accepted",
}


def now() -> int:
    return int(time.time())


def parse_tags(value: str) -> list[str]:
    return [tag for tag in (part.strip() for part in value.split(",")) if tag]


def serialize_tags(tags: list[str]) -> str:
    return ", ".join(tags)


def user_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.full_name if user is not None else None


# --------------------------------------------------
# LITERATURE
# --------------------------------------------------


def literature_payload(entry: LiteratureEntry, citation_count: int = 0) -> dict:
    return {
        "id": entry.id,
        "title": entry.title,
        "authors": entry.authors,
        "venue": entry.venue,
        "year": entry.year,
        "doi": entry.doi,
        "url": entry.url,
        "abstract": entry.abstract,
        "notes": entry.notes,
        "tags": parse_tags(entry.tags),
        "review_status": entry.review_status,
        "citation_key": entry.citation_key,
        "proposal_citation_count": citation_count,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def literature_citation_counts(db: Session, entry_ids: list[int]) -> dict[int, int]:
    if not entry_ids:
        return {}
    rows = (
        db.query(ProposalCitation.literature_entry_id, func.count())
        .filter(ProposalCitation.literature_entry_id.in_(entry_ids))
        .group_by(ProposalCitation.literature_entry_id)
        .all()
    )
    return {entry_id: count for entry_id, count in rows}


# --------------------------------------------------
# PROPOSALS
# --------------------------------------------------


def section_payload(section: ProposalSection) -> dict:
    return {
        "id": section.id,
        "heading": section.heading,
        "body": section.body,
        "position": section.position,
        "created_at": section.created_at,
        "updated_at": section.updated_at,
    }


def collaborator_payload(
    collaborator: ProposalCollaborator, full_name: str | None
) -> dict:
    return {
        "user_id": collaborator.user_id,
        "full_name": full_name,
        "role": collaborator.role,
        "created_at": collaborator.created_at,
    }


def citation_payload(
    citation: ProposalCitation, entry: LiteratureEntry
) -> dict:
    return {
        "id": citation.id,
        "literature_entry_id": entry.id,
        "section_id": citation.section_id,
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "venue": entry.venue,
        "doi": entry.doi,
        "url": entry.url,
        "citation_key": entry.citation_key,
        "created_at": citation.created_at,
    }


def latest_proposal_version(db: Session, proposal_id: int) -> int:
    latest = (
        db.query(func.max(ProposalVersion.version_number))
        .filter(ProposalVersion.proposal_id == proposal_id)
        .scalar()
    )
    return int(latest or 0)


def proposal_version_lock_statement(proposal_id: int):
    return (
        select(ResearchProposal.id)
        .where(ResearchProposal.id == proposal_id)
        .with_for_update()
    )


def lock_proposal_for_versioning(db: Session, proposal_id: int) -> None:
    """Serialize version allocation per proposal (row lock on PostgreSQL)."""
    db.execute(proposal_version_lock_statement(proposal_id)).scalar_one()


def publication_revision_lock_statement(submission_id: int):
    return (
        select(PublicationSubmission.id)
        .where(PublicationSubmission.id == submission_id)
        .with_for_update()
    )


def lock_publication_for_revision(db: Session, submission_id: int) -> None:
    """Serialize revision allocation per submission (row lock on PostgreSQL)."""
    db.execute(publication_revision_lock_statement(submission_id)).scalar_one()


def proposal_snapshot(db: Session, proposal: ResearchProposal) -> dict:
    sections = (
        db.query(ProposalSection)
        .filter(ProposalSection.proposal_id == proposal.id)
        .order_by(ProposalSection.position.asc(), ProposalSection.id.asc())
        .all()
    )
    citations = (
        db.query(ProposalCitation)
        .filter(ProposalCitation.proposal_id == proposal.id)
        .order_by(ProposalCitation.id.asc())
        .all()
    )
    return {
        "title": proposal.title,
        "status": proposal.status,
        "sections": [
            {
                "id": section.id,
                "heading": section.heading,
                "body": section.body,
                "position": section.position,
            }
            for section in sections
        ],
        "citations": [
            {
                "literature_entry_id": citation.literature_entry_id,
                "section_id": citation.section_id,
            }
            for citation in citations
        ],
    }


def record_proposal_version(
    db: Session, proposal: ResearchProposal, actor_user_id: int | None
) -> ProposalVersion:
    db.flush()
    lock_proposal_for_versioning(db, proposal.id)
    version = ProposalVersion(
        proposal_id=proposal.id,
        version_number=latest_proposal_version(db, proposal.id) + 1,
        snapshot=json.dumps(
            proposal_snapshot(db, proposal),
            sort_keys=True,
            separators=(",", ":"),
        ),
        created_by_user_id=actor_user_id,
        created_at=now(),
    )
    db.add(version)
    db.flush()
    return version


def proposal_detail(
    db: Session, proposal: ResearchProposal, access_role: str
) -> dict:
    sections = (
        db.query(ProposalSection)
        .filter(ProposalSection.proposal_id == proposal.id)
        .order_by(ProposalSection.position.asc(), ProposalSection.id.asc())
        .all()
    )
    collaborators = (
        db.query(ProposalCollaborator, User)
        .join(User, ProposalCollaborator.user_id == User.id)
        .filter(ProposalCollaborator.proposal_id == proposal.id)
        .order_by(ProposalCollaborator.id.asc())
        .all()
    )
    citations = (
        db.query(ProposalCitation, LiteratureEntry)
        .join(
            LiteratureEntry,
            ProposalCitation.literature_entry_id == LiteratureEntry.id,
        )
        .filter(ProposalCitation.proposal_id == proposal.id)
        .order_by(ProposalCitation.id.asc())
        .all()
    )
    return {
        "id": proposal.id,
        "title": proposal.title,
        "status": proposal.status,
        "owner": {
            "user_id": proposal.owner_user_id,
            "full_name": user_name(db, proposal.owner_user_id),
        },
        "access_role": access_role,
        "sections": [section_payload(section) for section in sections],
        "collaborators": [
            collaborator_payload(collaborator, user.full_name)
            for collaborator, user in collaborators
        ],
        "citations": [
            citation_payload(citation, entry) for citation, entry in citations
        ],
        "latest_version": latest_proposal_version(db, proposal.id),
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def proposal_summary(
    db: Session, proposal: ResearchProposal, access_role: str
) -> dict:
    section_count = (
        db.query(func.count(ProposalSection.id))
        .filter(ProposalSection.proposal_id == proposal.id)
        .scalar()
    )
    citation_count = (
        db.query(func.count(ProposalCitation.id))
        .filter(ProposalCitation.proposal_id == proposal.id)
        .scalar()
    )
    return {
        "id": proposal.id,
        "title": proposal.title,
        "status": proposal.status,
        "access_role": access_role,
        "section_count": int(section_count or 0),
        "citation_count": int(citation_count or 0),
        "latest_version": latest_proposal_version(db, proposal.id),
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def proposal_version_detail(version: ProposalVersion) -> dict:
    return {
        "version": version.version_number,
        "snapshot": json.loads(version.snapshot),
        "created_by_user_id": version.created_by_user_id,
        "created_at": version.created_at,
    }


# --------------------------------------------------
# THESES
# --------------------------------------------------


def milestone_payload(milestone: ThesisMilestone) -> dict:
    return {
        "id": milestone.id,
        "title": milestone.title,
        "due_at": milestone.due_at,
        "status": milestone.status,
        "position": milestone.position,
        "completed_at": milestone.completed_at,
        "created_by_user_id": milestone.created_by_user_id,
        "created_at": milestone.created_at,
        "updated_at": milestone.updated_at,
    }


def thesis_payload(
    db: Session, thesis: ThesisRecord, access_role: str
) -> dict:
    milestones = (
        db.query(ThesisMilestone)
        .filter(ThesisMilestone.thesis_id == thesis.id)
        .order_by(ThesisMilestone.position.asc(), ThesisMilestone.id.asc())
        .all()
    )
    supervisor = None
    if thesis.supervisor_user_id is not None:
        supervisor = {
            "user_id": thesis.supervisor_user_id,
            "full_name": user_name(db, thesis.supervisor_user_id),
        }
    return {
        "id": thesis.id,
        "title": thesis.title,
        "abstract": thesis.abstract,
        "status": thesis.status,
        "owner": {
            "user_id": thesis.owner_user_id,
            "full_name": user_name(db, thesis.owner_user_id),
        },
        "supervisor": supervisor,
        "access_role": access_role,
        "milestones": [milestone_payload(item) for item in milestones],
        "created_at": thesis.created_at,
        "updated_at": thesis.updated_at,
    }


def thesis_summary(
    db: Session, thesis: ThesisRecord, access_role: str
) -> dict:
    milestone_count = (
        db.query(func.count(ThesisMilestone.id))
        .filter(ThesisMilestone.thesis_id == thesis.id)
        .scalar()
    )
    open_count = (
        db.query(func.count(ThesisMilestone.id))
        .filter(
            ThesisMilestone.thesis_id == thesis.id,
            ThesisMilestone.status == "pending",
        )
        .scalar()
    )
    next_deadline = (
        db.query(func.min(ThesisMilestone.due_at))
        .filter(
            ThesisMilestone.thesis_id == thesis.id,
            ThesisMilestone.status == "pending",
            ThesisMilestone.due_at.is_not(None),
        )
        .scalar()
    )
    return {
        "id": thesis.id,
        "title": thesis.title,
        "status": thesis.status,
        "access_role": access_role,
        "supervisor_user_id": thesis.supervisor_user_id,
        "milestone_count": int(milestone_count or 0),
        "open_milestone_count": int(open_count or 0),
        "next_deadline": next_deadline,
        "created_at": thesis.created_at,
        "updated_at": thesis.updated_at,
    }


def thesis_event_payload(
    event: ThesisProgressEvent, actor_name: str | None
) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "note": event.note,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "milestone_id": event.milestone_id,
        "actor_user_id": event.actor_user_id,
        "actor_name": actor_name,
        "created_at": event.created_at,
    }


def record_thesis_event(
    db: Session,
    thesis: ThesisRecord,
    *,
    actor_user_id: int | None,
    event_type: str,
    note: str = "",
    from_status: str | None = None,
    to_status: str | None = None,
    milestone_id: int | None = None,
) -> ThesisProgressEvent:
    event = ThesisProgressEvent(
        thesis_id=thesis.id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        note=note,
        from_status=from_status,
        to_status=to_status,
        milestone_id=milestone_id,
        created_at=now(),
    )
    db.add(event)
    return event


# --------------------------------------------------
# PUBLICATION SUBMISSIONS
# --------------------------------------------------


def revision_payload(revision: PublicationRevision) -> dict:
    return {
        "id": revision.id,
        "revision_number": revision.revision_number,
        "notes": revision.notes,
        "submitted_at": revision.submitted_at,
        "created_by_user_id": revision.created_by_user_id,
        "created_at": revision.created_at,
    }


def publication_event_payload(
    event: PublicationStatusEvent, actor_name: str | None
) -> dict:
    return {
        "id": event.id,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "note": event.note,
        "actor_user_id": event.actor_user_id,
        "actor_name": actor_name,
        "created_at": event.created_at,
    }


def publication_payload(
    db: Session,
    submission: PublicationSubmission,
    *,
    revision_offset: int = 0,
    revision_limit: int | None = None,
    history_offset: int = 0,
    history_limit: int | None = None,
) -> dict:
    revision_query = db.query(PublicationRevision).filter(
        PublicationRevision.submission_id == submission.id
    )
    revision_total = revision_query.count()
    revisions = (
        revision_query.order_by(PublicationRevision.revision_number.asc())
        .offset(revision_offset)
        .limit(revision_limit)
        .all()
    )
    history_query = (
        db.query(PublicationStatusEvent, User)
        .outerjoin(User, PublicationStatusEvent.actor_user_id == User.id)
        .filter(PublicationStatusEvent.submission_id == submission.id)
    )
    history_total = history_query.count()
    events = (
        history_query.order_by(PublicationStatusEvent.id.desc())
        .offset(history_offset)
        .limit(history_limit)
        .all()
    )
    return {
        "id": submission.id,
        "title": submission.title,
        "venue": submission.venue,
        "venue_type": submission.venue_type,
        "status": submission.status,
        "doi": submission.doi,
        "url": submission.url,
        "notes": submission.notes,
        "submitted_at": submission.submitted_at,
        "decision_at": submission.decision_at,
        "published_at": submission.published_at,
        "revisions": [revision_payload(item) for item in revisions],
        "revisions_total": revision_total,
        "history": [
            publication_event_payload(event, actor.full_name if actor else None)
            for event, actor in events
        ],
        "history_total": history_total,
        "created_at": submission.created_at,
        "updated_at": submission.updated_at,
    }


def publication_summary(db: Session, submission: PublicationSubmission) -> dict:
    return publication_summaries(db, [submission])[0]


def publication_summaries(
    db: Session, submissions: list[PublicationSubmission]
) -> list[dict]:
    if not submissions:
        return []
    latest_revisions = dict(
        db.query(
            PublicationRevision.submission_id,
            func.max(PublicationRevision.revision_number),
        )
        .filter(
            PublicationRevision.submission_id.in_(
                [submission.id for submission in submissions]
            )
        )
        .group_by(PublicationRevision.submission_id)
        .all()
    )
    return [
        {
            "id": submission.id,
            "title": submission.title,
            "venue": submission.venue,
            "venue_type": submission.venue_type,
            "status": submission.status,
            "submitted_at": submission.submitted_at,
            "decision_at": submission.decision_at,
            "published_at": submission.published_at,
            "latest_revision": int(
                latest_revisions.get(submission.id) or 0
            ),
            "created_at": submission.created_at,
            "updated_at": submission.updated_at,
        }
        for submission in submissions
    ]
