"""Semantic matching edge-case tests (no embedding model download)."""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

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


class TextVectorModel:
    """Deterministic encoder keyed by the exact text it receives."""

    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []

    def encode(self, texts, normalize_embeddings=True):
        self.calls.append(list(texts))
        return np.asarray(
            [self.vectors[text] for text in texts], dtype=np.float64
        )


def distinct_researchers():
    return [
        make_researcher(
            1,
            research_areas="Machine Learning",
            expertise="Ranking",
            skills="Python",
            projects="Search",
            publications="IR",
        ),
        make_researcher(
            2,
            research_areas="Computer Vision",
            expertise="Segmentation",
            skills="PyTorch",
            projects="Vision",
            publications="CNN",
        ),
        make_researcher(
            3,
            research_areas="Cyber Security",
            expertise="Intrusion Detection",
            skills="Go",
            projects="SIEM",
            publications="IDS",
        ),
    ]


def text_vectors(researchers):
    student_text = semantic_matching.build_student_text(STUDENT)
    units = ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])
    vectors = {student_text: units[0]}

    for index, researcher in enumerate(researchers):
        vectors[semantic_matching.build_researcher_text(researcher)] = units[index]

    return vectors


def test_researcher_embeddings_are_reused_across_identical_calls(monkeypatch):
    researchers = distinct_researchers()
    model = TextVectorModel(text_vectors(researchers))
    patch_model(monkeypatch, model)

    first = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)
    second = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    assert [len(call) for call in model.calls] == [4, 1]
    assert model.calls[1] == [semantic_matching.build_student_text(STUDENT)]
    assert second == first


def test_researcher_embedding_cache_evicts_least_recently_used(monkeypatch):
    monkeypatch.setattr(semantic_matching, "RESEARCHER_EMBEDDING_CACHE_SIZE", 2)

    researchers = distinct_researchers()
    texts = [semantic_matching.build_researcher_text(r) for r in researchers]
    model = TextVectorModel(text_vectors(researchers))
    patch_model(monkeypatch, model)

    first = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)
    second = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)
    third = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    assert [len(call) for call in model.calls] == [4, 2, 2]
    assert texts[0] in model.calls[1]
    assert texts[1] in model.calls[2]
    assert second == first
    assert third == first


def test_switching_embedding_models_invalidates_cached_researcher_vectors(
    monkeypatch,
):
    researchers = distinct_researchers()
    vectors = text_vectors(researchers)
    first_model = TextVectorModel(vectors)
    second_model = TextVectorModel(vectors)

    patch_model(monkeypatch, first_model)
    first = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)
    repeated = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    patch_model(monkeypatch, second_model)
    second = semantic_matching.calculate_semantic_similarity(STUDENT, researchers)

    assert [len(call) for call in first_model.calls] == [4, 1]
    assert [len(call) for call in second_model.calls] == [4]
    assert repeated == first
    assert second == first


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


def test_mean_pool_ignores_padding_and_normalises():
    hidden = np.array(
        [[[3.0, 4.0], [0.0, 5.0], [100.0, 100.0]]], dtype=np.float32
    )
    attention_mask = np.array([[1, 1, 0]])

    pooled = semantic_matching.mean_pool(hidden, attention_mask)

    np.testing.assert_allclose(
        pooled,
        [[0.31622776, 0.9486833]],
        rtol=1e-6,
    )


def test_missing_model_files_raise_semantic_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        semantic_matching, "MODEL_PATH", str(tmp_path / "missing.onnx")
    )
    monkeypatch.setattr(semantic_matching, "_embedder", None)

    with pytest.raises(semantic_matching.SemanticMatchingError):
        semantic_matching.get_model()


