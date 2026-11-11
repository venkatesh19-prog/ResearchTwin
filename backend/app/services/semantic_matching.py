import hashlib
import os
import threading
from collections import OrderedDict

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "models",
        "all-MiniLM-L6-v2-onnx",
    )
)
MODEL_PATH = os.path.join(MODEL_DIR, "model.onnx")
TOKENIZER_PATH = os.path.join(MODEL_DIR, "tokenizer.json")

MAX_SEQUENCE_LENGTH = 256
EMBED_BATCH_SIZE = 8
ONNX_INTRA_OP_THREADS = 1
# Researcher vectors are reused across requests; 2048 x 384 float32 rows is
# roughly 3 MB. Entries are scoped to the embedder that produced them.
RESEARCHER_EMBEDDING_CACHE_SIZE = 2048

_researcher_embedding_cache = OrderedDict()
_researcher_embedding_cache_owner = None
_researcher_embedding_cache_lock = threading.Lock()

# Pinned by scripts/fetch_embedding_model.py from the recorded Hugging Face
# revision. Readiness re-hashes the installed files against these values.
EXPECTED_FILE_SHA256 = {
    "model.onnx": "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",
    "tokenizer.json": "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
}

_verification_lock = threading.Lock()
_verified_signature = None


class SemanticMatchingError(RuntimeError):
    """Raised when the embedding model cannot be loaded or used."""


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verification_signature():
    return tuple(
        (path, os.stat(path).st_size, os.stat(path).st_mtime_ns)
        for path in (MODEL_PATH, TOKENIZER_PATH)
    )


def verify_model_files():
    global _verified_signature

    files = {"model.onnx": MODEL_PATH, "tokenizer.json": TOKENIZER_PATH}
    missing = [path for path in files.values() if not os.path.exists(path)]

    if missing:
        raise SemanticMatchingError(
            "Semantic embedding model files are missing: "
            + ", ".join(missing)
            + ". Run python scripts/fetch_embedding_model.py."
        )

    try:
        signature = _verification_signature()
    except OSError as exc:
        raise SemanticMatchingError(
            f"Could not inspect the semantic embedding model files: {exc}"
        ) from exc

    if signature == _verified_signature:
        return

    with _verification_lock:
        if signature == _verified_signature:
            return

        for name, path in files.items():
            try:
                actual = _file_sha256(path)
            except OSError as exc:
                raise SemanticMatchingError(
                    f"Could not read the semantic embedding file '{name}': {exc}"
                ) from exc
            if actual != EXPECTED_FILE_SHA256[name]:
                raise SemanticMatchingError(
                    f"Semantic embedding file '{name}' failed its SHA-256 "
                    "integrity check"
                )

        _verified_signature = signature


