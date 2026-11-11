"""Phase 4 research intelligence: network, clusters, topics, trends, graph."""

import threading
import time

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    ResearchClusterAssignment,
    ResearchClusterRun,
    Researcher,
    ResearcherVerification,
)
from app.services import research_intelligence, semantic_matching
from conftest import register_test_account

NETWORK = "/research-intelligence/network"
CLUSTERS = "/research-intelligence/clusters"
REBUILD = "/research-intelligence/clusters/rebuild"
TOPICS = "/research-intelligence/topics/predict"
TRENDS = "/research-intelligence/trends"
GRAPH = "/research-intelligence/knowledge-graph"

RESEARCH_AREAS = {
    "artificial intelligence",
    "machine learning",
    "cybersecurity",
    "distributed systems",
    "algorithms",
    "optimization",
}


class FakeEmbedder:
    """Semantic vectors aligned to the three seeded researcher profiles."""

    def __init__(self):
        self.calls = []

    def encode(self, texts, normalize_embeddings=True):
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            if "Semantic Search Engine" in text:
                vectors.append([1.0, 0.0])
            elif "Intrusion Detection Platform" in text:
                vectors.append([0.0, 1.0])
            elif "Resource Allocation Optimizer" in text:
                vectors.append([0.9, 0.1])
            else:
                vectors.append([0.2, 0.2])
        return np.asarray(vectors, dtype=np.float32)


@pytest.fixture(autouse=True)
def clean_research_intelligence_tables():
    def cleanup():
        session = SessionLocal()
        try:
            session.query(ResearchClusterAssignment).delete()
            session.query(ResearchClusterRun).delete()
            session.query(ResearcherVerification).delete()
            session.commit()
        finally:
            session.close()
        research_intelligence._snapshot_cache = None
        research_intelligence._embedding_cache = None

    cleanup()
    yield cleanup()


@pytest.fixture()
def student_headers(client):
    headers, _ = register_test_account(client, role="student")
    return headers


@pytest.fixture()
def faculty_headers(client):
    headers, _ = register_test_account(client, role="faculty")
    return headers


def _researcher(db, name):
    return db.query(Researcher).filter_by(name=name).one()


def _rebuild(client, admin_headers, monkeypatch, **body):
    monkeypatch.setattr(semantic_matching, "get_model", lambda: FakeEmbedder())
    return client.post(REBUILD, json=body, headers=admin_headers)


def test_research_intelligence_reads_require_authentication(
    client, seeded_db
):
    for path in (NETWORK, CLUSTERS, TRENDS, GRAPH):
        assert client.get(path).status_code == 401

    assert client.post(TOPICS, json={"text": "machine learning"}).status_code == 401
    assert client.post(REBUILD, json={}).status_code == 401


