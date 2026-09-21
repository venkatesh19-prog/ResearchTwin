from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer


def build_tfidf_features(
    documents: List[str],
    max_features: int = 500
):
    """
    Convert researcher text documents into TF-IDF vectors.

    Parameters
    ----------
    documents:
        List of researcher profile texts.

    max_features:
        Maximum number of vocabulary features.

    Returns
    -------
    vectorizer:
        Fitted TF-IDF vectorizer.

    matrix:
        TF-IDF feature matrix.
    """

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        max_features=max_features
    )

    matrix = vectorizer.fit_transform(documents)

    return vectorizer, matrix


def get_feature_names(vectorizer):
    """
    Return the vocabulary learned by TF-IDF.
    """

    return vectorizer.get_feature_names_out().tolist()