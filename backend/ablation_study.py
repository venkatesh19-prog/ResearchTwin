import pandas as pd
import numpy as np

from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score
)


DATA_FILE = "data/matching_topk_labeled.csv"

ALL_FEATURES = [
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
    "department_match",
]

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

    "Hybrid Model": ALL_FEATURES,
}


def evaluate_experiment(
    df,
    feature_list,
    groups
):

    X = df[feature_list]
    y = df["relevance_label"]

    group_kfold = GroupKFold(
        n_splits=5
    )

    all_true = []
    all_probabilities = []
    all_predictions = []

    for train_idx, test_idx in group_kfold.split(
        X,
        y,
        groups
    ):

        X_train = X.iloc[train_idx]
        X_test = X.iloc[test_idx]

        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]

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

        probabilities = model.predict_proba(
            X_test
        )[:, 1]

        predictions = (
            probabilities >= 0.5
        ).astype(int)

        all_true.extend(
            y_test.tolist()
        )

        all_probabilities.extend(
            probabilities.tolist()
        )

        all_predictions.extend(
            predictions.tolist()
        )

    roc_auc = roc_auc_score(
        all_true,
        all_probabilities
    )

    precision = precision_score(
        all_true,
        all_predictions,
        zero_division=0
    )

    recall = recall_score(
        all_true,
        all_predictions,
        zero_division=0
    )

    f1 = f1_score(
        all_true,
        all_predictions,
        zero_division=0
    )

    return {
        "ROC-AUC": roc_auc,
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
    }


def main():

    print("\n" + "=" * 75)
    print("RESEARCHTWIN - ABLATION STUDY")
    print("=" * 75)

    df = pd.read_csv(
        DATA_FILE
    )

    groups = df["student_id"]

    results = []

    for experiment_name, features in EXPERIMENTS.items():

        print(
            f"\nRunning: {experiment_name}"
        )

        metrics = evaluate_experiment(
            df,
            features,
            groups
        )

        results.append({
            "Model": experiment_name,
            **metrics
        })

    results_df = pd.DataFrame(
        results
    )

    print("\n" + "=" * 75)
    print("ABLATION RESULTS")
    print("=" * 75)

    print(
        results_df.to_string(
            index=False,
            formatters={
                "ROC-AUC":
                    "{:.4f}".format,
                "Precision":
                    "{:.4f}".format,
                "Recall":
                    "{:.4f}".format,
                "F1":
                    "{:.4f}".format,
            }
        )
    )

    results_df.to_csv(
        "data/ablation_results.csv",
        index=False
    )

    print(
        "\nResults saved to:"
        " data/ablation_results.csv"
    )

    print("\n" + "=" * 75)
    print("ABLATION STUDY COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()