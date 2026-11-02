"""Student-held-out evaluation of the exact model that is served in production.

This mirrors ``save_model.py``: the same feature order and the classifier
hyperparameters recorded in the active joblib bundle are refitted per fold with
``GroupKFold`` so no student appears in both training and test data.

The labels in ``matching_topk_labeled.csv`` are prototype heuristics (the top
three candidates by a formula that deliberately excludes TF-IDF and semantic
similarity). These metrics therefore measure agreement with that formula, not
real student or faculty outcomes. Do not present them as human relevance.

Run from ``backend/``:

    python evaluate_grouped_ranking.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


BACKEND_DIR = Path(__file__).resolve().parent
DATA_FILE = BACKEND_DIR / "data" / "matching_topk_labeled.csv"
MODEL_FILE = BACKEND_DIR / "models" / "researchtwin_logistic_v2_7features.joblib"
K_VALUES = (1, 3, 5)
PARAM_KEYS = ("C", "class_weight", "solver", "max_iter", "random_state")


def training_recipe():
    """Read the served feature order and classifier settings from the bundle."""

    bundle = joblib.load(MODEL_FILE)
    classifier = bundle["model"].named_steps["classifier"]
    params = {key: classifier.get_params()[key] for key in PARAM_KEYS}
    return list(bundle["features"]), params


def ranking_metrics(y_true, scores, k):
    order = np.argsort(scores)[::-1]
    ranked = np.asarray(y_true)[order]
    hits = ranked[:k]
    total_relevant = int(np.sum(y_true))

    precision = float(np.mean(hits)) if len(hits) else 0.0
    recall = float(np.sum(hits) / total_relevant) if total_relevant else 0.0

    discounts = np.log2(np.arange(2, len(hits) + 2))
    dcg = float(np.sum((2 ** hits - 1) / discounts))
    ideal = np.sort(y_true)[::-1][:k]
    idcg = float(np.sum((2 ** ideal - 1) / np.log2(np.arange(2, len(ideal) + 2))))
    ndcg = dcg / idcg if idcg else 0.0

    precisions_at_i = np.cumsum(hits) / np.arange(1, len(hits) + 1)
    average_precision = (
        float(np.sum(precisions_at_i * hits) / min(total_relevant, k))
        if total_relevant
        else 0.0
    )

    relevant_positions = np.where(ranked == 1)[0]
    reciprocal_rank = (
        float(1.0 / (relevant_positions[0] + 1)) if len(relevant_positions) else 0.0
    )

    return {
        "precision": precision,
        "recall": recall,
        "ndcg": ndcg,
        "average_precision": average_precision,
        "reciprocal_rank": reciprocal_rank,
    }


def calibration_table(y_true, probabilities, bins=10):
    frame = pd.DataFrame({"y": y_true, "p": probabilities})
    frame["bucket"] = pd.cut(frame["p"], bins=bins, labels=False, include_lowest=True)
    table = (
        frame.groupby("bucket")
        .agg(rows=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean"))
        .reset_index()
    )
    table["mean_predicted"] = table["mean_predicted"].round(4)
    table["observed_rate"] = table["observed_rate"].round(4)
    return table


def main():
    features, params = training_recipe()
    df = pd.read_csv(DATA_FILE)
    missing = [name for name in features if name not in df.columns]
    if missing:
        raise SystemExit(f"Dataset is missing serving features: {missing}")

    X = df[features]
    y = df["relevance_label"].values
    groups = df["student_id"].values

    print(f"Serviced features ({len(features)}): {features}")
    print(f"Classifier settings: {params}")

    oof_scores = np.zeros(len(df))

    for fold, (train_idx, test_idx) in enumerate(
        GroupKFold(n_splits=5).split(X, y, groups), start=1
    ):
        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(**params)),
            ]
        )
        model.fit(X.iloc[train_idx], y[train_idx])
        oof_scores[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
        print(f"Fold {fold} held-out students: {sorted(set(groups[test_idx]))}")

    rows = []
    for student_id, indices in df.groupby("student_id").groups.items():
        indices = np.asarray(indices)
        row = {"student_id": student_id}
        for k in K_VALUES:
            metrics = ranking_metrics(y[indices], oof_scores[indices], k)
            row[f"P@{k}"] = metrics["precision"]
            row[f"R@{k}"] = metrics["recall"]
            row[f"NDCG@{k}"] = metrics["ndcg"]
        row["MAP@5"] = ranking_metrics(y[indices], oof_scores[indices], 5)[
            "average_precision"
        ]
        row["MRR"] = ranking_metrics(y[indices], oof_scores[indices], 1)[
            "reciprocal_rank"
        ]
        rows.append(row)

    results = pd.DataFrame(rows)
    print("\n" + "=" * 78)
    print("SERVED-MODEL GROUPED STUDENT-LEVEL EVALUATION (out-of-fold)")
    print("=" * 78)
    print(results.to_string(index=False, float_format=lambda value: f"{value:.4f}"))

    summary = {
        column: round(float(results[column].mean()), 4)
        for column in results.columns
        if column != "student_id"
    }
    summary.update(
        {
            "Brier": round(float(brier_score_loss(y, oof_scores)), 4),
            "LogLoss": round(
                float(log_loss(y, np.clip(oof_scores, 1e-6, 1 - 1e-6))), 4
            ),
            "ROC_AUC": round(float(roc_auc_score(y, oof_scores)), 4),
            "positive_rate": round(float(np.mean(y)), 4),
        }
    )

    print("\n" + "-" * 78)
    print("AVERAGE ACROSS HELD-OUT STUDENTS")
    print("-" * 78)
    print(json.dumps(summary, indent=2, sort_keys=True))

    print("\nOut-of-fold calibration (deciles):")
    print(
        calibration_table(y, oof_scores).to_string(
            index=False, float_format=lambda value: f"{value:.4f}"
        )
    )
    print(
        "\nLabels are prototype heuristics, not observed student outcomes; "
        "treat these scores as agreement with the prototype formula."
    )


if __name__ == "__main__":
    main()
