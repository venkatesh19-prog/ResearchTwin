"""Research proposal builder: sections, collaborators, citations and versions."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    LiteratureEntry,
    ProposalCitation,
    ProposalCollaborator,
    ProposalSection,
    ProposalVersion,
    ResearchProposal,
    User,
)
from ..schemas import (
    ProposalCitationCreate,
    ProposalCollaboratorCreate,
    ProposalSectionCreate,
    ProposalSectionUpdate,
    ResearchProposalCreate,
    ResearchProposalUpdate,
)
from ..services import research_outputs
from .deps import get_current_user

router = APIRouter(tags=["Proposals"])

PROPOSAL_NOT_FOUND = "Proposal not found"


def _proposal_access(
    db: Session, user: User, proposal_id: int
) -> tuple[ResearchProposal, str]:
    proposal = db.get(ResearchProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND)
    if proposal.owner_user_id == user.id:
        return proposal, "owner"
    collaborator = (
        db.query(ProposalCollaborator)
        .filter(
            ProposalCollaborator.proposal_id == proposal.id,
            ProposalCollaborator.user_id == user.id,
        )
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND)
    return proposal, collaborator.role


def _require_writer(access_role: str) -> None:
    if access_role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Viewers cannot change this proposal",
        )


def _require_owner(access_role: str) -> None:
    if access_role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the proposal owner can perform this action",
        )


def _get_section(
    db: Session, proposal_id: int, section_id: int
) -> ProposalSection:
    section = (
        db.query(ProposalSection)
        .filter(
            ProposalSection.id == section_id,
            ProposalSection.proposal_id == proposal_id,
        )
        .first()
    )
    if section is None:
        raise HTTPException(status_code=404, detail="Proposal section not found")
    return section


def _touch(proposal: ResearchProposal) -> None:
    proposal.updated_at = research_outputs.now()


def _renumber_sections(db: Session, proposal_id: int) -> None:
    remaining = (
        db.query(ProposalSection)
        .filter(ProposalSection.proposal_id == proposal_id)
        .order_by(ProposalSection.position.asc(), ProposalSection.id.asc())
        .all()
    )
    for index, section in enumerate(remaining):
        section.position = index


def _version_summary(version: ProposalVersion) -> dict:
    snapshot = json.loads(version.snapshot)
    return {
        "version": version.version_number,
        "title": snapshot.get("title"),
        "status": snapshot.get("status"),
        "section_count": len(snapshot.get("sections", [])),
        "citation_count": len(snapshot.get("citations", [])),
        "created_by_user_id": version.created_by_user_id,
        "created_at": version.created_at,
    }


@router.get("/proposals")
def list_proposals(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    collaborator_ids = select(ProposalCollaborator.proposal_id).where(
        ProposalCollaborator.user_id == user.id
    )
    query = db.query(ResearchProposal).filter(
        or_(
            ResearchProposal.owner_user_id == user.id,
            ResearchProposal.id.in_(collaborator_ids),
        )
    )
    total = query.order_by(None).count()
    rows = (
        query.order_by(
            ResearchProposal.updated_at.desc(), ResearchProposal.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    roles = {
        collaborator.proposal_id: collaborator.role
        for collaborator in db.query(ProposalCollaborator)
        .filter(
            ProposalCollaborator.user_id == user.id,
            ProposalCollaborator.proposal_id.in_(
                [proposal.id for proposal in rows]
            ),
        )
        .all()
    }
    return {
        "proposals": [
            research_outputs.proposal_summary(
                db,
                proposal,
                "owner"
                if proposal.owner_user_id == user.id
                else roles[proposal.id],
            )
            for proposal in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/proposals", status_code=201)
def create_proposal(
    payload: ResearchProposalCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    timestamp = research_outputs.now()
    proposal = ResearchProposal(
        owner_user_id=user.id,
        title=payload.title,
        status="draft",
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(proposal)
    db.flush()
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    db.refresh(proposal)
    return research_outputs.proposal_detail(db, proposal, "owner")


@router.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    return research_outputs.proposal_detail(db, proposal, access_role)


@router.put("/proposals/{proposal_id}")
def update_proposal(
    proposal_id: int,
    payload: ResearchProposalUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_owner(access_role)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return research_outputs.proposal_detail(db, proposal, access_role)
    for field, value in changes.items():
        setattr(proposal, field, value)
    _touch(proposal)
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    db.refresh(proposal)
    return research_outputs.proposal_detail(db, proposal, access_role)


@router.delete("/proposals/{proposal_id}")
def delete_proposal(
    proposal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_owner(access_role)

    db.query(ProposalCitation).filter(
        ProposalCitation.proposal_id == proposal.id
    ).delete(synchronize_session=False)
    db.query(ProposalVersion).filter(
        ProposalVersion.proposal_id == proposal.id
    ).delete(synchronize_session=False)
    db.query(ProposalSection).filter(
        ProposalSection.proposal_id == proposal.id
    ).delete(synchronize_session=False)
    db.query(ProposalCollaborator).filter(
        ProposalCollaborator.proposal_id == proposal.id
    ).delete(synchronize_session=False)
    db.delete(proposal)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# COLLABORATORS
# --------------------------------------------------


@router.post("/proposals/{proposal_id}/collaborators", status_code=201)
def add_proposal_collaborator(
    proposal_id: int,
    payload: ProposalCollaboratorCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_owner(access_role)

    if payload.user_id == proposal.owner_user_id:
        raise HTTPException(
            status_code=422,
            detail="The proposal owner already has full access",
        )
    collaborator_user = db.get(User, payload.user_id)
    if collaborator_user is None or not collaborator_user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    existing = (
        db.query(ProposalCollaborator)
        .filter(
            ProposalCollaborator.proposal_id == proposal.id,
            ProposalCollaborator.user_id == payload.user_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="This user is already a collaborator"
        )

    collaborator = ProposalCollaborator(
        proposal_id=proposal.id,
        user_id=payload.user_id,
        role=payload.role,
        created_at=research_outputs.now(),
    )
    db.add(collaborator)
    db.commit()
    db.refresh(collaborator)
    return research_outputs.collaborator_payload(
        collaborator, collaborator_user.full_name
    )


@router.delete("/proposals/{proposal_id}/collaborators/{user_id}")
def remove_proposal_collaborator(
    proposal_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_owner(access_role)

    collaborator = (
        db.query(ProposalCollaborator)
        .filter(
            ProposalCollaborator.proposal_id == proposal.id,
            ProposalCollaborator.user_id == user_id,
        )
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    db.delete(collaborator)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# SECTIONS
# --------------------------------------------------


@router.post("/proposals/{proposal_id}/sections", status_code=201)
def add_proposal_section(
    proposal_id: int,
    payload: ProposalSectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_writer(access_role)

    position = (
        db.query(ProposalSection)
        .filter(ProposalSection.proposal_id == proposal.id)
        .count()
    )
    timestamp = research_outputs.now()
    section = ProposalSection(
        proposal_id=proposal.id,
        heading=payload.heading,
        body=payload.body,
        position=position,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(section)
    _touch(proposal)
    db.flush()
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    db.refresh(section)
    return research_outputs.section_payload(section)


@router.put("/proposals/{proposal_id}/sections/{section_id}")
def update_proposal_section(
    proposal_id: int,
    section_id: int,
    payload: ProposalSectionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_writer(access_role)
    section = _get_section(db, proposal.id, section_id)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return research_outputs.section_payload(section)
    for field, value in changes.items():
        setattr(section, field, value)
    section.updated_at = research_outputs.now()
    _touch(proposal)
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    db.refresh(section)
    return research_outputs.section_payload(section)


@router.delete("/proposals/{proposal_id}/sections/{section_id}")
def delete_proposal_section(
    proposal_id: int,
    section_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_writer(access_role)
    section = _get_section(db, proposal.id, section_id)

    db.query(ProposalCitation).filter(
        ProposalCitation.section_id == section.id
    ).update({"section_id": None}, synchronize_session=False)
    db.delete(section)
    db.flush()
    _renumber_sections(db, proposal.id)
    _touch(proposal)
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# CITATIONS
# --------------------------------------------------


@router.post("/proposals/{proposal_id}/citations", status_code=201)
def add_proposal_citation(
    proposal_id: int,
    payload: ProposalCitationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_writer(access_role)

    entry = db.get(LiteratureEntry, payload.literature_entry_id)
    if entry is None or entry.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Literature entry not found")

    if payload.section_id is not None:
        _get_section(db, proposal.id, payload.section_id)

    existing = (
        db.query(ProposalCitation)
        .filter(
            ProposalCitation.proposal_id == proposal.id,
            ProposalCitation.literature_entry_id == entry.id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This reference is already cited in the proposal",
        )

    citation = ProposalCitation(
        proposal_id=proposal.id,
        literature_entry_id=entry.id,
        section_id=payload.section_id,
        created_by_user_id=user.id,
        created_at=research_outputs.now(),
    )
    db.add(citation)
    _touch(proposal)
    db.flush()
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    db.refresh(citation)
    return research_outputs.citation_payload(citation, entry)


@router.delete("/proposals/{proposal_id}/citations/{citation_id}")
def delete_proposal_citation(
    proposal_id: int,
    citation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, access_role = _proposal_access(db, user, proposal_id)
    _require_writer(access_role)

    citation = (
        db.query(ProposalCitation)
        .filter(
            ProposalCitation.id == citation_id,
            ProposalCitation.proposal_id == proposal.id,
        )
        .first()
    )
    if citation is None:
        raise HTTPException(status_code=404, detail="Citation not found")
    db.delete(citation)
    _touch(proposal)
    research_outputs.record_proposal_version(db, proposal, user.id)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------
# VERSIONS
# --------------------------------------------------


@router.get("/proposals/{proposal_id}/versions")
def list_proposal_versions(
    proposal_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, _ = _proposal_access(db, user, proposal_id)
    query = db.query(ProposalVersion).filter(
        ProposalVersion.proposal_id == proposal.id
    )
    total = query.count()
    versions = (
        query.order_by(ProposalVersion.version_number.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "versions": [_version_summary(version) for version in versions],
        "total": total,
    }


@router.get("/proposals/{proposal_id}/versions/{version}")
def get_proposal_version(
    proposal_id: int,
    version: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal, _ = _proposal_access(db, user, proposal_id)
    row = (
        db.query(ProposalVersion)
        .filter(
            ProposalVersion.proposal_id == proposal.id,
            ProposalVersion.version_number == version,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal version not found")
    return research_outputs.proposal_version_detail(row)
