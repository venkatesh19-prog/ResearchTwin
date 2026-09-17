from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import Researcher
from .researcher_intelligence import build_research_profile


def rank_researchers(
    student_profile: str,
    db: Session,
    top_k: int = 5
):
    """
    Rank researchers against a student research profile
    using TF-IDF and cosine similarity.
    """

    researchers = db.query(Researcher).all()

    if not researchers:
        return []

    # Build researcher profiles
    researcher_profiles = [
        build_research_profile(researcher)
        for researcher in researchers
    ]

    # Combine student + researcher text
    all_profiles = [student_profile] + researcher_profiles

    # Convert text into TF-IDF vectors
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english"
    )

    vectors = vectorizer.fit_transform(all_profiles)

    # Student vector
    student_vector = vectors[0]

    # Researcher vectors
    researcher_vectors = vectors[1:]

    # Calculate similarity
    similarities = cosine_similarity(
        student_vector,
        researcher_vectors
    )[0]

    # Create ranked results
    results = []

    for researcher, similarity in zip(
        researchers,
        similarities
    ):
        results.append(
            {
                "researcher_id": researcher.id,
                "name": researcher.name,
                "department": researcher.department,
                "similarity_score": round(
                    float(similarity),
                    4
                )
            }
        )

    # Highest similarity first
    results.sort(
        key=lambda x: x["similarity_score"],
        reverse=True
    )

    return results[:top_k]