def test_network_returns_actual_nodes_and_thresholded_edges(
    client, seeded_db, student_headers
):
    response = client.get(
        NETWORK,
        params={"min_similarity": 0.01, "max_edges": 10},
        headers=student_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "tfidf_cosine_v1"
    assert body["node_count"] == 3
    assert {node["name"] for node in body["nodes"]} == {
        "Dr. Ada Lovelace",
        "Dr. Grace Hopper",
        "Dr. Alan Turing",
    }
    node_ids = {node["id"] for node in body["nodes"]}
    assert all(node["degree"] >= 0 for node in body["nodes"])
    assert all(isinstance(node["research_areas"], list) for node in body["nodes"])

    assert body["edges"]
    assert body["edge_count"] == len(body["edges"])
    assert body["edge_count"] <= 10
    for edge in body["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert edge["source"] < edge["target"]
        assert 0.01 <= edge["similarity"] <= 1.0
    assert body["truncated"] is False


def test_network_department_filter_keeps_only_matching_nodes(
    client, seeded_db, student_headers
):
    body = client.get(
        NETWORK,
        params={"department": "computer science and engineering"},
        headers=student_headers,
    ).json()

    assert body["node_count"] == 2
    assert {node["department"] for node in body["nodes"]} == {
        "Computer Science and Engineering"
    }
    node_ids = {node["id"] for node in body["nodes"]}
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids
        for edge in body["edges"]
    )


def test_network_rejects_invalid_threshold(client, seeded_db, student_headers):
    assert (
        client.get(
            NETWORK, params={"min_similarity": 2}, headers=student_headers
        ).status_code
        == 422
    )


def test_clusters_are_empty_before_the_first_batch_run(
    client, seeded_db, student_headers
):
    body = client.get(CLUSTERS, headers=student_headers).json()

    assert body["run"] is None
    assert body["clusters"] == []


def test_cluster_rebuild_requires_admin(client, seeded_db, student_headers, faculty_headers):
    assert client.post(REBUILD, json={}, headers=student_headers).status_code == 403
    assert client.post(REBUILD, json={}, headers=faculty_headers).status_code == 403


def test_cluster_rebuild_persists_deterministic_semantic_clusters(
    client, seeded_db, admin_headers, student_headers, monkeypatch, db
):
    response = _rebuild(
        client,
        admin_headers,
        monkeypatch,
        min_similarity=0.3,
        use_semantic=True,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    run = body["run"]
    assert run is not None
    assert run["semantic_used"] is True
    assert run["method"] == "tfidf_semantic_agglomerative_v1"
    assert run["min_similarity"] == 0.3
    assert run["researcher_count"] == 3
    assert run["cluster_count"] == 2
    assert len(body["clusters"]) == 2

    assignments = {
        member["name"]: cluster["cluster_index"]
        for cluster in body["clusters"]
        for member in cluster["members"]
    }
    assert assignments["Dr. Ada Lovelace"] == assignments["Dr. Alan Turing"]
    assert assignments["Dr. Grace Hopper"] != assignments["Dr. Ada Lovelace"]

    ada_cluster = next(
        cluster
        for cluster in body["clusters"]
        if cluster["label"].startswith("machine learning")
    )
    assert {member["name"] for member in ada_cluster["members"]} == {
        "Dr. Ada Lovelace",
        "Dr. Alan Turing",
    }
    assert "cybersecurity" in next(
        cluster["label"]
        for cluster in body["clusters"]
        if cluster["cluster_index"] == assignments["Dr. Grace Hopper"]
    )

    assert db.query(ResearchClusterRun).count() == 1
    assert db.query(ResearchClusterAssignment).count() == 3

    second = _rebuild(
        client,
        admin_headers,
        monkeypatch,
        min_similarity=0.3,
        use_semantic=True,
    )
    assert second.status_code == 200
    assert db.query(ResearchClusterRun).count() == 1
    assert db.query(ResearchClusterAssignment).count() == 3

    stored = client.get(CLUSTERS, headers=student_headers).json()
    assert stored["run"]["id"] == second.json()["run"]["id"]


def test_cluster_rebuild_can_skip_the_embedding_model(
    client, seeded_db, admin_headers, monkeypatch, db
):
    def fail():
        raise AssertionError("the embedding model must not load")

    monkeypatch.setattr(semantic_matching, "get_model", fail)

    response = client.post(
        REBUILD,
        json={"min_similarity": 0.05, "use_semantic": False},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"]["semantic_used"] is False
    assert body["run"]["method"] == "tfidf_agglomerative_v1"
    assert db.query(ResearchClusterAssignment).count() == 3


def test_cluster_rebuild_rejects_an_empty_directory(
    client, empty_db, admin_headers
):
    response = client.post(REBUILD, json={}, headers=admin_headers)

    assert response.status_code == 400
    assert "no researchers" in response.json()["detail"].lower()


def test_cluster_rebuild_reports_semantic_failure_without_leaking(
    client, seeded_db, admin_headers, monkeypatch, db
):
    def fail():
        raise semantic_matching.SemanticMatchingError("private model path")

    monkeypatch.setattr(semantic_matching, "get_model", fail)

    response = client.post(REBUILD, json={"use_semantic": True}, headers=admin_headers)

    assert response.status_code == 503
    assert "private model path" not in response.text
    assert db.query(ResearchClusterRun).count() == 0


def test_cluster_rebuild_validates_parameters(client, seeded_db, admin_headers):
    assert (
        client.post(
            REBUILD, json={"min_similarity": 0.0}, headers=admin_headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            REBUILD, json={"use_semantic": True, "unknown": 1}, headers=admin_headers
        ).status_code
        == 422
    )


def test_clusters_are_read_from_persistence_without_recomputing(
    client, seeded_db, admin_headers, student_headers, monkeypatch
):
    assert (
        _rebuild(
            client,
            admin_headers,
            monkeypatch,
            min_similarity=0.3,
            use_semantic=True,
        ).status_code
        == 200
    )

    def fail(_db):
        raise AssertionError("persisted clusters must not rebuild the pipeline")

    monkeypatch.setattr(research_intelligence, "build_snapshot", fail)

    body = client.get(CLUSTERS, headers=student_headers).json()
    assert body["run"] is not None
    assert len(body["clusters"]) == 2


def test_batch_clustering_does_not_load_the_seven_feature_model(
    client, seeded_db, admin_headers, monkeypatch
):
    from app.services import recommendation

    def fail():
        raise AssertionError("the seven-feature model must not be used")

    monkeypatch.setattr(recommendation, "load_model", fail)
    response = _rebuild(
        client,
        admin_headers,
        monkeypatch,
        min_similarity=0.3,
        use_semantic=True,
    )

    assert response.status_code == 200


def test_snapshot_is_cached_between_reads(db, seeded_db):
    first = research_intelligence.build_snapshot(db)
    second = research_intelligence.build_snapshot(db)

    assert first is second
    assert len(first["researchers"]) == 3


def test_topic_prediction_scores_only_existing_research_area_labels(
    client, seeded_db, student_headers
):
    response = client.post(
        TOPICS,
        json={
            "text": "deep learning transformers with python and pytorch",
            "top_k": 5,
        },
        headers=student_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "tfidf_research_area_label_propagation_v1"
    assert body["labeled_researcher_count"] == 3
    assert body["matched_researcher_count"] >= 1

    topics = body["topics"]
    assert topics
    assert {topic["topic"] for topic in topics} <= RESEARCH_AREAS
    assert "machine learning" in {topic["topic"] for topic in topics}
    assert all(0.0 < topic["score"] <= 1.0 for topic in topics)
    assert [topic["score"] for topic in topics] == sorted(
        [topic["score"] for topic in topics], reverse=True
    )

    evidence = topics[0]["evidence"]
    assert evidence
    assert all(0.0 < item["similarity"] <= 1.0 for item in evidence)
    assert all(item["researcher_id"] for item in evidence)


def test_topic_prediction_returns_no_topics_without_lexical_support(
    client, seeded_db, student_headers
):
    body = client.post(
        TOPICS,
        json={"text": "medieval poetry manuscript illumination"},
        headers=student_headers,
    ).json()

    assert body["topics"] == []
    assert body["matched_researcher_count"] == 0


def test_topic_prediction_validates_input(client, seeded_db, student_headers):
    assert (
        client.post(TOPICS, json={"text": "   "}, headers=student_headers).status_code
        == 422
    )
    assert (
        client.post(
            TOPICS,
            json={"text": "machine learning", "top_k": 0},
            headers=student_headers,
        ).status_code
        == 422
    )


def test_topic_prediction_requires_labels_in_the_directory(
    client, empty_db, student_headers
):
    response = client.post(
        TOPICS,
        json={"text": "machine learning"},
        headers=student_headers,
    )

    assert response.status_code == 400
    assert "research area" in response.json()["detail"].lower()


def test_trends_use_only_current_researcher_metadata(
    client, seeded_db, student_headers
):
    body = client.get(TRENDS, headers=student_headers).json()

    assert body["generated_from"] == {
        "researcher_count": 3,
        "researchers_with_research_areas": 3,
        "researchers_with_publications": 3,
        "publication_record_count": 3,
    }

    topics = {topic["topic"]: topic for topic in body["topics"]}
    assert set(topics) == RESEARCH_AREAS
    assert topics["machine learning"]["researcher_count"] == 2
    assert topics["machine learning"]["share"] == pytest.approx(2 / 3, abs=1e-4)
    assert {
        row["department"]: row["researcher_count"]
        for row in topics["machine learning"]["departments"]
    } == {"Computer Science and Engineering": 2}

    co_occurring = {
        tuple(sorted(pair["topics"])): pair["researcher_count"]
        for pair in body["co_occurring_topics"]
    }
    assert co_occurring[("artificial intelligence", "machine learning")] == 1
    assert co_occurring[("algorithms", "machine learning")] == 1

    assert body["temporal"]["available"] is False
    assert "no publication dates" in body["temporal"]["reason"].lower()
    assert "yearly" not in body


def test_trends_limit_the_number_of_topics(client, seeded_db, student_headers):
    body = client.get(TRENDS, params={"top_k": 2}, headers=student_headers).json()

    assert len(body["topics"]) == 2
    assert len(body["co_occurring_topics"]) <= 2


def test_knowledge_graph_builds_entities_from_stored_records(
    client, seeded_db, student_headers
):
    body = client.get(GRAPH, headers=student_headers).json()

    nodes = {node["id"]: node for node in body["nodes"]}
    researcher_nodes = [
        node for node in body["nodes"] if node["type"] == "researcher"
    ]
    assert len(researcher_nodes) == 3
    assert {node["label"] for node in researcher_nodes} == {
        "Dr. Ada Lovelace",
        "Dr. Grace Hopper",
        "Dr. Alan Turing",
    }
    assert all(node["verification_status"] == "unverified" for node in researcher_nodes)

    department_nodes = [
        node for node in body["nodes"] if node["type"] == "department"
    ]
    assert {node["label"] for node in department_nodes} == {
        "Computer Science and Engineering",
        "Information Technology",
    }

    relations = {edge["relation"] for edge in body["edges"]}
    assert {
        "member_of_department",
        "has_research_area",
        "has_expertise",
        "has_skill",
        "author_of",
        "works_on",
    } <= relations

    for edge in body["edges"]:
        assert edge["source"] in nodes
        assert edge["target"] in nodes
        assert edge["source"].startswith("researcher:")

    assert body["meta"]["researcher_count"] == 3
    assert body["meta"]["node_count"] == len(body["nodes"])
    assert body["meta"]["edge_count"] == len(body["edges"])
    assert body["meta"]["verified_only"] is False
    assert body["meta"]["verification_status_counts"]["unverified"] == 3

    serialized = str(body)
    assert "evidence" not in serialized.lower()
    assert "review_note" not in serialized
    assert serialized


def test_knowledge_graph_verified_only_uses_the_latest_verification(
    client, seeded_db, student_headers, db
):
    now = int(time.time())
    ada = _researcher(db, "Dr. Ada Lovelace")
    db.add(
        ResearcherVerification(
            researcher_id=ada.id,
            status="verified",
            evidence_reference="private-evidence",
            note="",
            review_note="private-review",
            submitted_by_user_id=None,
            reviewed_by_user_id=None,
            submitted_at=now,
            reviewed_at=now,
            expires_at=None,
            created_at=now,
        )
    )
    db.commit()

    body = client.get(
        GRAPH, params={"verified_only": "true"}, headers=student_headers
    ).json()

    researcher_nodes = [
        node for node in body["nodes"] if node["type"] == "researcher"
    ]
    assert len(researcher_nodes) == 1
    assert researcher_nodes[0]["label"] == "Dr. Ada Lovelace"
    assert researcher_nodes[0]["verification_status"] == "verified"
    assert body["meta"]["verified_only"] is True
    assert body["meta"]["verification_status_counts"]["verified"] == 1
    assert "private-evidence" not in str(body)
    assert "private-review" not in str(body)


def test_cluster_assignment_constraints_and_cascade(db, seeded_db):
    run = ResearchClusterRun(
        method="tfidf_agglomerative_v1",
        semantic_used=False,
        min_similarity=0.1,
        researcher_count=1,
        cluster_count=1,
        created_by_user_id=None,
        created_at=int(time.time()),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    researcher = db.query(Researcher).order_by(Researcher.id).first()
    db.add(
        ResearchClusterAssignment(
            run_id=run.id,
            researcher_id=researcher.id,
            cluster_index=0,
            cluster_label="machine learning",
        )
    )
    db.commit()

    db.add(
        ResearchClusterAssignment(
            run_id=run.id,
            researcher_id=researcher.id,
            cluster_index=0,
            cluster_label="machine learning",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.delete(run)
    db.commit()
    assert db.query(ResearchClusterAssignment).count() == 0


def _graph_fixture():
    matrix = csr_matrix(
        [
            [1.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 1.0],
            [1.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    records = [
        {"id": researcher_id}
        for researcher_id in (10, 3, 7, 1, 5, 2, 9)
    ]
    return matrix, [0, 2, 3, 5, 6], records


def _dense_graph_edges(matrix, indices, records, min_similarity, max_edges):
    """Reference implementation of the pre-STB-20 dense edge builder."""
    edges = []

    if len(indices) > 1:
        similarities = cosine_similarity(matrix[indices])

        for left in range(len(indices)):
            for right in range(left + 1, len(indices)):
                score = float(similarities[left, right])
                if score < min_similarity or score <= 0:
                    continue
                source = records[indices[left]]["id"]
                target = records[indices[right]]["id"]
                edges.append(
                    {
                        "source": min(source, target),
                        "target": max(source, target),
                        "similarity": round(score, 4),
                    }
                )

    edges.sort(
        key=lambda edge: (
            -edge["similarity"],
            edge["source"],
            edge["target"],
        )
    )
    truncated = len(edges) > max_edges
    return edges[:max_edges], truncated


@pytest.mark.parametrize(
    ("min_similarity", "max_edges"),
    [
        (0.0, 100),
        (0.5, 100),
        (0.75, 100),
        (0.1, 3),
        (0.6, 1),
        (1.0, 2),
    ],
)
def test_graph_edges_match_the_dense_reference(min_similarity, max_edges):
    matrix, indices, records = _graph_fixture()

    expected_edges, expected_truncated = _dense_graph_edges(
        matrix, indices, records, min_similarity, max_edges
    )
    edges, truncated = research_intelligence._top_graph_edges(
        matrix,
        indices,
        records,
        min_similarity=min_similarity,
        max_edges=max_edges,
    )

    assert edges == expected_edges
    assert truncated is expected_truncated


def test_graph_edges_are_computed_in_bounded_row_chunks(monkeypatch):
    matrix, indices, records = _graph_fixture()
    real_cosine = research_intelligence.cosine_similarity
    shapes = []

    def spy(left, right):
        shapes.append((left.shape[0], right.shape[0]))
        return real_cosine(left, right)

    monkeypatch.setattr(research_intelligence, "cosine_similarity", spy)
    monkeypatch.setattr(research_intelligence, "GRAPH_ROW_CHUNK", 2)

    research_intelligence._top_graph_edges(
        matrix, indices, records, min_similarity=0.0, max_edges=100
    )

    assert shapes == [(2, 5), (2, 5), (1, 5)]


def test_network_graph_uses_the_bounded_edge_builder(db, seeded_db, monkeypatch):
    calls = []
    real_builder = research_intelligence._top_graph_edges

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(research_intelligence, "_top_graph_edges", spy)

    body = research_intelligence.network_graph(
        db, min_similarity=0.01, max_edges=10
    )

    assert len(calls) == 1
    assert body["edge_count"] == len(body["edges"])


def test_semantic_clustering_rejects_oversized_directories(monkeypatch):
    monkeypatch.setattr(
        research_intelligence, "MAX_SEMANTIC_CLUSTER_RESEARCHERS", 3
    )
    records = [
        {
            "id": index,
            "name": f"Researcher {index}",
            "department": "",
            "research_areas": "Machine Learning",
        }
        for index in range(4)
    ]
    snapshot = {
        "signature": "oversized",
        "researchers": records,
        "texts": ["machine learning"] * 4,
        "matrix": object(),
    }
    monkeypatch.setattr(
        research_intelligence, "build_snapshot", lambda db: snapshot
    )

    with pytest.raises(research_intelligence.ResearchIntelligenceError) as excinfo:
        research_intelligence.rebuild_clusters(None, actor=None, use_semantic=True)

    assert excinfo.value.status_code == 400
    assert "use_semantic=false" in str(excinfo.value)


def test_network_endpoint_is_rate_limited(
    client, seeded_db, student_headers, monkeypatch
):
    monkeypatch.setattr("app.api.research_intelligence.NETWORK_MAX", 1)

    first = client.get(NETWORK, headers=student_headers)
    second = client.get(NETWORK, headers=student_headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0


def test_network_endpoint_reports_busy_when_all_slots_are_held(
    client, seeded_db, student_headers, monkeypatch
):
    monkeypatch.setattr(
        research_intelligence, "_network_slots", threading.BoundedSemaphore(1)
    )

    with research_intelligence.network_slot():
        response = client.get(NETWORK, headers=student_headers)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(
        research_intelligence.NETWORK_RETRY_AFTER_SECONDS
    )
    assert "busy" in response.json()["detail"].lower()
