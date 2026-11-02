import os
import threading

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


class SemanticMatchingError(RuntimeError):
    """Raised when the embedding model cannot be loaded or used."""


def verify_model_files():
    missing = [
        path
        for path in (MODEL_PATH, TOKENIZER_PATH)
        if not os.path.exists(path)
    ]

    if missing:
        raise SemanticMatchingError(
            "Semantic embedding model files are missing: "
            + ", ".join(missing)
            + ". Run python scripts/fetch_embedding_model.py."
        )


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
        self._session = ort.InferenceSession(
            model_path,
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
        embeddings = get_model().encode(
            [student_text] + [text for _, text in encodable],
            normalize_embeddings=True,
        )
    except SemanticMatchingError:
        raise
    except Exception as exc:
        raise SemanticMatchingError(
            f"Semantic similarity computation failed: {exc}"
        ) from exc

    similarities = cosine_similarity(
        embeddings[0:1],
        embeddings[1:],
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
