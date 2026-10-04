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
    "department_match",
]


def main():

    print("\n" + "=" * 80)
    print("RESEARCHTWIN - ERROR ANALYSIS")
    print("=" * 80)

    df = pd.read_csv(DATA_FILE)

    groups = df["student_id"]

    cv = GroupKFold(n_splits=5)

    all_results = []

    for fold, (train_idx, test_idx) in enumerate(
        cv.split(
            df,
            df["relevance_label"],
            groups
        ),
        start=1
    ):

        train_df = df.iloc[train_idx]
        test_df = df.iloc[test_idx]

        X_train = train_df[FEATURES]
        y_train = train_df["relevance_label"]

        X_test = test_df[FEATURES]
        y_test = test_df["relevance_label"]

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

        fold_results = test_df.copy()

        fold_results["predicted_probability"] = probabilities
        fold_results["predicted_label"] = predictions
        fold_results["fold"] = fold

        all_results.append(
            fold_results
        )

    results = pd.concat(
        all_results,
        ignore_index=True
    )

    # =====================================================
    # ERROR TYPES
    # =====================================================

    false_positives = results[
        (results["relevance_label"] == 0) &
        (results["predicted_label"] == 1)
    ].copy()

    false_negatives = results[
        (results["relevance_label"] == 1) &
        (results["predicted_label"] == 0)
    ].copy()

    true_positives = results[
        (results["relevance_label"] == 1) &
        (results["predicted_label"] == 1)
    ].copy()

    true_negatives = results[
        (results["relevance_label"] == 0) &
        (results["predicted_label"] == 0)
    ].copy()

    # =====================================================
    # SUMMARY
    # =====================================================

    print("\n" + "=" * 80)
    print("ERROR SUMMARY")
    print("=" * 80)

    print(
        f"\nTrue Positives : {len(true_positives)}"
    )

    print(
        f"True Negatives : {len(true_negatives)}"
    )

    print(
        f"False Positives: {len(false_positives)}"
    )

    print(
        f"False Negatives: {len(false_negatives)}"
    )

    # =====================================================
    # FALSE POSITIVES
    # =====================================================

    print("\n" + "=" * 80)
    print("TOP FALSE POSITIVES")
    print("=" * 80)

    if len(false_positives) > 0:

        fp = false_positives.sort_values(
            "predicted_probability",
            ascending=False
        )

        print(
            fp[
                [
                    "student_id",
                    "researcher_id",
                    "predicted_probability",
                    "tfidf_similarity",
                    "semantic_similarity",
                    "research_area_similarity",
                    "expertise_similarity",
                    "skill_overlap",
                    "project_similarity",
                    "publication_similarity",
                ]
            ].head(15).to_string(
                index=False
            )
        )

    else:

        print(
            "\nNo false positives."
        )

    # =====================================================
    # FALSE NEGATIVES
    # =====================================================

    print("\n" + "=" * 80)
    print("FALSE NEGATIVES")
    print("=" * 80)

    if len(false_negatives) > 0:

        fn = false_negatives.sort_values(
            "predicted_probability",
            ascending=False
        )

        print(
            fn[
                [
                    "student_id",
                    "researcher_id",
                    "predicted_probability",
                    "tfidf_similarity",
                    "semantic_similarity",
                    "research_area_similarity",
                    "expertise_similarity",
                    "skill_overlap",
                    "project_similarity",
                    "publication_similarity",
                ]
            ].to_string(
                index=False
            )
        )

    else:

        print(
            "\nNo false negatives."
        )

    # =====================================================
    # LOW-CONFIDENCE CASES
    # =====================================================

    print("\n" + "=" * 80)
    print("LOW-CONFIDENCE CASES")
    print("=" * 80)

    results["confidence_distance"] = abs(
        results["predicted_probability"] - 0.5
    )

    low_confidence = results.sort_values(
        "confidence_distance"
    ).head(15)

    print(
        low_confidence[
            [
                "student_id",
                "researcher_id",
                "relevance_label",
                "predicted_probability",
                "tfidf_similarity",
                "semantic_similarity",
                "research_area_similarity",
                "expertise_similarity",
                "skill_overlap",
            ]
        ].to_string(
            index=False
        )
    )

    # =====================================================
    # STUDENT-LEVEL PERFORMANCE
    # =====================================================

    print("\n" + "=" * 80)
    print("STUDENT-LEVEL ERROR COUNTS")
    print("=" * 80)

    student_errors = results.copy()

    student_errors["error"] = (
        student_errors["relevance_label"]
        != student_errors["predicted_label"]
    )

    student_summary = (
        student_errors
        .groupby("student_id")
        .agg(
            total_cases=(
                "student_id",
                "count"
            ),
            errors=(
                "error",
                "sum"
            )
        )
        .reset_index()
    )

    student_summary["error_rate"] = (
        student_summary["errors"]
        /
        student_summary["total_cases"]
    )

    print(
        student_summary
        .sort_values(
            "error_rate",
            ascending=False
        )
        .to_string(
            index=False
        )
    )

    # =====================================================
    # SAVE RESULTS
    # =====================================================

    results.to_csv(
        "data/error_analysis_predictions.csv",
        index=False
    )

    false_positives.to_csv(
        "data/false_positives.csv",
        index=False
    )

    false_negatives.to_csv(
        "data/false_negatives.csv",
        index=False
    )

    student_summary.to_csv(
        "data/student_error_summary.csv",
        index=False
    )

    print("\n" + "=" * 80)
    print("ERROR ANALYSIS COMPLETE")
    print("=" * 80)

    print(
        "\nSaved:"
    )

    print(
        " - data/error_analysis_predictions.csv"
    )

    print(
        " - data/false_positives.csv"
    )

    print(
        " - data/false_negatives.csv"
    )

    print(
        " - data/student_error_summary.csv"
    )


if __name__ == "__main__":
    main()