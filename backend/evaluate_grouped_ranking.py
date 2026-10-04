import pandas as pd
import numpy as np

from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


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

    total_relevant = np.sum(y_true)

    if total_relevant == 0:
        return 0.0

    return np.sum(y_true[order]) / total_relevant


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

    ranked = y_true[order]

    dcg = dcg_at_k(
        ranked,
        k
    )

    ideal = np.sort(
        y_true
    )[::-1]

    idcg = dcg_at_k(
        ideal,
        k
    )

    if idcg == 0:
        return 0.0

    return dcg / idcg


def reciprocal_rank(y_true, scores):
    order = np.argsort(scores)[::-1]

    ranked = y_true[order]

    relevant = np.where(
        ranked == 1
    )[0]

    if len(relevant) == 0:
        return 0.0

    return 1.0 / (relevant[0] + 1)


def main():

    df = pd.read_csv(DATA_FILE)

    X = df[FEATURES]
    y = df["relevance_label"]
    groups = df["student_id"]

    group_kfold = GroupKFold(
        n_splits=5
    )

    all_results = []

    for fold, (train_idx, test_idx) in enumerate(
        group_kfold.split(
            X,
            y,
            groups
        ),
        start=1
    ):

        X_train = X.iloc[train_idx]
        X_test = X.iloc[test_idx]

        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]

        test_df = df.iloc[test_idx].copy()

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

        test_df["score"] = model.predict_proba(
            X_test
        )[:, 1]

        print(
            f"\nFold {fold} "
            f"test students: "
            f"{sorted(test_df['student_id'].unique())}"
        )

        for student_id, group in test_df.groupby(
            "student_id"
        ):

            y_true = group[
                "relevance_label"
            ].values

            scores = group[
                "score"
            ].values

            result = {
                "student_id": student_id,

                "Precision@1":
                    precision_at_k(
                        y_true,
                        scores,
                        1
                    ),

                "Recall@1":
                    recall_at_k(
                        y_true,
                        scores,
                        1
                    ),

                "NDCG@3":
                    ndcg_at_k(
                        y_true,
                        scores,
                        3
                    ),

                "NDCG@5":
                    ndcg_at_k(
                        y_true,
                        scores,
                        5
                    ),

                "MRR":
                    reciprocal_rank(
                        y_true,
                        scores
                    )
            }

            all_results.append(result)

    results = pd.DataFrame(
        all_results
    )

    print("\n" + "=" * 65)
    print("GROUPED STUDENT-LEVEL RANKING EVALUATION")
    print("=" * 65)

    print(
        results.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}"
        )
    )

    print("\n" + "-" * 65)
    print("AVERAGE ACROSS HELD-OUT STUDENTS")
    print("-" * 65)

    for column in results.columns:

        if column == "student_id":
            continue

        print(
            f"{column:<15}"
            f"{results[column].mean():.4f}"
        )


if __name__ == "__main__":
    main()