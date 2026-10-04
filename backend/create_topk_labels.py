import pandas as pd

INPUT_FILE = "data/matching_features.csv"
OUTPUT_FILE = "data/matching_topk_labeled.csv"

TOP_K = 3


def main():

    df = pd.read_csv(INPUT_FILE)

    # Independent prototype relevance score.
    # Deliberately excludes TF-IDF and semantic similarity.
    df["prototype_relevance_score"] = (
        0.30 * df["research_area_similarity"]
        + 0.20 * df["expertise_similarity"]
        + 0.15 * df["skill_overlap"]
        + 0.20 * df["project_similarity"]
        + 0.15 * df["publication_similarity"]
    )

    # Rank candidates independently for each student.
    df["student_rank"] = (
        df.groupby("student_id")["prototype_relevance_score"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    # Top-K candidates are prototype relevant.
    df["relevance_label"] = (
        df["student_rank"] <= TOP_K
    ).astype(int)

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nTop-K prototype labels created.")
    print(f"Students: {df['student_id'].nunique()}")
    print(f"Researchers per student: {df.groupby('student_id').size().iloc[0]}")
    print(f"Top-K: {TOP_K}")
    print(f"Total pairs: {len(df)}")

    print("\nLabel distribution:")
    print(
        df["relevance_label"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print("\nRelevant pairs:")
    relevant = df[df["relevance_label"] == 1].sort_values(
        ["student_id", "student_rank"]
    )

    print(
        relevant[
            [
                "student_id",
                "researcher_id",
                "prototype_relevance_score",
                "student_rank"
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()