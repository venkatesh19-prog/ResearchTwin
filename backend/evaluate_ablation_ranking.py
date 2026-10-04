import pandas as pd
import numpy as np

from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


DATA_FILE = "data/matching_topk_labeled.csv"

EXPERIMENTS = {

    "TF-IDF Only": [
        "tfidf_similarity"
    ],

    "Semantic Only": [
        "semantic_similarity"
    ],

    "Structured Features": [
        "research_area_similarity",
        "expertise_similarity",
        "skill_overlap",
        "project_similarity",
        "publication_similarity",
        "department_match",
    ],

    "Hybrid Model": [
        "tfidf_similarity",
        "semantic_similarity",
        "research_area_similarity",
        "expertise_similarity",
        "skill_overlap",
        "project_similarity",
        "publication_similarity",
        "department_match",
    ],
}


# =========================================================
# RANKING METRICS
# =========================================================

def precision_at_k(relevant, k):

    top_k = relevant[:k]

    if k == 0:
        return 0.0

    return sum(top_k) / k


def recall_at_k(relevant, k):

    total_relevant = sum(relevant)

    if total_relevant == 0:
        return 0.0

    return sum(relevant[:k]) / total_relevant


def dcg_at_k(relevant, k):

    relevant = relevant[:k]

    score = 0.0

    for rank, relevance in enumerate(
        relevant,
        start=1
    ):

        score += (
            (2 ** relevance - 1)
            / np.log2(rank + 1)
        )

    return score


def ndcg_at_k(relevant, k):

    actual = dcg_at_k(
        relevant,
        k
    )

    ideal = dcg_at_k(
        sorted(
            relevant,
            reverse=True
        ),
        k
    )

    if ideal == 0:
        return 0.0

    return actual / ideal


def reciprocal_rank(relevant):

    for rank, relevance in enumerate(
        relevant,
        start=1
    ):

        if relevance == 1:
            return 1.0 / rank

    return 0.0


# =========================================================
# GROUPED RANKING EVALUATION
# =========================================================

def evaluate_model(
    df,
    features
):

    groups = df["student_id"]

    group_kfold = GroupKFold(
        n_splits=5
    )

    metrics = []

    for train_idx, test_idx in group_kfold.split(
        df,
        df["relevance_label"],
        groups
    ):

        train_df = df.iloc[train_idx]
        test_df = df.iloc[test_idx]

        X_train = train_df[features]
        y_train = train_df[
            "relevance_label"
        ]

        model = Pipeline([

            (
                "scaler",
                StandardScaler()
            ),

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

        model.fit(
            X_train,
            y_train
        )

        # ---------------------------------------------
        # Evaluate separately for each unseen student
        # ---------------------------------------------

        for student_id in test_df[
            "student_id"
        ].unique():

            student_df = test_df[
                test_df["student_id"]
                == student_id
            ].copy()

            X_student = student_df[
                features
            ]

            probabilities = model.predict_proba(
                X_student
            )[:, 1]

            student_df[
                "predicted_score"
            ] = probabilities

            student_df = student_df.sort_values(
                "predicted_score",
                ascending=False
            )

            relevance = student_df[
                "relevance_label"
            ].tolist()

            metrics.append({

                "student_id":
                    student_id,

                "precision@1":
                    precision_at_k(
                        relevance,
                        1
                    ),

                "recall@1":
                    recall_at_k(
                        relevance,
                        1
                    ),

                "precision@3":
                    precision_at_k(
                        relevance,
                        3
                    ),

                "recall@3":
                    recall_at_k(
                        relevance,
                        3
                    ),

                "ndcg@3":
                    ndcg_at_k(
                        relevance,
                        3
                    ),

                "ndcg@5":
                    ndcg_at_k(
                        relevance,
                        5
                    ),

                "mrr":
                    reciprocal_rank(
                        relevance
                    )
            })

    metrics_df = pd.DataFrame(
        metrics
    )

    return metrics_df


# =========================================================
# MAIN
# =========================================================

def main():

    print("\n" + "=" * 80)
    print("RESEARCHTWIN - GROUPED RANKING ABLATION")
    print("=" * 80)

    df = pd.read_csv(
        DATA_FILE
    )

    results = []

    for model_name, features in EXPERIMENTS.items():

        print(
            f"\nEvaluating: {model_name}"
        )

        metrics_df = evaluate_model(
            df,
            features
        )

        results.append({

            "Model":
                model_name,

            "Precision@1":
                metrics_df[
                    "precision@1"
                ].mean(),

            "Recall@1":
                metrics_df[
                    "recall@1"
                ].mean(),

            "Precision@3":
                metrics_df[
                    "precision@3"
                ].mean(),

            "Recall@3":
                metrics_df[
                    "recall@3"
                ].mean(),

            "NDCG@3":
                metrics_df[
                    "ndcg@3"
                ].mean(),

            "NDCG@5":
                metrics_df[
                    "ndcg@5"
                ].mean(),

            "MRR":
                metrics_df[
                    "mrr"
                ].mean()
        })

    results_df = pd.DataFrame(
        results
    )

    print("\n" + "=" * 80)
    print("GROUPED RANKING RESULTS")
    print("=" * 80)

    print(
        results_df.to_string(
            index=False,
            formatters={

                "Precision@1":
                    "{:.4f}".format,

                "Recall@1":
                    "{:.4f}".format,

                "Precision@3":
                    "{:.4f}".format,

                "Recall@3":
                    "{:.4f}".format,

                "NDCG@3":
                    "{:.4f}".format,

                "NDCG@5":
                    "{:.4f}".format,

                "MRR":
                    "{:.4f}".format
            }
        )
    )

    results_df.to_csv(
        "data/ranking_ablation_results.csv",
        index=False
    )

    print(
        "\nResults saved to:"
        " data/ranking_ablation_results.csv"
    )

    print("\n" + "=" * 80)
    print("RANKING EVALUATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()