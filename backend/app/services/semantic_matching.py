from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "all-MiniLM-L6-v2"

model = SentenceTransformer(MODEL_NAME)


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


def calculate_semantic_similarity(student_profile: dict, researchers):
    student_text = build_student_text(student_profile)

    researcher_texts = [
        build_researcher_text(researcher)
        for researcher in researchers
    ]

    if not student_text or not researcher_texts:
        return []

    student_embedding = model.encode(
        [student_text],
        normalize_embeddings=True
    )

    researcher_embeddings = model.encode(
        researcher_texts,
        normalize_embeddings=True
    )

    similarities = cosine_similarity(
        student_embedding,
        researcher_embeddings
    )[0]

    results = []

    for researcher, score in zip(researchers, similarities):
        results.append({
            "researcher_id": researcher.id,
            "name": researcher.name,
            "department": researcher.department,
            "semantic_score": round(float(score), 4)
        })

    results.sort(
        key=lambda x: x["semantic_score"],
        reverse=True
    )

    return results