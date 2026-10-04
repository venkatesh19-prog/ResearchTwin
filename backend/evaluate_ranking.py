import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline


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


def precision_at_k(y_true, scores, k):
    order = np.argsort(scores)[::-1][:k]
    return np.mean(y_true[order])


def recall_at_k(y_true, scores, k):
    order = np.argsort(scores)[::-1][:k]

    relevant_total = np.sum(y_true)

    if relevant_total == 0:
        return 0.0

    return np.sum(y_true[order]) / relevant_total


def dcg_at_k(relevances, k):
    relevances = np.asarray(relevances)[:k]

    if len(relevances) == 0:
        return 0.0

    discounts = np.log2(
        np.arange(2, len(relevances) + 2)
    )

    return np.sum(
        (2 ** relevances - 1) / discounts
    )


def ndcg_at_k(y_true, scores, k):
    order = np.argsort(scores)[::-1]

    ranked_relevances = y_true[order]

    dcg = dcg_at_k(
        ranked_relevances,
        k
    )

    ideal_relevances = np.sort(
        y_true
    )[::-1]

    idcg = dcg_at_k(
        ideal_relevances,
        k
    )

    if idcg == 0:
        return 0.0

    return dcg / idcg


def reciprocal_rank(y_true, scores):
    order = np.argsort(scores)[::-1]

    ranked = y_true[order]

    relevant_positions = np.where(
        ranked == 1
    )[0]

    if len(relevant_positions) == 0:
        return 0.0

    first_position = relevant_positions[0]

    return 1.0 / (first_position + 1)


def main():

    df = pd.read_csv(DATA_FILE)

    X = df[FEATURES]
    y = df["relevance_label"]

    # Train the same Logistic Regression baseline.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )

    model = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),
        (
            "classifier",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42
            )
        )
    ])

    model.fit(
        X_train,
        y_train
    )

    # Score every candidate in the complete dataset.
    df["recommendation_score"] = model.predict_proba(
        X
    )[:, 1]

    print("\n" + "=" * 65)
    print("RESEARCHTWIN RANKING EVALUATION")
    print("=" * 65)

    k_values = [1, 3, 5, 10]

    results = []

    for student_id, group in df.groupby(
        "student_id"
    ):

        y_true = group[
            "relevance_label"
        ].values

        scores = group[
            "recommendation_score"
        ].values

        row = {
            "student_id": student_id
        }

        for k in k_values:

            row[f"Precision@{k}"] = precision_at_k(
                y_true,
                scores,
                k
            )

            row[f"Recall@{k}"] = recall_at_k(
                y_true,
                scores,
                k
            )

            row[f"NDCG@{k}"] = ndcg_at_k(
                y_true,
                scores,
                k
            )

        row["MRR"] = reciprocal_rank(
            y_true,
            scores
        )

        results.append(row)

    results_df = pd.DataFrame(results)

    print("\nPer-student results:")
    print(
        results_df.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}"
        )
    )

    print("\n" + "-" * 65)
    print("AVERAGE RANKING METRICS")
    print("-" * 65)

    metric_columns = [
        column
        for column in results_df.columns
        if column != "student_id"
    ]

    for metric in metric_columns:
        print(
            f"{metric:<15} "
            f"{results_df[metric].mean():.4f}"
        )


if __name__ == "__main__":
    main()