def test_concurrent_first_use_builds_a_single_embedder(monkeypatch):
    built = []

    class SlowEmbedder:
        def __init__(self, *args):
            time.sleep(0.05)
            built.append(self)

    monkeypatch.setattr(semantic_matching, "OnnxTextEmbedder", SlowEmbedder)
    monkeypatch.setattr(semantic_matching, "verify_model_files", lambda: None)
    monkeypatch.setattr(semantic_matching, "_embedder", None)

    barrier = threading.Barrier(8)

    def load():
        barrier.wait()
        return semantic_matching.get_model()

    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = [future.result() for future in [pool.submit(load) for _ in range(8)]]

    assert len(built) == 1, f"expected one embedder, built {len(built)}"
    assert len({id(model) for model in loaded}) == 1


def test_installed_model_files_match_the_pinned_hashes():
    model_path = getattr(semantic_matching, "MODEL_PATH")
    tokenizer_path = getattr(semantic_matching, "TOKENIZER_PATH")

    if not (os.path.exists(model_path) and os.path.exists(tokenizer_path)):
        pytest.skip("embedding artifacts are not installed in this checkout")

    semantic_matching._verified_signature = None
    semantic_matching.verify_model_files()


def _point_at(tmp_path, monkeypatch, model_bytes, tokenizer_bytes):
    model = tmp_path / "model.onnx"
    tokenizer = tmp_path / "tokenizer.json"
    model.write_bytes(model_bytes)
    tokenizer.write_bytes(tokenizer_bytes)
    monkeypatch.setattr(semantic_matching, "MODEL_PATH", str(model))
    monkeypatch.setattr(semantic_matching, "TOKENIZER_PATH", str(tokenizer))
    monkeypatch.setattr(semantic_matching, "_verified_signature", None)
    return model, tokenizer


def test_missing_tokenizer_is_rejected(tmp_path, monkeypatch):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"present")
    monkeypatch.setattr(semantic_matching, "MODEL_PATH", str(model))
    monkeypatch.setattr(
        semantic_matching, "TOKENIZER_PATH", str(tmp_path / "missing.json")
    )
    monkeypatch.setattr(semantic_matching, "_verified_signature", None)

    with pytest.raises(semantic_matching.SemanticMatchingError, match="missing"):
        semantic_matching.verify_model_files()


def test_modified_model_files_are_rejected(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch, b"tampered model", b"tampered tokenizer")

    with pytest.raises(
        semantic_matching.SemanticMatchingError, match="integrity check"
    ):
        semantic_matching.verify_model_files()


def test_verification_hashes_once_and_then_uses_the_cache(tmp_path, monkeypatch):
    model, tokenizer = _point_at(tmp_path, monkeypatch, b"model", b"tokenizer")
    real_hash = semantic_matching._file_sha256
    calls = []

    def counting_hash(path):
        calls.append(path)
        return real_hash(path)

    monkeypatch.setattr(semantic_matching, "_file_sha256", counting_hash)
    monkeypatch.setattr(
        semantic_matching,
        "EXPECTED_FILE_SHA256",
        {
            "model.onnx": real_hash(str(model)),
            "tokenizer.json": real_hash(str(tokenizer)),
        },
    )

    semantic_matching.verify_model_files()
    semantic_matching.verify_model_files()

    assert len(calls) == 2


def test_onnx_session_uses_one_intra_op_thread(monkeypatch):
    import onnxruntime
    import tokenizers

    captured = {}

    class FakeOptions:
        intra_op_num_threads = 0

    class FakeSession:
        def __init__(self, path, sess_options=None, providers=None):
            captured["options"] = sess_options

        def get_inputs(self):
            return []

    class FakeTokenizer:
        @classmethod
        def from_file(cls, path):
            return cls()

        def enable_truncation(self, **kwargs):
            pass

        def enable_padding(self, **kwargs):
            pass

    monkeypatch.setattr(onnxruntime, "SessionOptions", FakeOptions)
    monkeypatch.setattr(onnxruntime, "InferenceSession", FakeSession)
    monkeypatch.setattr(tokenizers, "Tokenizer", FakeTokenizer)

    semantic_matching.OnnxTextEmbedder("model.onnx", "tokenizer.json")

    assert captured["options"].intra_op_num_threads == 1
