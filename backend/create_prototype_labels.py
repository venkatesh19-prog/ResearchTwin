import pandas as pd


INPUT_FILE = "data/matching_features.csv"
OUTPUT_FILE = "data/matching_labeled.csv"


def calculate_relevance_score(row):
    score = (
        0.30 * row["research_area_similarity"]
        + 0.20 * row["expertise_similarity"]
        + 0.15 * row["skill_overlap"]
        + 0.20 * row["project_similarity"]
        + 0.15 * row["publication_similarity"]
    )

    return round(score, 4)


def main():

    df = pd.read_csv(INPUT_FILE)

    # Independent prototype relevance score.
    #
    # IMPORTANT:
    # semantic_similarity and tfidf_similarity are
    # intentionally NOT used here.

    df["prototype_relevance_score"] = df.apply(
        calculate_relevance_score,
        axis=1
    )

    df["relevance_label"] = (
        df["prototype_relevance_score"] >= 0.60
    ).astype(int)

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nPrototype labels created successfully.")
    print(f"Rows: {len(df)}")
    print(f"Saved: {OUTPUT_FILE}")

    print("\nLabel distribution:")
    print(
        df["relevance_label"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print("\nPrototype relevance statistics:")
    print(
        df["prototype_relevance_score"]
        .describe()
        .to_string()
    )

    print("\nSample labeled pairs:")
    print(
        df[
            [
                "student_id",
                "researcher_id",
                "prototype_relevance_score",
                "relevance_label"
            ]
        ]
        .head(20)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()