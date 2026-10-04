import pandas as pd
import shap

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
    print("\n" + "=" * 65)
    print("RESEARCHTWIN - SHAP MODEL EXPLAINABILITY")
    print("=" * 65)

    df = pd.read_csv(DATA_FILE)

    X = df[FEATURES]
    y = df["relevance_label"]
    groups = df["student_id"]

    # Optimized Logistic Regression configuration
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        (
            "classifier",
            LogisticRegression(
                C=0.01,
                class_weight=None,
                solver="liblinear",
                max_iter=2000,
                random_state=42,
            ),
        ),
    ])

    # Train on all prototype data for explainability demonstration
    pipeline.fit(X, y)

    # Transform features before explaining the linear model
    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]

    X_scaled = scaler.transform(X)

    print("\nModel trained successfully.")

    print("\nModel coefficients:")
    for feature, coefficient in zip(FEATURES, classifier.coef_[0]):
        print(f"{feature:30s}: {coefficient:+.6f}")

    # SHAP LinearExplainer
    explainer = shap.LinearExplainer(
        classifier,
        X_scaled
    )

    shap_values = explainer(X_scaled)

    print("\n" + "=" * 65)
    print("GLOBAL FEATURE IMPORTANCE")
    print("=" * 65)

    importance = pd.DataFrame({
        "feature": FEATURES,
        "mean_abs_shap": abs(shap_values.values).mean(axis=0),
    })

    importance = importance.sort_values(
        "mean_abs_shap",
        ascending=False
    )

    print(
        importance.to_string(
            index=False,
            formatters={
                "mean_abs_shap": "{:.6f}".format
            }
        )
    )

    # Explain one positive example
    positive_indices = df.index[
        df["relevance_label"] == 1
    ].tolist()

    if not positive_indices:
        print("\nNo positive examples found.")
        return

    example_index = positive_indices[0]

    print("\n" + "=" * 65)
    print("LOCAL EXPLANATION")
    print("=" * 65)

    print(f"\nStudent: {df.loc[example_index, 'student_id']}")
    print(f"Researcher: {df.loc[example_index, 'researcher_id']}")
    print(f"Label: {df.loc[example_index, 'relevance_label']}")

    print("\nFeature contributions:")

    local_values = shap_values.values[example_index]

    local_explanation = pd.DataFrame({
        "feature": FEATURES,
        "shap_value": local_values,
        "feature_value": X.iloc[example_index].values,
    })

    local_explanation["absolute_shap"] = abs(
        local_explanation["shap_value"]
    )

    local_explanation = local_explanation.sort_values(
        "absolute_shap",
        ascending=False
    )

    print(
        local_explanation[
            ["feature", "feature_value", "shap_value"]
        ].to_string(
            index=False,
            formatters={
                "feature_value": "{:.4f}".format,
                "shap_value": "{:+.6f}".format,
            }
        )
    )

    print("\n" + "=" * 65)
    print("EXPLAINABILITY COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()