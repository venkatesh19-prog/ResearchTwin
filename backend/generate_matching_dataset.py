import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.database import SessionLocal
from app.models import Researcher
from app.services.semantic_matching import model


STUDENT_FILE = Path("data/students.csv")
OUTPUT_FILE = Path("data/matching_features.csv")


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def combined_student_text(row):
    return " ".join([
        clean(row["research_areas"]),
        clean(row["expertise"]),
        clean(row["skills"]),
        clean(row["projects"]),
        clean(row["publications"]),
    ])


def combined_researcher_text(researcher):
    return " ".join([
        clean(researcher.research_areas),
        clean(researcher.expertise),
        clean(researcher.skills),
        clean(researcher.projects),
        clean(researcher.publications),
    ])


def text_similarity(student_text, researcher_text):
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2)
    )

    matrix = vectorizer.fit_transform([
        student_text,
        researcher_text
    ])

    return float(
        cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
    )


def token_set(text):
    return {
        token.strip().lower()
        for token in text.replace(";", ",").split(",")
        if token.strip()
    }


def skill_overlap(student_skills, researcher_skills):
    student = token_set(student_skills)
    researcher = token_set(researcher_skills)

    if not researcher:
        return 0.0

    return len(student & researcher) / len(researcher)


def main():

    students = pd.read_csv(STUDENT_FILE)

    db = SessionLocal()

    try:
        researchers = db.query(Researcher).all()

        if not researchers:
            raise RuntimeError("No researchers found in database.")

        print(f"Students: {len(students)}")
        print(f"Researchers: {len(researchers)}")
        print(f"Expected pairs: {len(students) * len(researchers)}")

        # -----------------------------------------
        # Prepare semantic embeddings
        # -----------------------------------------

        student_texts = [
            combined_student_text(row)
            for _, row in students.iterrows()
        ]

        researcher_texts = [
            combined_researcher_text(researcher)
            for researcher in researchers
        ]

        student_embeddings = model.encode(
            student_texts,
            normalize_embeddings=True
        )

        researcher_embeddings = model.encode(
            researcher_texts,
            normalize_embeddings=True
        )

        semantic_matrix = cosine_similarity(
            student_embeddings,
            researcher_embeddings
        )

        # -----------------------------------------
        # Generate feature rows
        # -----------------------------------------

        rows = []

        for student_index, (_, student) in enumerate(
            students.iterrows()
        ):

            student_full_text = student_texts[student_index]

            for researcher_index, researcher in enumerate(
                researchers
            ):

                researcher_full_text = researcher_texts[
                    researcher_index
                ]

                row = {
                    "student_id": student["student_id"],
                    "researcher_id": researcher.id,

                    "tfidf_similarity":
                        text_similarity(
                            student_full_text,
                            researcher_full_text
                        ),

                    "semantic_similarity":
                        float(
                            semantic_matrix[
                                student_index,
                                researcher_index
                            ]
                        ),

                    "research_area_similarity":
                        text_similarity(
                            clean(student["research_areas"]),
                            clean(researcher.research_areas)
                        ),

                    "expertise_similarity":
                        text_similarity(
                            clean(student["expertise"]),
                            clean(researcher.expertise)
                        ),

                    "skill_overlap":
                        skill_overlap(
                            student["skills"],
                            researcher.skills
                        ),

                    "project_similarity":
                        text_similarity(
                            clean(student["projects"]),
                            clean(researcher.projects)
                        ),

                    "publication_similarity":
                        text_similarity(
                            clean(student["publications"]),
                            clean(researcher.publications)
                        ),

                    "department_match":
                        int(
                            "computer science"
                            in clean(researcher.department).lower()
                        ),

                    # Label intentionally NOT generated here.
                    # It must come from independent relevance annotation.
                }

                rows.append(row)

        feature_df = pd.DataFrame(rows)

        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        feature_df.to_csv(
            OUTPUT_FILE,
            index=False
        )

        print("\nFeature dataset created successfully.")
        print(f"Rows: {len(feature_df)}")
        print(f"Columns: {len(feature_df.columns)}")
        print(f"Saved: {OUTPUT_FILE}")

        print("\nFeatures:")
        for column in feature_df.columns:
            print(f" - {column}")

        print("\nFirst 5 rows:")
        print(feature_df.head().to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()