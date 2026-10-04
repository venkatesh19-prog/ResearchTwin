import os
import joblib
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


DATA_FILE = "data/matching_topk_labeled.csv"
MODEL_DIR = "models"
MODEL_FILE = os.path.join(
    MODEL_DIR,
    "researchtwin_logistic.joblib"
)

FEATURES = [
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
    "department_match",
]


def main():

    print("\n" + "=" * 65)
    print("RESEARCHTWIN - SAVING OPTIMIZED MODEL")
    print("=" * 65)

    df = pd.read_csv(DATA_FILE)

    X = df[FEATURES]
    y = df["relevance_label"]

    model = Pipeline([
        ("scaler", StandardScaler()),
        (
            "classifier",
            LogisticRegression(
                C=0.01,
                class_weight=None,
                solver="liblinear",
                max_iter=2000,
                random_state=42
            )
        )
    ])

    model.fit(X, y)

    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(
        {
            "model": model,
            "features": FEATURES
        },
        MODEL_FILE
    )

    print("\nModel trained successfully.")
    print(f"Model saved to: {MODEL_FILE}")

    print("\nFeatures:")
    for feature in FEATURES:
        print(f" - {feature}")

    print("\n" + "=" * 65)
    print("MODEL EXPORT COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()