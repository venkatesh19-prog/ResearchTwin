from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import Researcher
from ..services.researcher_intelligence import (
    build_structured_profile
)


# Initial experimental weights
WEIGHTS = {
    "research_areas": 0.30,
    "expertise": 0.25,
    "skills": 0.20,
    "projects": 0.15,
    "publications": 0.10,
}


def calculate_text_similarity(
    student_text: str,
    researcher_texts: list[str]
):
    """
    Calculate TF-IDF cosine similarity between
    one student text and multiple researcher texts.
    """

    documents = [student_text] + researcher_texts

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2)
    )

    matrix = vectorizer.fit_transform(documents)

    student_vector = matrix[0]
    researcher_vectors = matrix[1:]

    scores = cosine_similarity(
        student_vector,
        researcher_vectors
    )[0]

    return scores


def calculate_weighted_similarity(
    student_profile: dict,
    researcher: Researcher
):
    """
    Calculate weighted similarity between a student
    profile and one researcher.
    """

    researcher_profile = build_structured_profile(
        researcher
    )

    component_scores = {}

    for field, weight in WEIGHTS.items():

        student_text = student_profile.get(
            field,
            ""
        )

        researcher_text = researcher_profile.get(
            field,
            ""
        )

        if not student_text or not researcher_text:
            score = 0.0

        else:
            score = calculate_text_similarity(
                student_text,
                [researcher_text]
            )[0]

        component_scores[field] = float(score)

    final_score = sum(
        component_scores[field] * WEIGHTS[field]
        for field in WEIGHTS
    )

    return {
        "researcher_id": researcher.id,
        "name": researcher.name,
        "department": researcher.department,
        "component_scores": {
            field: round(score, 4)
            for field, score in component_scores.items()
        },
        "final_score": round(
            final_score,
            4
        )
    }


def rank_researchers_weighted(
    student_profile: dict,
    researchers: list[Researcher],
    top_k: int = 5
):
    """
    Rank researchers using weighted similarity.
    """

    results = []

    for researcher in researchers:

        result = calculate_weighted_similarity(
            student_profile,
            researcher
        )

        results.append(result)

    results.sort(
        key=lambda x: x["final_score"],
        reverse=True
    )

    return results[:top_k]