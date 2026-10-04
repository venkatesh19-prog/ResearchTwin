import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report
)


DATA_FILE = "data/matching_topk_labeled.csv"


FEATURES = [
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
    "department_match"
]


def main():

    df = pd.read_csv(DATA_FILE)

    X = df[FEATURES]
    y = df["relevance_label"]

    print("Dataset shape:", df.shape)
    print("Features:", len(FEATURES))
    print("Positive samples:", int(y.sum()))
    print("Negative samples:", int((y == 0).sum()))

    # -----------------------------------------
    # Train / Test Split
    # -----------------------------------------

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )

    print("\nTraining samples:", len(X_train))
    print("Testing samples:", len(X_test))

    # -----------------------------------------
    # Logistic Regression Pipeline
    # -----------------------------------------

    model = Pipeline([
        ("scaler", StandardScaler()),
        (
            "classifier",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42
            )
        )
    ])

    model.fit(X_train, y_train)

    # -----------------------------------------
    # Predictions
    # -----------------------------------------

    predictions = model.predict(X_test)

    probabilities = model.predict_proba(X_test)[:, 1]

    # -----------------------------------------
    # Evaluation
    # -----------------------------------------

    accuracy = accuracy_score(
        y_test,
        predictions
    )

    precision = precision_score(
        y_test,
        predictions,
        zero_division=0
    )

    recall = recall_score(
        y_test,
        predictions,
        zero_division=0
    )

    f1 = f1_score(
        y_test,
        predictions,
        zero_division=0
    )

    auc = roc_auc_score(
        y_test,
        probabilities
    )

    print("\n" + "=" * 60)
    print("LOGISTIC REGRESSION RESULTS")
    print("=" * 60)

    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")
    print(f"ROC-AUC  : {auc:.4f}")

    print("\nClassification Report:")
    print(
        classification_report(
            y_test,
            predictions,
            zero_division=0
        )
    )


if __name__ == "__main__":
    main()