import pandas as pd
import numpy as np

from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


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
    groups = df["student_id"]

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        (
            "classifier",
            LogisticRegression(
                max_iter=2000,
                random_state=42
            )
        )
    ])

    parameter_grid = {
        "classifier__C": [
            0.01,
            0.1,
            1.0,
            10.0,
            100.0
        ],
        "classifier__class_weight": [
            "balanced",
            None
        ],
        "classifier__solver": [
            "liblinear",
            "lbfgs"
        ]
    }

    cv = GroupKFold(
        n_splits=5
    )

    search = GridSearchCV(
        estimator=pipeline,
        param_grid=parameter_grid,
        scoring="roc_auc",
        cv=cv,
        n_jobs=-1,
        refit=True
    )

    search.fit(
        X,
        y,
        groups=groups
    )

    print("\n" + "=" * 65)
    print("LOGISTIC REGRESSION HYPERPARAMETER OPTIMIZATION")
    print("=" * 65)

    print("\nBest parameters:")

    for key, value in search.best_params_.items():
        print(
            f"{key}: {value}"
        )

    print(
        f"\nBest grouped CV ROC-AUC: "
        f"{search.best_score_:.4f}"
    )

    print("\nTop configurations:")

    results = pd.DataFrame(
        search.cv_results_
    )

    top_results = results.sort_values(
        "rank_test_score"
    ).head(10)

    print(
        top_results[
            [
                "rank_test_score",
                "mean_test_score",
                "std_test_score",
                "param_classifier__C",
                "param_classifier__class_weight",
                "param_classifier__solver"
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()