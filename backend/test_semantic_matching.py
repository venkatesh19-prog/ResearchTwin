from app.database import SessionLocal
from app.models import Researcher
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

    results = calculate_semantic_similarity(
        student_profile,
        researchers
    )

    print("\n===== SEMANTIC RESEARCHER MATCHING =====\n")

    for index, result in enumerate(results[:10], start=1):
        print(
            f"{index}. {result['name']} | "
            f"{result['department']} | "
            f"Score: {result['semantic_score']}"
        )

finally:
    db.close()