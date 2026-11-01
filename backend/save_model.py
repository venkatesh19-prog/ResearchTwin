import hashlib
from pathlib import Path

import joblib
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


BACKEND_DIR = Path(__file__).resolve().parent
DATA_FILE = BACKEND_DIR / "data" / "matching_topk_labeled.csv"
MODEL_DIR = BACKEND_DIR / "models"
MODEL_FILE = MODEL_DIR / "researchtwin_logistic_v2_7features.joblib"

FEATURES = [
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
]


def main():

    print("\n" + "=" * 65)
    print("RESEARCHTWIN - SAVING OPTIMIZED MODEL")
    print("=" * 65)

    if MODEL_FILE.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing model artifact: {MODEL_FILE.name}"
        )

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

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    bundle = {
        "model": model,
        "features": FEATURES,
        "model_version": "researchtwin-logistic-v2-7features",
        "training_data_sha256": hashlib.sha256(DATA_FILE.read_bytes()).hexdigest(),
    }
    with MODEL_FILE.open("xb") as output:
        joblib.dump(bundle, output)

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