class OnnxTextEmbedder:
    """all-MiniLM-L6-v2 mean-pooled sentence embeddings via ONNX Runtime.

    Importing torch/sentence-transformers costs over 400 MB of RSS; the ONNX
    graph produces the same vectors within float32 rounding at a fraction of
    that footprint.
    """

    def __init__(self, model_path: str, tokenizer_path: str):
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise SemanticMatchingError(
                f"Could not import the ONNX embedding runtime: {exc}"
            ) from exc

        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_truncation(max_length=MAX_SEQUENCE_LENGTH)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = ONNX_INTRA_OP_THREADS
        self._session = ort.InferenceSession(
            model_path,
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {
            item.name for item in self._session.get_inputs()
        }

    def encode(self, texts, normalize_embeddings=True):
        batch = list(texts)
        outputs = []

        for start in range(0, len(batch), EMBED_BATCH_SIZE):
            outputs.append(
                self._encode_batch(
                    batch[start:start + EMBED_BATCH_SIZE],
                    normalize_embeddings,
                )
            )

        return np.vstack(outputs)

    def _encode_batch(self, texts, normalize_embeddings):
        encodings = self._tokenizer.encode_batch(texts)
        attention_mask = np.array(
            [encoding.attention_mask for encoding in encodings],
            dtype=np.int64,
        )
        inputs = {
            "input_ids": np.array(
                [encoding.ids for encoding in encodings],
                dtype=np.int64,
            ),
            "attention_mask": attention_mask,
        }

        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = np.array(
                [encoding.type_ids for encoding in encodings],
                dtype=np.int64,
            )

        hidden = self._session.run(None, inputs)[0]

        return mean_pool(hidden, attention_mask, normalize_embeddings)


def mean_pool(hidden, attention_mask, normalize=True):
    """Mean-pool token states, ignoring padding, then L2-normalise."""

    weights = attention_mask[..., None].astype(np.float32)
    pooled = (hidden * weights).sum(axis=1) / np.clip(
        weights.sum(axis=1),
        1e-9,
        None,
    )

    if normalize:
        pooled = pooled / np.clip(
            np.linalg.norm(pooled, axis=1, keepdims=True),
            1e-12,
            None,
        )

    return pooled.astype(np.float32)


_embedder = None
_embedder_lock = threading.Lock()


def get_model():
    global _embedder

    if _embedder is not None:
        return _embedder

    with _embedder_lock:

        if _embedder is not None:
            return _embedder

        verify_model_files()

        try:
            _embedder = OnnxTextEmbedder(MODEL_PATH, TOKENIZER_PATH)
        except SemanticMatchingError:
            raise
        except Exception as exc:
            raise SemanticMatchingError(
                f"Could not load the semantic embedding model "
                f"'{MODEL_NAME}': {exc}"
            ) from exc

    return _embedder


def build_student_text(student_profile: dict) -> str:
    fields = [
        student_profile.get("research_areas", ""),
        student_profile.get("expertise", ""),
        student_profile.get("skills", ""),
        student_profile.get("projects", ""),
        student_profile.get("publications", ""),
    ]

    return " ".join(
        str(field).strip()
        for field in fields
        if field
    )


def build_researcher_text(researcher) -> str:
    fields = [
        researcher.research_areas,
        researcher.expertise,
        researcher.skills,
        researcher.projects,
        researcher.publications,
    ]

    return " ".join(
        str(field).strip()
        for field in fields
        if field
    )


def _unavailable(researcher) -> dict:
    return {
        "researcher_id": researcher.id,
        "name": researcher.name,
        "department": researcher.department,
        "semantic_score": 0.0,
        "semantic_available": False,
    }


def reset_researcher_embedding_cache():
    global _researcher_embedding_cache_owner

    with _researcher_embedding_cache_lock:
        _researcher_embedding_cache.clear()
        _researcher_embedding_cache_owner = None


def _checked_embeddings(encoded, expected_rows):
    encoded = np.asarray(encoded)

    if encoded.ndim != 2 or len(encoded) != expected_rows:
        raise SemanticMatchingError(
            "Semantic similarity computation returned an unexpected "
            "number of vectors."
        )

    return encoded


def _encode_student_and_researchers(model, student_text, researcher_entries):
    """Encode the student plus only the researchers missing from cache.

    ``researcher_entries`` pairs one cache key per researcher with its profile
    text. The first call still sends the student and every researcher in one
    batch, and duplicate texts keep one row per researcher. The student is
    re-encoded every call so a changed profile never reuses a stale vector.
    """
    global _researcher_embedding_cache_owner

    texts = [text for _, text in researcher_entries]
    limit = max(int(RESEARCHER_EMBEDDING_CACHE_SIZE), 0)

    with _researcher_embedding_cache_lock:
        if _researcher_embedding_cache_owner is not model:
            _researcher_embedding_cache.clear()
            _researcher_embedding_cache_owner = model

        if limit == 0:
            encoded = _checked_embeddings(
                model.encode(
                    [student_text] + texts,
                    normalize_embeddings=True,
                ),
                1 + len(texts),
            )
            return encoded[0:1], encoded[1:]

        cached = {}
        missing = []

        for entry in researcher_entries:
            key = entry[0]
            if key not in _researcher_embedding_cache:
                missing.append(entry)
            elif key not in cached:
                _researcher_embedding_cache.move_to_end(key)
                cached[key] = _researcher_embedding_cache[key]

        if missing:
            encoded = _checked_embeddings(
                model.encode(
                    [student_text] + [text for _, text in missing],
                    normalize_embeddings=True,
                ),
                1 + len(missing),
            )
            student_embedding = encoded[0:1]
            fresh = []

            for (key, _), row in zip(missing, encoded[1:]):
                # Copy rows so cached entries cannot retain the whole encoded
                # batch through a base-array view.
                value = np.array(row, copy=True)
                _researcher_embedding_cache[key] = value
                fresh.append((key, value))
            while len(_researcher_embedding_cache) > limit:
                _researcher_embedding_cache.popitem(last=False)

            for key, value in fresh:
                cached[key] = value
        else:
            encoded = _checked_embeddings(
                model.encode([student_text], normalize_embeddings=True),
                1,
            )
            student_embedding = encoded[0:1]

    return student_embedding, [
        cached[key] for key, _ in researcher_entries
    ]


def calculate_semantic_similarity(student_profile: dict, researchers):
    """Score every researcher against the student profile.

    Exactly one result is returned per researcher, keyed by researcher id.

    Fallback contract: when the student profile contains no text, every
    candidate receives ``semantic_score`` 0.0 with
    ``semantic_available: False``. The same applies to a researcher whose
    own profile is empty. Callers must treat ``semantic_available: False``
    as "no signal", never as evidence of dissimilarity.

    Model load/encode failures raise :class:`SemanticMatchingError` so the
    caller can fail the request instead of silently scoring everyone 0.0.
    """

    researchers = list(researchers)

    if not researchers:
        return []

    student_text = build_student_text(student_profile)
    researcher_texts = [
        build_researcher_text(researcher)
        for researcher in researchers
    ]

    if not student_text:
        return [_unavailable(researcher) for researcher in researchers]

    encodable = [
        (index, text)
        for index, text in enumerate(researcher_texts)
        if text
    ]

    if not encodable:
        return [_unavailable(researcher) for researcher in researchers]

    try:
        student_embedding, researcher_embeddings = (
            _encode_student_and_researchers(
                get_model(),
                student_text,
                [
                    (researchers[index].id, text)
                    for index, text in encodable
                ],
            )
        )
    except SemanticMatchingError:
        raise
    except Exception as exc:
        raise SemanticMatchingError(
            f"Semantic similarity computation failed: {exc}"
        ) from exc

    similarities = cosine_similarity(
        student_embedding,
        np.vstack(researcher_embeddings),
    )[0]

    scores_by_index = {
        index: float(score)
        for (index, _), score in zip(encodable, similarities)
    }

    results = []

    for index, researcher in enumerate(researchers):
        score = scores_by_index.get(index)

        if score is None:
            results.append(_unavailable(researcher))
            continue

        results.append({
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department,
            "semantic_score": round(score, 4),
            "semantic_available": True,
        })

    results.sort(
        key=lambda result: result["semantic_score"],
        reverse=True,
    )

    return results
