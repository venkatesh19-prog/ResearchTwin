from app.database import SessionLocal
from app.models import Researcher

from app.services.researcher_similarity import rank_researchers_weighted
from app.services.semantic_matching import calculate_semantic_similarity


student_profile = {
    "research_areas": "Artificial Intelligence, Machine Learning, Natural Language Processing",
    "expertise": "Deep Learning, Large Language Models, NLP",
    "skills": "Python, PyTorch, Transformers, Machine Learning",
    "projects": "AI chatbot using large language models and semantic search",
    "publications": "Natural Language Processing and Transformer-based models"
}


db = SessionLocal()

try:
    researchers = db.query(Researcher).all()

    # -----------------------------
    # TF-IDF BASELINE
    # -----------------------------
    tfidf_results = rank_researchers_weighted(
        student_profile,
        researchers,
        top_k=len(researchers)
    )

    # -----------------------------
    # SEMANTIC MODEL
    # -----------------------------
    semantic_results = calculate_semantic_similarity(
        student_profile,
        researchers
    )

    # Create lookup tables
    tfidf_lookup = {
        result["researcher_id"]: result["final_score"]
        for result in tfidf_results
    }

    semantic_lookup = {
        result["researcher_id"]: result["semantic_score"]
        for result in semantic_results
    }

    researcher_lookup = {
        researcher.id: researcher
        for researcher in researchers
    }

    # -----------------------------
    # COMPARISON
    # -----------------------------
    comparison = []

    for researcher_id in researcher_lookup:

        tfidf_score = tfidf_lookup.get(researcher_id, 0.0)
        semantic_score = semantic_lookup.get(researcher_id, 0.0)

        comparison.append({
            "id": researcher_id,
            "name": researcher_lookup[researcher_id].name,
            "tfidf": tfidf_score,
            "semantic": semantic_score,
            "difference": semantic_score - tfidf_score
        })

    # Sort by semantic score
    comparison.sort(
        key=lambda x: x["semantic"],
        reverse=True
    )

    print("\n" + "=" * 80)
    print("RESEARCHTWIN MODEL COMPARISON")
    print("=" * 80)

    print(
        f"{'Rank':<6}"
        f"{'Researcher':<25}"
        f"{'TF-IDF':<12}"
        f"{'Semantic':<12}"
        f"{'Difference':<12}"
    )

    print("-" * 80)

    for rank, result in enumerate(comparison, start=1):

        print(
            f"{rank:<6}"
            f"{result['name'][:24]:<25}"
            f"{result['tfidf']:<12.4f}"
            f"{result['semantic']:<12.4f}"
            f"{result['difference']:<12.4f}"
        )

finally:
    db.close()