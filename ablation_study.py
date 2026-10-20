import os
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score

DATA_FILE = "data/matching_topk_labeled.csv"
MODEL_SAVE_PATH = "models/hybrid_matching_model.pkl"

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
    "TF-IDF Only": ["tfidf_similarity"],
    "Semantic Only": ["semantic_similarity"],
    "Structured Features": [
        "research_area_similarity", "expertise_similarity", "skill_overlap",
        "project_similarity", "publication_similarity", "department_match"
    ],
    "Hybrid Model": ALL_FEATURES,
}

def evaluate_experiment(df, feature_list, groups):
    X = df[feature_list]
    y = df["relevance_label"]
    group_kfold = GroupKFold(n_splits=5)

    all_true, all_probs, all_preds = [], [], []

    for train_idx, test_idx in group_kfold.split(X, y, groups):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(C=0.01, solver="liblinear", max_iter=2000, random_state=42))
        ])

        model.fit(X_train, y_train)
        probs = model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)

        all_true.extend(y_test.tolist())
        all_probs.extend(probs.tolist())
        all_preds.extend(preds.tolist())

    return {
        "ROC-AUC": roc_auc_score(all_true, all_probs),
        "Precision": precision_score(all_true, all_preds, zero_division=0),
        "Recall": recall_score(all_true, all_preds, zero_division=0),
        "F1": f1_score(all_true, all_preds, zero_division=0),
    }

def main():
    if not os.path.exists(DATA_FILE):
        import generate_dataset
        generate_dataset.generate_pairwise_features()

    df = pd.read_csv(DATA_FILE)
    groups = df["student_id"]
    results = []

    for name, features in EXPERIMENTS.items():
        metrics = evaluate_experiment(df, features, groups)
        results.append({"Model": name, **metrics})

    results_df = pd.DataFrame(results)
    os.makedirs("data", exist_ok=True)
    results_df.to_csv("data/ablation_results.csv", index=False)
    print("\n=== ABLATION STUDY RESULTS ===")
    print(results_df.to_string(index=False))

    final_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(C=0.01, solver="liblinear", max_iter=2000, random_state=42))
    ])
    final_pipeline.fit(df[ALL_FEATURES], df["relevance_label"])
    
    os.makedirs("models", exist_ok=True)
    joblib.dump(final_pipeline, MODEL_SAVE_PATH)
    print(f"\nSaved production model to {MODEL_SAVE_PATH}")

if __name__ == "__main__":
    main()