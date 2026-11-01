from functools import lru_cache

from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "all-MiniLM-L6-v2"


class SemanticMatchingError(RuntimeError):
    """Raised when the embedding model cannot be loaded or used."""


@lru_cache(maxsize=1)
def get_model():
    # Imported lazily: sentence-transformers pulls in torch, which costs
    # hundreds of MB of RSS and is useless for routes that never embed text.
    from sentence_transformers import SentenceTransformer

    try:
        return SentenceTransformer(MODEL_NAME)
    except Exception as exc:
        raise SemanticMatchingError(
            f"Could not load the semantic embedding model "
            f"'{MODEL_NAME}': {exc}"
        ) from exc


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
