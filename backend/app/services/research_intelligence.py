"""Shared research-intelligence pipeline over stored researcher records.

One cached TF-IDF snapshot powers the network graph, topic prediction, trend
analytics and the knowledge graph. Clustering is an explicit batch operation:
it optionally blends the existing ONNX sentence embeddings with TF-IDF and
persists the result so read endpoints never recompute it.

No part of this module reads or writes the seven-feature Logistic Regression
model, its scaler, SHAP explainer or serving artifacts.
"""

import hashlib
import heapq
import re
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from itertools import combinations

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session

from ..models import (
    ResearchClusterAssignment,
    ResearchClusterRun,
    Researcher,
    User,
)
from . import semantic_matching
from .audit import record_event
from .researcher_intelligence import build_research_profile
from .verification import effective_status, latest_by_researcher


TEXT_FIELDS = ("research_areas", "expertise", "skills", "projects", "publications")
NETWORK_METHOD = "tfidf_cosine_v1"
TFIDF_CLUSTER_METHOD = "tfidf_agglomerative_v1"
SEMANTIC_CLUSTER_METHOD = "tfidf_semantic_agglomerative_v1"
TOPIC_METHOD = "tfidf_research_area_label_propagation_v1"
TEXT_WEIGHT = 0.6
SEMANTIC_WEIGHT = 0.4
MAX_TFIDF_FEATURES = 2000
# Network similarity is scored GRAPH_ROW_CHUNK rows at a time so peak memory
# stays at chunk x researchers instead of researchers^2.
GRAPH_ROW_CHUNK = 256
# Above this size the dense precomputed-distance agglomerative clustering and
# its embedding matrices no longer fit a small Render instance comfortably.
MAX_SEMANTIC_CLUSTER_RESEARCHERS = 2000


