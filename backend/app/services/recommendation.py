import os
import joblib
import pandas as pd
import shap

from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import Researcher
from .researcher_intelligence import build_structured_profile
from .semantic_matching import build_student_text, build_researcher_text
from .skill_gap import calculate_skill_gap


# =========================================================
# MODEL CONFIGURATION
# =========================================================

MODEL_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "models",
        "researchtwin_logistic.joblib"
    )
)

DATA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
        "matching_topk_labeled.csv"
    )
)

_model_bundle = None
_shap_explainer = None


# =========================================================
# MODEL LOADING
# =========================================================

def load_model():

    global _model_bundle

    if _model_bundle is None:

        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"ResearchTwin model not found: {MODEL_PATH}"
            )

        _model_bundle = joblib.load(MODEL_PATH)

    return _model_bundle


def get_shap_explainer():

    global _shap_explainer

    if _shap_explainer is None:

        bundle = load_model()

        model = bundle["model"]
        features = bundle["features"]

        scaler = model.named_steps["scaler"]
        classifier = model.named_steps["classifier"]

        training_df = pd.read_csv(DATA_PATH)

        X_background = training_df[features]

        X_background_scaled = scaler.transform(
            X_background
        )

        _shap_explainer = shap.LinearExplainer(
            classifier,
            X_background_scaled,
            max_samples=len(X_background_scaled)
        )

    return _shap_explainer


# =========================================================
# TEXT SIMILARITY
# =========================================================

def calculate_tfidf_similarity(
    student_text: str,
    researcher_text: str
):

    if not student_text or not researcher_text:
        return 0.0

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2)
    )

    matrix = vectorizer.fit_transform(
        [student_text, researcher_text]
    )

    score = cosine_similarity(
        matrix[0:1],
        matrix[1:2]
    )[0][0]

    return float(score)


# =========================================================
# FIELD SIMILARITY
# =========================================================

def field_similarity(
    student_value,
    researcher_value
):

    return calculate_tfidf_similarity(
        str(student_value or "").strip(),
        str(researcher_value or "").strip()
    )


# =========================================================
# SKILL OVERLAP
# =========================================================

def calculate_skill_overlap(
    student_skills,
    researcher_skills
):

    student_set = {
        skill.strip().lower()
        for skill in str(student_skills or "").split(",")
        if skill.strip()
    }

    researcher_set = {
        skill.strip().lower()
        for skill in str(researcher_skills or "").split(",")
        if skill.strip()
    }

    if not researcher_set:
        return 0.0

    overlap = student_set.intersection(
        researcher_set
    )

    return float(
        len(overlap) / len(researcher_set)
    )


# =========================================================
# DEPARTMENT MATCH
# =========================================================

def calculate_department_match(
    student_profile,
    researcher
):

    student_department = str(
        student_profile.get("department", "")
    ).strip().lower()

    researcher_department = str(
        researcher.department or ""
    ).strip().lower()

    if not student_department:
        return 0.0

    if not researcher_department:
        return 0.0

    return 1.0 if (
        student_department ==
        researcher_department
    ) else 0.0


# =========================================================
# BUILD 8 ML FEATURES
# =========================================================

def calculate_features(
    student_profile,
    researcher
):

    researcher_profile = build_structured_profile(
        researcher
    )

    # ---------------------------------------------
    # Individual field similarities
    # ---------------------------------------------

    research_area_similarity = field_similarity(
        student_profile.get("research_areas", ""),
        researcher_profile.get("research_areas", "")
    )

    expertise_similarity = field_similarity(
        student_profile.get("expertise", ""),
        researcher_profile.get("expertise", "")
    )

    project_similarity = field_similarity(
        student_profile.get("projects", ""),
        researcher_profile.get("projects", "")
    )

    publication_similarity = field_similarity(
        student_profile.get("publications", ""),
        researcher_profile.get("publications", "")
    )

    skill_overlap = calculate_skill_overlap(
        student_profile.get("skills", ""),
        researcher_profile.get("skills", "")
    )

    # ---------------------------------------------
    # Combined TF-IDF similarity
    # ---------------------------------------------

    student_text = build_student_text(
        student_profile
    )

    researcher_text = build_researcher_text(
        researcher
    )

    tfidf_similarity = calculate_tfidf_similarity(
        student_text,
        researcher_text
    )

    # ---------------------------------------------
    # Semantic similarity
    # ---------------------------------------------

    from .semantic_matching import model

    student_embedding = model.encode(
        [student_text],
        normalize_embeddings=True
    )

    researcher_embedding = model.encode(
        [researcher_text],
        normalize_embeddings=True
    )

    semantic_similarity = float(
        cosine_similarity(
            student_embedding,
            researcher_embedding
        )[0][0]
    )

    # ---------------------------------------------
    # Department
    # ---------------------------------------------

    department_match = calculate_department_match(
        student_profile,
        researcher
    )

    return {

        "tfidf_similarity":
            tfidf_similarity,

        "semantic_similarity":
            semantic_similarity,

        "research_area_similarity":
            research_area_similarity,

        "expertise_similarity":
            expertise_similarity,

        "skill_overlap":
            skill_overlap,

        "project_similarity":
            project_similarity,

        "publication_similarity":
            publication_similarity,

        "department_match":
            department_match,
    }


