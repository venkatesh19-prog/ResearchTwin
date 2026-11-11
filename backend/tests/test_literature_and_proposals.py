"""Literature/reference management and research proposal collaboration."""

import pytest

from app.database import SessionLocal
from app.models import (
    LiteratureEntry,
    ProposalCitation,
    ProposalCollaborator,
    ProposalSection,
    ProposalVersion,
    ResearchProposal,
)
from conftest import register_test_account

LITERATURE = "/literature"
PROPOSALS = "/proposals"
PROFILE_FIELDS = (
    "research_areas",
    "expertise",
    "skills",
    "projects",
    "publications",
    "courses",
    "academic_details",
)


@pytest.fixture(autouse=True)
def clean_literature_tables():
    session = SessionLocal()
    try:
        session.query(ProposalCitation).delete()
        session.query(ProposalVersion).delete()
        session.query(ProposalSection).delete()
        session.query(ProposalCollaborator).delete()
        session.query(ResearchProposal).delete()
        session.query(LiteratureEntry).delete()
        session.commit()
    finally:
        session.close()
    yield


def _student(client, publications="Legacy free-text publication"):
    headers, user = register_test_account(client, role="student")
    saved = client.put(
        "/students/me/profile",
        json={
            **{field: "" for field in PROFILE_FIELDS},
            "publications": publications,
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    return headers, user


def _entry(client, headers, **overrides):
    payload = {
        "title": "Attention Is All You Need",
        "authors": "Vaswani et al.",
        "venue": "NeurIPS",
        "year": 2017,
        "doi": "10.5555/attention",
        "url": "https://example.org/attention",
        "abstract": "Transformer architecture.",
        "notes": "Read the multi-head attention section.",
        "tags": ["NLP", "deep learning"],
        "review_status": "to_read",
        "citation_key": None,
    }
    payload.update(overrides)
    return client.post(LITERATURE, json=payload, headers=headers)


def _proposal(client, headers, title="Adaptive Retrieval Research Proposal"):
    response = client.post(PROPOSALS, json={"title": title}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _section(client, headers, proposal_id, heading, body="Draft text"):
    response = client.post(
        f"{PROPOSALS}/{proposal_id}/sections",
        json={"heading": heading, "body": body},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _collaborator(client, headers, proposal_id, user_id, role):
    response = client.post(
        f"{PROPOSALS}/{proposal_id}/collaborators",
        json={"user_id": user_id, "role": role},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------
# LITERATURE / REFERENCE MANAGER
# --------------------------------------------------


def test_literature_endpoints_require_authentication(client):
    assert client.get(LITERATURE).status_code == 401
    assert client.post(LITERATURE, json={"title": "Paper"}).status_code == 401


def test_literature_crud_preserves_legacy_profile_publications(client):
    headers, _ = _student(client)
    created = _entry(
        client,
        headers,
        title="  Attention Is All You Need  ",
        tags=["NLP", "nlp", " Deep Learning "],
        review_status="reading",
        citation_key="vaswani2017",
    )
    assert created.status_code == 201, created.text
    body = created.json()
    entry_id = body["id"]
    assert body["title"] == "Attention Is All You Need"
    assert body["tags"] == ["nlp", "deep learning"]
    assert body["review_status"] == "reading"
    assert body["citation_key"] == "vaswani2017"
    assert body["proposal_citation_count"] == 0

    detail = client.get(f"{LITERATURE}/{entry_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["notes"] == "Read the multi-head attention section."

    updated = client.put(
        f"{LITERATURE}/{entry_id}",
        json={
            "review_status": "reviewed",
            "notes": "Summarised for the related-work section.",
            "tags": [],
            "year": None,
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["review_status"] == "reviewed"
    assert updated.json()["tags"] == []
    assert updated.json()["year"] is None

    profile = client.get("/students/me/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["publications"] == "Legacy free-text publication"

    deleted = client.delete(f"{LITERATURE}/{entry_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert client.get(f"{LITERATURE}/{entry_id}", headers=headers).status_code == 404


def test_literature_is_private_to_its_owner(client):
    owner_headers, _ = _student(client)
    other_headers, _ = _student(client)
    entry_id = _entry(client, owner_headers).json()["id"]

    assert client.get(f"{LITERATURE}/{entry_id}", headers=other_headers).status_code == 404
    assert (
        client.put(
            f"{LITERATURE}/{entry_id}",
            json={"notes": "hijack"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"{LITERATURE}/{entry_id}", headers=other_headers).status_code
        == 404
    )
    listing = client.get(LITERATURE, headers=other_headers)
    assert listing.status_code == 200
    assert listing.json()["entries"] == []


def test_literature_search_status_and_tag_filters(client):
    headers, _ = _student(client)
    _entry(client, headers, title="Graph Neural Networks", tags=["graphs"], notes="")
    _entry(
        client,
        headers,
        title="Attention Is All You Need",
        tags=["nlp", "deep learning"],
        review_status="reviewed",
    )
    _entry(
        client,
        headers,
        title="Secure Compilers",
        tags=["security"],
        review_status="reading",
        notes="",
    )

    by_text = client.get(f"{LITERATURE}?q=attention", headers=headers).json()
    assert by_text["total"] == 1
    assert by_text["entries"][0]["title"] == "Attention Is All You Need"

    by_status = client.get(
        f"{LITERATURE}?review_status=reading", headers=headers
    ).json()
    assert [entry["title"] for entry in by_status["entries"]] == [
        "Secure Compilers"
    ]

    by_tag = client.get(f"{LITERATURE}?tag=deep%20learning", headers=headers).json()
    assert by_tag["total"] == 1
    assert by_tag["entries"][0]["title"] == "Attention Is All You Need"

    missing = client.get(f"{LITERATURE}?tag=missing", headers=headers).json()
    assert missing == {"entries": [], "total": 0, "offset": 0, "limit": 50}

    page = client.get(f"{LITERATURE}?limit=1&offset=1", headers=headers).json()
    assert page["total"] == 3
    assert len(page["entries"]) == 1


def test_literature_validation_and_citation_key_uniqueness(client):
    headers, _ = _student(client)

    assert (
        client.post(LITERATURE, json={"title": "   "}, headers=headers).status_code
        == 422
    )
    assert (
        client.post(
            LITERATURE,
            json={"title": "Paper", "review_status": "skimmed"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            LITERATURE,
            json={"title": "Paper", "url": "ftp://example.org/paper"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            LITERATURE,
            json={"title": "Paper", "tags": ["x" * 60]},
            headers=headers,
        ).status_code
        == 422
    )

    assert (
        _entry(client, headers, citation_key="samekey").status_code == 201
    )
    duplicate = _entry(
        client, headers, title="Another paper", citation_key="samekey"
    )
    assert duplicate.status_code == 409


# --------------------------------------------------
# PROPOSAL BUILDER
# --------------------------------------------------


def test_proposal_lifecycle_sections_collaborators_and_versions(
    client, seeded_db
):
    owner_headers, owner = _student(client)
    editor_headers, editor = _student(client)
    viewer_headers, viewer = _student(client)
    outsider_headers, _ = _student(client)

    proposal = _proposal(client, owner_headers)
    proposal_id = proposal["id"]
    assert proposal["status"] == "draft"
    assert proposal["access_role"] == "owner"
    assert proposal["sections"] == []
    assert proposal["collaborators"] == []
    assert proposal["citations"] == []
    assert proposal["latest_version"] == 1
    assert proposal["owner"] == {"user_id": owner["id"], "full_name": owner["full_name"]}

    first = _section(client, owner_headers, proposal_id, "Introduction")
    second = _section(client, owner_headers, proposal_id, "Methods")
    assert (first["position"], second["position"]) == (0, 1)

    _collaborator(client, owner_headers, proposal_id, editor["id"], "editor")
    _collaborator(client, owner_headers, proposal_id, viewer["id"], "viewer")

    edited = client.put(
        f"{PROPOSALS}/{proposal_id}/sections/{first['id']}",
        json={"body": "Edited by a collaborator."},
        headers=editor_headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["body"] == "Edited by a collaborator."

    detail = client.get(f"{PROPOSALS}/{proposal_id}", headers=editor_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["access_role"] == "editor"
    assert body["latest_version"] == 4
    assert [section["heading"] for section in body["sections"]] == [
        "Introduction",
        "Methods",
    ]
    assert {item["role"] for item in body["collaborators"]} == {"editor", "viewer"}

    versions = client.get(f"{PROPOSALS}/{proposal_id}/versions", headers=viewer_headers)
    assert versions.status_code == 200, versions.text
    assert [item["version"] for item in versions.json()["versions"]] == [4, 3, 2, 1]
    snapshot = client.get(
        f"{PROPOSALS}/{proposal_id}/versions/4", headers=viewer_headers
    )
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["snapshot"]["sections"][0]["body"] == (
        "Edited by a collaborator."
    )

    viewer_read = client.get(f"{PROPOSALS}/{proposal_id}", headers=viewer_headers)
    assert viewer_read.status_code == 200
    assert viewer_read.json()["access_role"] == "viewer"
    assert (
        client.post(
            f"{PROPOSALS}/{proposal_id}/sections",
            json={"heading": "Forbidden"},
            headers=viewer_headers,
        ).status_code
        == 403
    )

    assert client.get(f"{PROPOSALS}/{proposal_id}", headers=outsider_headers).status_code == 404
    assert (
        client.post(
            f"{PROPOSALS}/{proposal_id}/collaborators",
            json={"user_id": viewer["id"], "role": "editor"},
            headers=editor_headers,
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"{PROPOSALS}/{proposal_id}",
            json={"title": "Editor cannot rename"},
            headers=editor_headers,
        ).status_code
        == 403
    )

    removed = client.delete(
        f"{PROPOSALS}/{proposal_id}/sections/{second['id']}",
        headers=editor_headers,
    )
    assert removed.status_code == 200, removed.text
    remaining = client.get(f"{PROPOSALS}/{proposal_id}", headers=owner_headers)
    assert remaining.json()["sections"][0]["position"] == 0
    assert remaining.json()["latest_version"] == 5

    deleted = client.delete(f"{PROPOSALS}/{proposal_id}", headers=owner_headers)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"{PROPOSALS}/{proposal_id}", headers=owner_headers).status_code == 404

    session = SessionLocal()
    try:
        assert session.query(ResearchProposal).count() == 0
        assert session.query(ProposalSection).count() == 0
        assert session.query(ProposalCollaborator).count() == 0
        assert session.query(ProposalVersion).count() == 0
    finally:
        session.close()


def test_proposal_citations_share_bibliographic_metadata_only(client):
    owner_headers, _ = _student(client)
    other_headers, _ = _student(client)
    proposal = _proposal(client, owner_headers)
    proposal_id = proposal["id"]
    section = _section(client, owner_headers, proposal_id, "Related Work")
    entry = _entry(
        client,
        owner_headers,
        notes="Private reading notes that must not leak.",
        review_status="reading",
    ).json()
    foreign_entry = _entry(client, other_headers).json()

    created = client.post(
        f"{PROPOSALS}/{proposal_id}/citations",
        json={"literature_entry_id": entry["id"], "section_id": section["id"]},
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    citation = created.json()
    assert citation["literature_entry_id"] == entry["id"]
    assert citation["section_id"] == section["id"]
    assert citation["title"] == "Attention Is All You Need"

    detail = client.get(f"{PROPOSALS}/{proposal_id}", headers=owner_headers).json()
    serialized = str(detail["citations"])
    assert "Private reading notes" not in serialized
    assert detail["citations"][0]["citation_key"] is None
    assert detail["latest_version"] == 3

    entry_detail = client.get(
        f"{LITERATURE}/{entry['id']}", headers=owner_headers
    ).json()
    assert entry_detail["proposal_citation_count"] == 1

    duplicate = client.post(
        f"{PROPOSALS}/{proposal_id}/citations",
        json={"literature_entry_id": entry["id"]},
        headers=owner_headers,
    )
    assert duplicate.status_code == 409

    foreign = client.post(
        f"{PROPOSALS}/{proposal_id}/citations",
        json={"literature_entry_id": foreign_entry["id"]},
        headers=owner_headers,
    )
    assert foreign.status_code == 404

    other_proposal = _proposal(client, owner_headers, title="Other proposal")
    other_section = _section(
        client, owner_headers, other_proposal["id"], "Other section"
    )
    mismatched = client.post(
        f"{PROPOSALS}/{proposal_id}/citations",
        json={
            "literature_entry_id": entry["id"],
            "section_id": other_section["id"],
        },
        headers=owner_headers,
    )
    assert mismatched.status_code == 404


def test_deleting_a_cited_entry_and_section_updates_the_proposal(client):
    owner_headers, _ = _student(client)
    proposal = _proposal(client, owner_headers)
    proposal_id = proposal["id"]
    section = _section(client, owner_headers, proposal_id, "Discussion")
    entry_id = _entry(client, owner_headers).json()["id"]
    client.post(
        f"{PROPOSALS}/{proposal_id}/citations",
        json={"literature_entry_id": entry_id, "section_id": section["id"]},
        headers=owner_headers,
    )

    removed = client.delete(
        f"{PROPOSALS}/{proposal_id}/sections/{section['id']}",
        headers=owner_headers,
    )
    assert removed.status_code == 200, removed.text
    detail = client.get(f"{PROPOSALS}/{proposal_id}", headers=owner_headers).json()
    assert detail["citations"][0]["section_id"] is None

    assert client.delete(f"{LITERATURE}/{entry_id}", headers=owner_headers).status_code == 200
    detail = client.get(f"{PROPOSALS}/{proposal_id}", headers=owner_headers).json()
    assert detail["citations"] == []


def test_proposal_validation_and_owner_only_metadata(client):
    owner_headers, owner = _student(client)
    proposal = _proposal(client, owner_headers)
    proposal_id = proposal["id"]

    assert (
        client.post(PROPOSALS, json={"title": "   "}, headers=owner_headers).status_code
        == 422
    )
    assert (
        client.post(
            f"{PROPOSALS}/{proposal_id}/sections",
            json={"heading": "   "},
            headers=owner_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{PROPOSALS}/{proposal_id}/collaborators",
            json={"user_id": owner["id"], "role": "editor"},
            headers=owner_headers,
        ).status_code
        == 422
    )

    updated = client.put(
        f"{PROPOSALS}/{proposal_id}",
        json={"title": "Refined Proposal", "status": "submitted"},
        headers=owner_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Refined Proposal"
    assert updated.json()["status"] == "submitted"
    assert updated.json()["latest_version"] == 2