class ResearchIntelligenceError(RuntimeError):
    """A research-intelligence request cannot be answered honestly."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class ResearchIntelligenceBusy(RuntimeError):
    """Raised when all in-process network analysis slots are occupied."""

    def __init__(self, retry_after: int = 5):
        super().__init__("Research network analysis is at capacity")
        self.retry_after = retry_after


NETWORK_MAX_CONCURRENCY = 2
NETWORK_RETRY_AFTER_SECONDS = 5
_network_slots = threading.BoundedSemaphore(NETWORK_MAX_CONCURRENCY)

_snapshot_lock = threading.Lock()
_snapshot_cache = None
_embedding_lock = threading.Lock()
_embedding_cache = None
_rebuild_lock = threading.Lock()


@contextmanager
def network_slot():
    """Non-blocking process-local guard around the O(n^2) network build."""
    if not _network_slots.acquire(blocking=False):
        raise ResearchIntelligenceBusy(NETWORK_RETRY_AFTER_SECONDS)
    try:
        yield
    finally:
        _network_slots.release()


def _clean_label(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _split_labels(value: str | None, *, keep_commas: bool = False) -> list[str]:
    """Split stored multi-value text, preserving the first display spelling."""
    if not value:
        return []

    separator = r"[;\n]" if keep_commas else r"[,;\n]"
    labels = []
    seen = set()

    for part in re.split(separator, str(value)):
        label = _clean_label(part)
        key = label.lower()
        if key and key not in seen:
            seen.add(key)
            labels.append(label)

    return labels


def _normalized_labels(value: str | None) -> set[str]:
    return {label.lower() for label in _split_labels(value)}


def _entity_id(kind: str, label: str) -> str:
    slug = label.strip().lower()
    if len(slug) > 120:
        digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
        slug = slug[:120] + "#" + digest
    return f"{kind}:{slug}"


def _signature(researchers: list[Researcher]) -> str:
    digest = hashlib.sha256()

    for researcher in researchers:
        digest.update(str(researcher.id).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(researcher.department or "").encode("utf-8"))
        digest.update(b"\0")
        for field in TEXT_FIELDS:
            digest.update(str(getattr(researcher, field) or "").encode("utf-8"))
            digest.update(b"\0")

    return digest.hexdigest()


def build_snapshot(db: Session) -> dict:
    """Return one cached, plain-data snapshot for all read models."""
    global _snapshot_cache

    researchers = db.query(Researcher).order_by(Researcher.id).all()
    signature = _signature(researchers)

    cached = _snapshot_cache
    if cached is not None and cached["signature"] == signature:
        return cached

    records = []
    texts = []

    for researcher in researchers:
        texts.append(build_research_profile(researcher))
        records.append(
            {
                "id": researcher.id,
                "name": researcher.name,
                "department": researcher.department or "",
                "designation": researcher.designation or "",
                "experience": researcher.experience,
                "research_areas": researcher.research_areas or "",
                "expertise": researcher.expertise or "",
                "skills": researcher.skills or "",
                "projects": researcher.projects or "",
                "publications": researcher.publications or "",
            }
        )

    vectorizer = None
    matrix = None

    if any(text.strip() for text in texts):
        candidate = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=MAX_TFIDF_FEATURES,
        )
        try:
            matrix = candidate.fit_transform(texts)
            vectorizer = candidate
        except ValueError:
            # Stop-word-only or otherwise empty vocabulary is "no text signal".
            matrix = None

    snapshot = {
        "signature": signature,
        "researchers": records,
        "texts": texts,
        "vectorizer": vectorizer,
        "matrix": matrix,
    }

    with _snapshot_lock:
        _snapshot_cache = snapshot

    return snapshot


def _latest_run(db: Session) -> ResearchClusterRun | None:
    return (
        db.query(ResearchClusterRun)
        .order_by(ResearchClusterRun.id.desc())
        .first()
    )


def _latest_assignments(db: Session) -> dict[int, tuple[int, str]]:
    run = _latest_run(db)
    if run is None:
        return {}

    rows = (
        db.query(ResearchClusterAssignment)
        .filter(ResearchClusterAssignment.run_id == run.id)
        .all()
    )
    return {
        row.researcher_id: (row.cluster_index, row.cluster_label)
        for row in rows
    }


def _top_graph_edges(
    matrix,
    indices: list[int],
    records: list[dict],
    *,
    min_similarity: float,
    max_edges: int,
) -> tuple[list[dict], bool]:
    """Return the strongest edges without materialising the dense n x n matrix.

    Similarity rows are scored in ``GRAPH_ROW_CHUNK``-sized blocks and only
    ``max_edges`` candidates are retained in a bounded heap. Ordering and the
    ``truncated`` flag match the original dense implementation exactly.
    """
    if matrix is None or len(indices) < 2:
        return [], False

    limit = max(int(max_edges), 0)
    selected = matrix[indices]
    candidate_count = 0
    heap = []

    for start in range(0, len(indices), GRAPH_ROW_CHUNK):
        stop = min(start + GRAPH_ROW_CHUNK, len(indices))
        block = cosine_similarity(matrix[indices[start:stop]], selected)

        for offset in range(stop - start):
            left = start + offset
            upper = block[offset, left + 1:]
            candidates = np.nonzero(
                (upper >= min_similarity) & (upper > 0)
            )[0]
            candidate_count += int(candidates.size)

            if limit == 0:
                continue

            for right in (candidates + left + 1).tolist():
                source = records[indices[left]]["id"]
                target = records[indices[right]]["id"]
                if source > target:
                    source, target = target, source

                # Larger tuples are better: higher similarity, then the lower
                # endpoint ids, mirroring the final ascending sort key.
                key = (round(float(block[offset, right]), 4), -source, -target)
                if len(heap) < limit:
                    heapq.heappush(heap, key)
                elif key > heap[0]:
                    heapq.heapreplace(heap, key)

    truncated = candidate_count > limit
    edges = [
        {
            "source": -key[1],
            "target": -key[2],
            "similarity": key[0],
        }
        for key in heap
    ]
    edges.sort(
        key=lambda edge: (
            -edge["similarity"],
            edge["source"],
            edge["target"],
        )
    )
    return edges, truncated


def network_graph(
    db: Session,
    *,
    min_similarity: float = 0.1,
    max_edges: int = 200,
    department: str | None = None,
    include_isolated: bool = True,
) -> dict:
    """Researcher nodes and TF-IDF cosine edges from the shared snapshot."""
    snapshot = build_snapshot(db)
    records = snapshot["researchers"]

    if department:
        key = department.strip().lower()
        indices = [
            index
            for index, record in enumerate(records)
            if record["department"].strip().lower() == key
        ]
    else:
        indices = list(range(len(records)))

    edges, truncated = _top_graph_edges(
        snapshot["matrix"],
        indices,
        records,
        min_similarity=min_similarity,
        max_edges=max_edges,
    )

    degrees = Counter()
    for edge in edges:
        degrees[edge["source"]] += 1
        degrees[edge["target"]] += 1

    assignments = _latest_assignments(db)
    nodes = []

    for index in indices:
        record = records[index]
        degree = degrees.get(record["id"], 0)
        if not include_isolated and degree == 0:
            continue
        cluster_index, cluster_label = assignments.get(record["id"], (None, None))
        nodes.append(
            {
                "id": record["id"],
                "name": record["name"],
                "department": record["department"],
                "research_areas": _split_labels(record["research_areas"]),
                "degree": degree,
                "cluster_index": cluster_index,
                "cluster_label": cluster_label,
            }
        )

    return {
        "method": NETWORK_METHOD,
        "min_similarity": min_similarity,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "truncated": truncated,
        "nodes": nodes,
        "edges": edges,
    }


def _cluster_label(records: list[dict]) -> str:
    counts = Counter()

    for record in records:
        counts.update(_normalized_labels(record["research_areas"]))

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    return ", ".join(label for label, _ in ranked) if ranked else "unlabeled"


def _semantic_vectors(snapshot: dict) -> np.ndarray:
    """Encode non-empty profiles once per snapshot and cache the vectors."""
    global _embedding_cache

    signature = snapshot["signature"]
    cached = _embedding_cache
    if cached is not None and cached["signature"] == signature:
        return cached["vectors"]

    texts = snapshot["texts"]
    encodable = [
        (index, text)
        for index, text in enumerate(texts)
        if text.strip()
    ]

    if not encodable:
        raise ResearchIntelligenceError(
            "Researcher records contain no text to embed."
        )

    try:
        encoded = semantic_matching.get_model().encode(
            [text for _, text in encodable],
            normalize_embeddings=True,
        )
        encoded = np.asarray(encoded, dtype=np.float32)
    except semantic_matching.SemanticMatchingError as exc:
        raise ResearchIntelligenceError(
            "Semantic clustering is unavailable.",
            status_code=503,
        ) from exc
    except Exception as exc:
        raise ResearchIntelligenceError(
            "Semantic clustering failed.",
            status_code=503,
        ) from exc

    if (
        encoded.ndim != 2
        or len(encoded) != len(encodable)
        or not np.isfinite(encoded).all()
    ):
        raise ResearchIntelligenceError(
            "Semantic clustering returned invalid vectors.",
            status_code=503,
        )

    vectors = np.zeros((len(texts), encoded.shape[1]), dtype=np.float32)
    for row, (index, _) in zip(encoded, encodable):
        vectors[index] = row

    with _embedding_lock:
        _embedding_cache = {"signature": signature, "vectors": vectors}

    return vectors


def _cluster_assignments(records, similarities, min_similarity):
    if len(records) == 1:
        raw_labels = [0]
    else:
        distances = np.clip(1.0 - similarities, 0.0, 2.0)
        np.fill_diagonal(distances, 0.0)
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="average",
            distance_threshold=1.0 - min_similarity,
        )
        raw_labels = model.fit_predict(distances).tolist()

    grouped = defaultdict(list)
    for record, raw_label in zip(records, raw_labels):
        grouped[raw_label].append(record)

    groups = sorted(
        grouped.values(),
        key=lambda members: (-len(members), _cluster_label(members)),
    )

    assignments = []
    for cluster_index, members in enumerate(groups):
        label = _cluster_label(members)
        for record in members:
            assignments.append((record, cluster_index, label))

    return assignments, len(groups)


def rebuild_clusters(
    db: Session,
    *,
    actor: User | None,
    min_similarity: float = 0.18,
    use_semantic: bool = True,
) -> dict:
    """Run one explicit batch pass, rejecting concurrent rebuilds.

    The guard is process-local, so multiple workers can each run one rebuild.
    """
    if not _rebuild_lock.acquire(blocking=False):
        raise ResearchIntelligenceError(
            "A clustering rebuild is already running.",
            status_code=409,
        )

    try:
        return _rebuild_clusters_locked(
            db,
            actor=actor,
            min_similarity=min_similarity,
            use_semantic=use_semantic,
        )
    finally:
        _rebuild_lock.release()


def _rebuild_clusters_locked(
    db: Session,
    *,
    actor: User | None,
    min_similarity: float,
    use_semantic: bool,
) -> dict:
    snapshot = build_snapshot(db)
    records = snapshot["researchers"]

    if not records:
        raise ResearchIntelligenceError(
            "No researchers are available to cluster."
        )
    if snapshot["matrix"] is None:
        raise ResearchIntelligenceError(
            "Researcher records contain no research profile text to cluster."
        )
    if use_semantic and len(records) > MAX_SEMANTIC_CLUSTER_RESEARCHERS:
        raise ResearchIntelligenceError(
            "Semantic clustering supports at most "
            f"{MAX_SEMANTIC_CLUSTER_RESEARCHERS} researchers; "
            "rerun with use_semantic=false."
        )

    text_similarity = cosine_similarity(snapshot["matrix"])
    method = TFIDF_CLUSTER_METHOD

    if use_semantic:
        semantic_similarity = cosine_similarity(_semantic_vectors(snapshot))
        similarity = np.clip(
            TEXT_WEIGHT * text_similarity + SEMANTIC_WEIGHT * semantic_similarity,
            -1.0,
            1.0,
        )
        method = SEMANTIC_CLUSTER_METHOD
    else:
        similarity = text_similarity

    assignments, cluster_count = _cluster_assignments(
        records,
        similarity,
        min_similarity,
    )

    try:
        db.query(ResearchClusterAssignment).delete()
        db.query(ResearchClusterRun).delete()

        run = ResearchClusterRun(
            method=method,
            semantic_used=use_semantic,
            min_similarity=min_similarity,
            researcher_count=len(records),
            cluster_count=cluster_count,
            created_by_user_id=actor.id if actor is not None else None,
            created_at=int(time.time()),
        )
        db.add(run)
        db.flush()

        for record, cluster_index, label in assignments:
            db.add(
                ResearchClusterAssignment(
                    run_id=run.id,
                    researcher_id=record["id"],
                    cluster_index=cluster_index,
                    cluster_label=label,
                )
            )

        record_event(
            db,
            actor=actor,
            action="research_intelligence.clusters_rebuilt",
            target_type="research_cluster_run",
            target_id=run.id,
            detail={
                "method": method,
                "semantic_used": use_semantic,
                "researcher_count": len(records),
                "cluster_count": cluster_count,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return cluster_state(db)


def cluster_state(db: Session) -> dict:
    """Read the latest persisted clustering result without recomputation."""
    run = _latest_run(db)

    scoring = {
        "text_weight": TEXT_WEIGHT,
        "semantic_weight": SEMANTIC_WEIGHT,
    }

    if run is None:
        return {"run": None, "clusters": [], "scoring": scoring}

    rows = (
        db.query(ResearchClusterAssignment, Researcher)
        .join(Researcher, Researcher.id == ResearchClusterAssignment.researcher_id)
        .filter(ResearchClusterAssignment.run_id == run.id)
        .order_by(
            ResearchClusterAssignment.cluster_index,
            Researcher.name,
            Researcher.id,
        )
        .all()
    )

    grouped = defaultdict(list)
    for assignment, researcher in rows:
        grouped[assignment.cluster_index].append((assignment, researcher))

    clusters = []
    for cluster_index in sorted(grouped):
        members = grouped[cluster_index]
        clusters.append(
            {
                "cluster_index": cluster_index,
                "label": members[0][0].cluster_label,
                "researcher_count": len(members),
                "members": [
                    {
                        "id": researcher.id,
                        "name": researcher.name,
                        "department": researcher.department,
                        "research_areas": _split_labels(researcher.research_areas),
                    }
                    for _, researcher in members
                ],
            }
        )

    scoring["method"] = run.method

    return {
        "run": {
            "id": run.id,
            "method": run.method,
            "semantic_used": run.semantic_used,
            "min_similarity": run.min_similarity,
            "researcher_count": len(rows),
            "cluster_count": len(clusters),
            "created_at": run.created_at,
        },
        "clusters": clusters,
        "scoring": scoring,
    }


def predict_topics(db: Session, *, text: str, top_k: int = 5) -> dict:
    """Propagate existing research-area labels from similar researchers."""
    snapshot = build_snapshot(db)
    records = snapshot["researchers"]
    labeled = [
        record
        for record in records
        if _split_labels(record["research_areas"])
    ]

    if not labeled:
        raise ResearchIntelligenceError(
            "No researcher research areas are available for topic prediction."
        )
    if snapshot["vectorizer"] is None or snapshot["matrix"] is None:
        raise ResearchIntelligenceError(
            "Researcher records contain no text for topic prediction."
        )

    query = snapshot["vectorizer"].transform([text])
    scores = cosine_similarity(query, snapshot["matrix"])[0]

    topic_weights = defaultdict(float)
    topic_evidence = defaultdict(list)
    matched = 0

    for record, raw_score in zip(records, scores):
        score = float(raw_score)
        if score <= 0:
            continue

        areas = _split_labels(record["research_areas"])
        if not areas:
            continue

        matched += 1
        for area in areas:
            key = area.lower()
            topic_weights[key] += score
            topic_evidence[key].append((score, record))

    total = sum(topic_weights.values())
    topics = []

    for topic, weight in sorted(
        topic_weights.items(),
        key=lambda item: (-item[1], item[0]),
    )[:top_k]:
        evidence = sorted(
            topic_evidence[topic],
            key=lambda item: (-item[0], item[1]["id"]),
        )[:3]
        topics.append(
            {
                "topic": topic,
                "score": round(weight / total, 4) if total else 0.0,
                "researcher_count": len(topic_evidence[topic]),
                "evidence": [
                    {
                        "researcher_id": record["id"],
                        "name": record["name"],
                        "department": record["department"],
                        "similarity": round(score, 4),
                    }
                    for score, record in evidence
                ],
            }
        )

    return {
        "method": TOPIC_METHOD,
        "labeled_researcher_count": len(labeled),
        "matched_researcher_count": matched,
        "topics": topics,
    }


def trend_summary(db: Session, *, top_k: int = 10) -> dict:
    """Current topic coverage only; no dated history is invented."""
    snapshot = build_snapshot(db)
    records = snapshot["researchers"]
    total = len(records)

    area_counts = Counter()
    department_counts = defaultdict(Counter)
    co_occurrence = Counter()
    researchers_with_areas = 0
    researchers_with_publications = 0
    publication_records = 0

    for record in records:
        areas = sorted(_normalized_labels(record["research_areas"]))
        if areas:
            researchers_with_areas += 1
            area_counts.update(areas)
            department = record["department"].strip() or "Unspecified"
            for area in areas:
                department_counts[area][department] += 1
            for left, right in combinations(areas, 2):
                co_occurrence[(left, right)] += 1

        publications = _split_labels(
            record["publications"],
            keep_commas=True,
        )
        if publications:
            researchers_with_publications += 1
            publication_records += len(publications)

    topics = [
        {
            "topic": area,
            "researcher_count": count,
            "share": round(count / total, 4) if total else None,
            "departments": [
                {"department": department, "researcher_count": department_count}
                for department, department_count in sorted(
                    department_counts[area].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
        }
        for area, count in sorted(
            area_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:top_k]
    ]

    co_occurring = [
        {"topics": [left, right], "researcher_count": count}
        for (left, right), count in sorted(
            co_occurrence.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )[:top_k]
    ]

    return {
        "generated_from": {
            "researcher_count": total,
            "researchers_with_research_areas": researchers_with_areas,
            "researchers_with_publications": researchers_with_publications,
            "publication_record_count": publication_records,
        },
        "topics": topics,
        "co_occurring_topics": co_occurring,
        "temporal": {
            "available": False,
            "reason": (
                "The researcher directory stores publication titles but no "
                "publication dates or dated topic metadata, so no historical "
                "trend series is reported."
            ),
        },
    }


def knowledge_graph(
    db: Session,
    *,
    verified_only: bool = False,
    researcher_limit: int = 200,
) -> dict:
    """Build entities and relations from stored directory records."""
    total = db.query(Researcher).count()
    researchers = (
        db.query(Researcher)
        .order_by(Researcher.id)
        .limit(researcher_limit)
        .all()
    )
    verification = latest_by_researcher(db, [researcher.id for researcher in researchers])

    status_counts = Counter()
    selected = []

    for researcher in researchers:
        status = effective_status(verification.get(researcher.id))
        status_counts[status] += 1
        if verified_only and status != "verified":
            continue
        selected.append((researcher, status))

    nodes = {}
    edges = []
    seen_edges = set()

    def add_entity_node(kind: str, label: str) -> str:
        label = _clean_label(label)
        node_id = _entity_id(kind, label)
        node = nodes.get(node_id)

        if node is None:
            node = {
                "id": node_id,
                "type": kind,
                "label": label,
                "researcher_count": 0,
            }
            nodes[node_id] = node

        node["researcher_count"] += 1
        return node_id

    def add_edge(source: str, target: str, relation: str) -> None:
        key = (source, target, relation)
        if key in seen_edges or target not in nodes:
            return
        seen_edges.add(key)
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
            }
        )

    for researcher, status in selected:
        source = f"researcher:{researcher.id}"
        nodes[source] = {
            "id": source,
            "type": "researcher",
            "label": researcher.name,
            "researcher_id": researcher.id,
            "department": researcher.department or "",
            "research_areas": _split_labels(researcher.research_areas),
            "verified": status == "verified",
            "verification_status": status,
        }

        department = _clean_label(researcher.department)
        if department:
            add_edge(
                source,
                add_entity_node("department", department),
                "member_of_department",
            )

        field_relations = (
            ("research_areas", "has_research_area", "research_area", False),
            ("expertise", "has_expertise", "expertise", False),
            ("skills", "has_skill", "skill", False),
            ("publications", "author_of", "publication", True),
            ("projects", "works_on", "project", True),
        )

        for field, relation, kind, keep_commas in field_relations:
            for label in _split_labels(
                getattr(researcher, field),
                keep_commas=keep_commas,
            ):
                add_edge(
                    source,
                    add_entity_node(kind, label),
                    relation,
                )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "meta": {
            "researcher_count": len(selected),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "verified_only": verified_only,
            "verification_status_counts": dict(sorted(status_counts.items())),
            "researcher_limit": researcher_limit,
            "truncated": total > len(researchers),
        },
    }
