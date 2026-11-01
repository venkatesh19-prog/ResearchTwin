"""Semantic matching edge-case tests (no embedding model download)."""

import numpy as np
import pytest
from types import SimpleNamespace

from app.services import semantic_matching


def make_researcher(researcher_id, **fields):
    defaults = {
        "id": researcher_id,
        "name": f"Researcher {researcher_id}",
        "department": "Computer Science and Engineering",
        "research_areas": "Machine Learning",
        "expertise": "Deep Learning",
        "skills": "Python, PyTorch",
        "projects": "Semantic Search",
        "publications": "Transformers for Retrieval",
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


STUDENT = {
    "research_areas": "Machine Learning",
    "expertise": "Deep Learning",
    "skills": "Python",
    "projects": "Search",
    "publications": "Transformers",
}


class FakeModel:
    def __init__(self, vectors):
        self.vectors = np.asarray(vectors, dtype=float)
        self.calls = []

    def encode(self, texts, normalize_embeddings=True):
        self.calls.append(list(texts))
        assert len(texts) == len(self.vectors), (
            f"expected {len(self.vectors)} texts, received {len(texts)}"
        )
        return self.vectors


def patch_model(monkeypatch, model):
    monkeypatch.setattr(semantic_matching, "get_model", lambda: model)
    return model


def test_no_researchers_returns_empty_list_without_loading_model(monkeypatch):
    def fail():
        raise AssertionError("embedding model must not load for zero researchers")

    monkeypatch.setattr(semantic_matching, "get_model", fail)

    assert semantic_matching.calculate_semantic_similarity(STUDENT, []) == []


def test_empty_student_profile_returns_zero_score_for_every_researcher(monkeypatch):
    def fail():
        raise AssertionError("embedding model must not load without student text")

    monkeypatch.setattr(semantic_matching, "get_model", fail)

    researchers = [make_researcher(1), make_researcher(2)]
    empty_profile = {
        "research_areas": "",
        "expertise": "",
        "skills": "",
        "projects": "",
        "publications": "",
    }

    results = semantic_matching.calculate_semantic_similarity(
        empty_profile, researchers
    )

    assert len(results) == len(researchers)
    assert {result["researcher_id"] for result in results} == {1, 2}
    assert all(result["semantic_score"] == 0.0 for result in results)
    assert all(result["semantic_available"] is False for result in results)


def test_each_researcher_receives_exactly_one_result(monkeypatch):
    patch_model(
        monkeypatch,
        FakeModel([
            [1.0, 0.0],   # student
            [1.0, 0.0],   # researcher 1: score 1.0
            [0.0, 1.0],   # researcher 2: score 0.0
        ]),
    )

    researchers = [make_researcher(1), make_researcher(2)]
    results = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    assert len(results) == 2
    assert [result["researcher_id"] for result in results] == [1, 2]
    assert results[0]["semantic_score"] == pytest.approx(1.0)
    assert results[0]["semantic_available"] is True


def test_results_are_sorted_by_descending_score(monkeypatch):
    patch_model(
        monkeypatch,
        FakeModel([
            [1.0, 0.0],            # student
            [0.0, 1.0],            # researcher 1: score 0.0
            [0.6, 0.8],            # researcher 2: score 0.6
        ]),
    )

    researchers = [make_researcher(1), make_researcher(2)]
    results = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    assert [result["researcher_id"] for result in results] == [2, 1]
    assert results[0]["semantic_score"] >= results[1]["semantic_score"]


def test_researcher_without_any_text_gets_documented_zero(monkeypatch):
    model = patch_model(
        monkeypatch,
        FakeModel([
            [1.0, 0.0],   # student
            [0.6, 0.8],   # researcher 1 only; researcher 2 has no text
        ]),
    )

    empty_researcher = make_researcher(
        2,
        research_areas="",
        expertise="",
        skills=None,
        projects="",
        publications=None,
    )
    researchers = [make_researcher(1), empty_researcher]

    results = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)
    by_id = {result["researcher_id"]: result for result in results}

    assert by_id[1]["semantic_score"] == pytest.approx(0.6)
    assert by_id[1]["semantic_available"] is True
    assert by_id[2]["semantic_score"] == 0.0
    assert by_id[2]["semantic_available"] is False

    assert len(model.calls) == 1
    assert len(model.calls[0]) == 2, "empty researcher text must not be encoded"


def test_student_and_researchers_are_encoded_in_a_single_batch(monkeypatch):
    model = patch_model(
        monkeypatch,
        FakeModel([
            [1.0, 0.0],
            [1.0, 0.0],
            [0.6, 0.8],
            [0.0, 1.0],
        ]),
    )

    researchers = [make_researcher(1), make_researcher(2), make_researcher(3)]
    semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    assert len(model.calls) == 1
    assert len(model.calls[0]) == 4
    assert "Machine Learning" in model.calls[0][0]


def test_model_failure_becomes_a_controlled_semantic_error(monkeypatch):
    error_cls = getattr(semantic_matching, "SemanticMatchingError", None)
    assert error_cls is not None, (
        "semantic_matching must define SemanticMatchingError"
    )

    def broken_model():
        raise RuntimeError("model download failed")

    monkeypatch.setattr(semantic_matching, "get_model", broken_model)

    with pytest.raises(error_cls):
        semantic_matching.calculate_semantic_similarity(
            STUDENT, [make_researcher(1)]
        )


def test_encode_failure_becomes_a_controlled_semantic_error(monkeypatch):
    error_cls = getattr(semantic_matching, "SemanticMatchingError", None)
    assert error_cls is not None, (
        "semantic_matching must define SemanticMatchingError"
    )

    class BrokenModel:
        def encode(self, texts, normalize_embeddings=True):
            raise ValueError("tensor shape mismatch")

    monkeypatch.setattr(semantic_matching, "get_model", lambda: BrokenModel())

    with pytest.raises(error_cls):
        semantic_matching.calculate_semantic_similarity(
            STUDENT, [make_researcher(1)]
        )


def test_build_texts_skip_missing_fields():
    researcher = make_researcher(
        9,
        research_areas="",
        expertise=None,
        skills="Python",
        projects=None,
        publications="",
    )

    assert semantic_matching.build_researcher_text(researcher) == "Python"
    assert semantic_matching.build_student_text({"skills": "Python"}) == "Python"
