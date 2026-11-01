"""Integration tests against the shipped model artifact and training data.

The pinned-dependency checks only run when the installed scikit-learn matches
`requirements.txt` (1.7.2); they are skipped in other environments.
"""

import warnings

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn
from sklearn.exceptions import InconsistentVersionWarning

from app.services import recommendation


REFERENCE_ROWS = [
    [0.2, 0.4, 0.3, 0.5, 0.1, 0.6, 0.2],
    [0.8, 0.9, 0.7, 0.6, 1.0, 0.5, 0.9],
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
]

REFERENCE_PROBABILITIES = [
    0.9498304771546008,
    0.9994823667218738,
    0.13463305793573527,
]

PINNED = sklearn.__version__.startswith("1.7.")


def test_training_data_contains_every_model_feature():
    frame = pd.read_csv(recommendation.DATA_PATH)

    for feature in recommendation.EXPECTED_FEATURES:
        assert feature in frame.columns

    assert "department_match" not in recommendation.EXPECTED_FEATURES
    assert "relevance_label" in frame.columns
    assert set(frame["relevance_label"].unique()) <= {0, 1}


def test_real_model_probabilities_are_stable():
    bundle = recommendation.load_model()
    model = bundle["model"]

    frame = pd.DataFrame(REFERENCE_ROWS, columns=bundle["features"])
    probabilities = model.predict_proba(frame)[:, 1]

    np.testing.assert_allclose(
        probabilities, REFERENCE_PROBABILITIES, atol=1e-6
    )

    repeated = model.predict_proba(frame)[:, 1]
    np.testing.assert_array_equal(probabilities, repeated)


def test_real_model_probabilities_are_bounded():
    bundle = recommendation.load_model()
    frame = pd.DataFrame(REFERENCE_ROWS, columns=bundle["features"])

    probabilities = bundle["model"].predict_proba(frame)[:, 1]

    assert probabilities.shape == (len(REFERENCE_ROWS),)
    assert np.all(probabilities >= 0.0)
    assert np.all(probabilities <= 1.0)


@pytest.mark.skipif(
    not PINNED,
    reason=f"pinned production scikit-learn is 1.7.x; found {sklearn.__version__}",
)
def test_artifact_loads_without_version_warning_under_pinned_sklearn():
    recommendation._model_bundle = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        recommendation.load_model()

    version_warnings = [
        warning
        for warning in caught
        if isinstance(warning.message, InconsistentVersionWarning)
    ]
    assert version_warnings == []


@pytest.mark.skipif(
    not PINNED,
    reason=f"pinned production scikit-learn is 1.7.x; found {sklearn.__version__}",
)
def test_pinned_versions_match_requirements():
    import shap

    assert sklearn.__version__ == "1.7.2"
    assert joblib.__version__ == "1.6.0"
    assert shap.__version__ == "0.51.0"
    assert pd.__version__ == "2.3.3"
