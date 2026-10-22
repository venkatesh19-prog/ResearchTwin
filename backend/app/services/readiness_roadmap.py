
from typing import Any


# Starter learning plans. These are editable recommendations,
# not claims about official course requirements.
SKILL_PLANS: dict[str, dict[str, Any]] = {
    "python": {
        "priority": "high",
        "reason": "Python is widely used in research prototyping and data workflows.",
        "milestones": [
            "Review functions, collections, modules, and exceptions.",
            "Implement a small data-processing script.",
            "Write tests and document the script."
        ],
        "project": "Build a CSV research-data analyzer that validates records and summarizes results.",
        "completion_criteria": [
            "Processes a sample CSV without crashing on invalid rows.",
            "Includes at least three automated tests.",
            "Documents setup and usage."
        ]
    },
    "pytorch": {
        "priority": "high",
        "reason": "Useful for implementing and experimenting with deep-learning models.",
        "milestones": [
            "Learn tensors, shapes, and tensor operations.",
            "Build a Dataset and DataLoader for sample data.",
            "Train and evaluate a small neural network."
        ],
        "project": "Train a small classifier on a public or synthetic dataset.",
        "completion_criteria": [
            "Training and evaluation run reproducibly.",
            "Reports a suitable evaluation metric.",
            "Explains the model and its limitations."
        ]
    },
    "tensorflow": {
        "priority": "medium",
        "reason": "A deep-learning framework that may be useful for the researcher's work.",
        "milestones": [
            "Learn tensors and basic model layers.",
            "Build a small Keras model.",
            "Evaluate it on held-out sample data."
        ],
        "project": "Create a small classification model using a public or synthetic dataset.",
        "completion_criteria": [
            "Separates training and evaluation data.",
            "Reports a suitable evaluation metric.",
            "Documents the experiment."
        ]
    },
    "sql": {
        "priority": "medium",
        "reason": "Useful for querying structured experimental or application data.",
        "milestones": [
            "Review SELECT, filtering, sorting, and aggregation.",
            "Practice joins and subqueries.",
            "Design and query a small relational schema."
        ],
        "project": "Build a research-publication database with searchable records.",
        "completion_criteria": [
            "Includes at least three related tables.",
            "Demonstrates joins and aggregate queries.",
            "Uses appropriate primary and foreign keys."
        ]
    },
    "pandas": {
        "priority": "medium",
        "reason": "Helps clean, transform, and analyze tabular research data.",
        "milestones": [
            "Load CSV files into DataFrames.",
            "Practice filtering, missing-value handling, and grouping.",
            "Create a reproducible analysis summary."
        ],
        "project": "Analyze a public dataset and produce a cleaned CSV plus summary report.",
        "completion_criteria": [
            "Handles missing and duplicate values explicitly.",
            "Documents the cleaning decisions.",
            "Produces reproducible summary statistics."
        ]
    },
    "scikit-learn": {
        "priority": "medium",
        "reason": "Useful for traditional machine-learning workflows and evaluation.",
        "milestones": [
            "Learn preprocessing and train/test splits.",
            "Train a baseline classification or regression model.",
            "Evaluate it using suitable metrics."
        ],
        "project": "Build a reproducible baseline ML pipeline on public or synthetic data.",
        "completion_criteria": [
            "Preprocessing is fitted on training data only.",
            "Reports suitable evaluation metrics.",
            "Compares against a simple baseline."
        ]
    },
    "cryptography": {
        "priority": "medium",
        "reason": "Relevant when the research involves secure systems or cryptographic methods.",
        "milestones": [
            "Learn hashing, symmetric encryption, and public-key concepts.",
            "Use a reputable library's documented cryptographic primitives.",
            "Practice key handling and verification in a local demo."
        ],
        "project": "Build a file-integrity checker that compares cryptographic hashes.",
        "completion_criteria": [
            "Detects changes to test files.",
            "Explains the difference between hashing and encryption.",
            "Does not implement custom cryptographic algorithms."
        ]
    },
    "opencv": {
        "priority": "medium",
        "reason": "Useful for image-processing and computer-vision experiments.",
        "milestones": [
            "Load and display images with OpenCV.",
            "Apply resizing, color conversion, and basic filtering.",
            "Measure the effect of a simple image-processing pipeline."
        ],
        "project": "Create an image-processing demo with before-and-after outputs.",
        "completion_criteria": [
            "Processes a small sample image set.",
            "Explains each transformation.",
            "Handles unsupported or unreadable images."
        ]
    }
}


def _generic_plan(skill: str) -> dict[str, Any]:
    """Create a safe starter plan when no skill-specific plan exists."""
    return {
        "priority": "medium",
        "reason": (
            f"{skill} appears in the researcher's listed skills. "
            "Confirm its relevance with the researcher."
        ),
        "milestones": [
            f"Review the fundamentals of {skill}.",
            f"Complete a guided exercise using {skill}.",
            f"Apply {skill} to a small research-related task."
        ],
        "project": (
            f"Build a small, documented demonstration using {skill} "
            "and a public or synthetic dataset where appropriate."
        ),
        "completion_criteria": [
            "The demonstration runs successfully.",
            "The code or workflow is documented.",
            "The results and limitations are explained."
        ]
    }


def generate_readiness_roadmap(
    researcher: dict[str, Any],
    matched_skills: list[str],
    skill_gap: list[str]
) -> dict[str, Any]:
    """Build a roadmap for one researcher using actual recommendation data."""
    gaps = sorted(
        {skill.strip() for skill in skill_gap if skill.strip()},
        key=str.casefold
    )
    matched = sorted(
        {skill.strip() for skill in matched_skills if skill.strip()},
        key=str.casefold
    )

    roadmap_items = []

    for skill in gaps:
        plan = SKILL_PLANS.get(skill.casefold(), _generic_plan(skill))
        roadmap_items.append({
            "skill": skill,
            **plan
        })

    return {
        "researcher": {
            "id": researcher.get("researcher_id", researcher.get("id")),
            "name": researcher.get("name", "Unknown researcher"),
            "department": researcher.get("department")
        },
        "matched_skills": matched,
        "skill_gaps": roadmap_items,
        "total_skill_gaps": len(roadmap_items),
        "message": (
            "Starter roadmap generated from the researcher's listed skills."
            if roadmap_items
            else "No skill gaps were returned for this researcher."
        )
    }
