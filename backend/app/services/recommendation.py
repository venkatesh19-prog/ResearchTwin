import hashlib
import importlib.util
import os
import threading

import joblib
import pandas as pd

from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import Researcher
from .researcher_intelligence import build_structured_profile
from .semantic_matching import (
    SemanticMatchingError,
    build_student_text,
    build_researcher_text,
    calculate_semantic_similarity,
    verify_model_files,
)
from .skill_gap import calculate_skill_gap, normalize_skills


class RecommendationError(RuntimeError):
    """Raised when the model bundle or recommendation pipeline is unusable."""


# =========================================================
# MODEL CONFIGURATION
# =========================================================

MODEL_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "models",
        "researchtwin_logistic_v2_7features.joblib"
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

# Order matters: the model was trained on this exact column order.
EXPECTED_FEATURES = (
    "tfidf_similarity",
    "semantic_similarity",
    "research_area_similarity",
    "expertise_similarity",
    "skill_overlap",
    "project_similarity",
    "publication_similarity",
)

_model_bundle = None
_shap_explainer = None
_model_lock = threading.Lock()
_shap_lock = threading.Lock()


# =========================================================
# MODEL LOADING
# =========================================================

def validate_model_bundle(bundle):
    """Reject bundles that would silently mis-score candidates."""

    if not isinstance(bundle, dict):
        raise RecommendationError(
            "Model bundle must be a dictionary."
        )

    model = bundle.get("model")
    features = bundle.get("features")

    if model is None or features is None:
        raise RecommendationError(
            "Model bundle must contain 'model' and 'features'."
        )

    features = list(features)

    if features != list(EXPECTED_FEATURES):
        raise RecommendationError(
            "Model bundle feature order does not match the serving "
            f"feature order. Expected {list(EXPECTED_FEATURES)}, "
            f"found {features}."
        )

    steps = getattr(model, "named_steps", None) or {}
    missing_steps = {"scaler", "classifier"} - set(steps)

    if missing_steps:
        raise RecommendationError(
            "Model bundle must be a pipeline containing "
            f"{sorted(missing_steps)} step(s)."
        )

    return bundle


def load_model():

    global _model_bundle

    if _model_bundle is not None:
        return _model_bundle

    with _model_lock:

        if _model_bundle is not None:
            return _model_bundle

        if not os.path.exists(MODEL_PATH):
            raise RecommendationError(
                f"ResearchTwin model not found: {MODEL_PATH}"
            )

        try:
            bundle = joblib.load(MODEL_PATH)
        except Exception as exc:
            raise RecommendationError(
                f"Could not load ResearchTwin model from "
                f"{MODEL_PATH}: {exc}"
            ) from exc

        _model_bundle = validate_model_bundle(bundle)

    return _model_bundle


_LAZY_RUNTIME_MODULES = ("onnxruntime", "tokenizers", "shap")


def _missing_lazy_runtime_modules():
    missing = []

    for name in _LAZY_RUNTIME_MODULES:
        try:
            installed = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            installed = False

        if not installed:
            missing.append(name)

    return missing