# =========================================================
# HUMAN READABLE EXPLANATION
# =========================================================

FEATURE_NAMES = {

    "tfidf_similarity":
        "textual research similarity",

    "semantic_similarity":
        "semantic research similarity",

    "research_area_similarity":
        "research-area alignment",

    "expertise_similarity":
        "expertise alignment",

    "skill_overlap":
        "shared technical skills",

    "project_similarity":
        "project similarity",

    "publication_similarity":
        "publication similarity",

    "department_match":
        "department alignment",
}


def generate_explanation(
    shap_values,
    feature_values,
    features
):

    contributions = []

    for feature, shap_value, feature_value in zip(
        features,
        shap_values,
        feature_values
    ):

        contributions.append({

            "feature": feature,

            "shap_value":
                float(shap_value),

            "feature_value":
                float(feature_value)
        })

    contributions.sort(
        key=lambda item:
            abs(item["shap_value"]),
        reverse=True
    )

    positive = [
        item
        for item in contributions
        if item["shap_value"] > 0
    ]

    negative = [
        item
        for item in contributions
        if item["shap_value"] < 0
    ]

    positive_names = [
        FEATURE_NAMES.get(
            item["feature"],
            item["feature"]
        )
        for item in positive[:3]
    ]

    if len(positive_names) == 1:

        summary = (
            "The recommendation is primarily "
            f"supported by {positive_names[0]}."
        )

    elif len(positive_names) == 2:

        summary = (
            "The recommendation is primarily "
            f"supported by {positive_names[0]} "
            f"and {positive_names[1]}."
        )

    elif len(positive_names) >= 3:

        summary = (
            "The recommendation is primarily "
            f"supported by {positive_names[0]}, "
            f"{positive_names[1]}, and "
            f"{positive_names[2]}."
        )

    else:

        summary = (
            "The model found limited positive "
            "evidence for this researcher match."
        )

    return {

        "summary": summary,

        "top_positive_factors":
            positive[:5],

        "top_negative_factors":
            negative[:5],

        "all_contributions":
            contributions
    }


# =========================================================
# MAIN RECOMMENDATION ENGINE
# =========================================================

def generate_recommendations(
    student_profile: dict,
    db: Session,
    top_k: int = 5
):

    researchers = db.query(
        Researcher
    ).all()

    if not researchers:
        return []

    bundle = load_model()

    model = bundle["model"]
    features = bundle["features"]

    # -----------------------------------------------------
    # STEP 1: Feature engineering
    # -----------------------------------------------------

    candidate_rows = []

    for researcher in researchers:

        feature_dict = calculate_features(
            student_profile,
            researcher
        )

        candidate_rows.append({

            "researcher":
                researcher,

            **feature_dict
        })

    # -----------------------------------------------------
    # STEP 2: ML feature matrix
    # -----------------------------------------------------

    X = pd.DataFrame([

        {
            feature:
                row[feature]
            for feature in features
        }

        for row in candidate_rows
    ])

    # -----------------------------------------------------
    # STEP 3: Predict probability
    # -----------------------------------------------------

    probabilities = model.predict_proba(
        X
    )[:, 1]

    for row, probability in zip(
        candidate_rows,
        probabilities
    ):

        row["model_score"] = float(
            probability
        )

    # -----------------------------------------------------
    # STEP 4: Rank
    # -----------------------------------------------------

    candidate_rows.sort(
        key=lambda row:
            row["model_score"],
        reverse=True
    )

    candidate_rows = candidate_rows[:top_k]

    # -----------------------------------------------------
    # STEP 5: SHAP
    # -----------------------------------------------------

    scaler = model.named_steps["scaler"]

    explainer = get_shap_explainer()

    X_top = pd.DataFrame([

        {
            feature:
                row[feature]
            for feature in features
        }

        for row in candidate_rows
    ])

    X_top_scaled = scaler.transform(
        X_top
    )

    shap_result = explainer(
        X_top_scaled
    )

    # -----------------------------------------------------
    # STEP 6: Final response
    # -----------------------------------------------------

    final_results = []

    for index, row in enumerate(
        candidate_rows
    ):

        researcher = row["researcher"]

        explanation = generate_explanation(
            shap_result.values[index],
            X_top.iloc[index].values,
            features
        )

        skill_gap = calculate_skill_gap(
            student_profile.get(
                "skills",
                ""
            ),
            researcher
        )

        final_results.append({

            "researcher_id":
                researcher.id,

            "name":
                researcher.name,

            "department":
                researcher.department,

            "match_score":
                round(
                    row["model_score"],
                    4
                ),

            "component_scores": {

                feature:
                    round(
                        float(
                            row[feature]
                        ),
                        4
                    )

                for feature in features
            },

            "why_recommended":
                explanation["summary"],

            "explanation":
                explanation,

            "matched_skills":
                skill_gap[
                    "matched_skills"
                ],

            "skill_gap":
                skill_gap[
                    "skill_gap"
                ]
        })

    return final_results