def verify_serving_artifacts():
    """Validate the serving artifacts without loading heavy ML extras.

    Loading the model bundle imports scikit-learn only; the ONNX embedding
    session used for semantic similarity is not created here.
    """

    missing = _missing_lazy_runtime_modules()

    if missing:
        raise RecommendationError(
            "Lazy recommendation dependencies are not installed: "
            + ", ".join(missing)
        )

    try:
        verify_model_files()
    except SemanticMatchingError as exc:
        raise RecommendationError(str(exc)) from exc

    bundle = load_model()

    if not os.path.exists(DATA_PATH):
        raise RecommendationError(
            f"SHAP background data not found: {DATA_PATH}"
        )

    recorded = bundle.get("training_data_sha256")

    if not recorded:
        raise RecommendationError(
            "Model bundle does not record the training dataset hash."
        )

    with open(DATA_PATH, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()

    if digest != recorded:
        raise RecommendationError(
            "SHAP background data does not match the dataset this "
            "model was trained on."
        )

    return {
        "model_version": bundle.get("model_version"),
        "dataset_sha256": digest,
    }


def get_shap_explainer():

    global _shap_explainer

    if _shap_explainer is not None:
        return _shap_explainer

    with _shap_lock:

        if _shap_explainer is not None:
            return _shap_explainer

        import shap

        bundle = load_model()

        model = bundle["model"]
        features = bundle["features"]

        scaler = model.named_steps["scaler"]
        classifier = model.named_steps["classifier"]

        if not os.path.exists(DATA_PATH):
            raise RecommendationError(
                f"SHAP background data not found: {DATA_PATH}"
            )

        try:
            training_df = pd.read_csv(DATA_PATH)
            X_background = training_df[list(features)]

            # Limit SHAP background rows to reduce explanation overhead.
            X_background = X_background.sample(
                n=min(50, len(X_background)),
                random_state=42
            )

            X_background_scaled = scaler.transform(
                X_background
            )

            _shap_explainer = shap.LinearExplainer(
                classifier,
                X_background_scaled
            )
        except Exception as exc:
            raise RecommendationError(
                f"Could not initialise the SHAP explainer: {exc}"
            ) from exc

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

    try:
        matrix = vectorizer.fit_transform(
            [student_text, researcher_text]
        )
    except ValueError:
        # Stop-word-only input produces an empty vocabulary, which is
        # the same "no lexical signal" case as empty text.
        return 0.0

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

    student_set = normalize_skills(student_skills)
    researcher_set = normalize_skills(researcher_skills)

    if not researcher_set:
        return 0.0

    overlap = student_set.intersection(
        researcher_set
    )

    return float(
        len(overlap) / len(researcher_set)
    )


# =========================================================
# BUILD 7 ML FEATURES
# =========================================================

def calculate_features(
    student_profile,
    researcher,
    semantic_score=None,
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

    if semantic_score is None:
        from .semantic_matching import get_model

        model = get_model()

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
    else:
        semantic_similarity = float(semantic_score)

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

    if top_k < 1:
        raise RecommendationError(
            "top_k must be at least 1."
        )

    researchers = db.query(
        Researcher
    ).all()

    if not researchers:
        return []

    bundle = load_model()

    model = bundle["model"]
    features = bundle["features"]

    # -----------------------------------------------------
    # STEP 1: Batch semantic similarity and feature engineering
    # -----------------------------------------------------

    semantic_results = calculate_semantic_similarity(
        student_profile,
        researchers
    )

    # Missing or foreign semantic ids must not silently become 0.0:
    # that would corrupt ranking without any visible signal.
    semantic_by_id = {}

    for result in semantic_results:
        result_id = result["researcher_id"]

        if result_id in semantic_by_id:
            raise RecommendationError(
                f"Duplicate semantic result for researcher {result_id}."
            )

        semantic_by_id[result_id] = result

    researcher_ids = {researcher.id for researcher in researchers}
    unknown_ids = set(semantic_by_id) - researcher_ids
    missing_ids = researcher_ids - set(semantic_by_id)

    if unknown_ids:
        raise RecommendationError(
            "Semantic results reference unknown researcher ids: "
            f"{sorted(unknown_ids)}."
        )

    if missing_ids:
        raise RecommendationError(
            "Semantic results are missing researcher ids: "
            f"{sorted(missing_ids)}."
        )

    candidate_rows = []

    for researcher in researchers:
        semantic_entry = semantic_by_id[researcher.id]

        feature_dict = calculate_features(
            student_profile,
            researcher,
            semantic_score=semantic_entry["semantic_score"],
        )

        candidate_rows.append({
            "researcher": researcher,
            "semantic_available": bool(
                semantic_entry.get("semantic_available", True)
            ),
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

    try:
        explainer = get_shap_explainer()

        shap_result = explainer(
            X_top_scaled
        )
    except RecommendationError:
        raise
    except Exception as exc:
        raise RecommendationError(
            "Could not generate SHAP explanations."
        ) from exc

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

            "semantic_available":
                row["semantic_available"],

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
