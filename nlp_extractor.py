import re
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer


def clean_text(text: str) -> str:
    """Cleans and normalizes input text."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'[^a-zA-Z0-9\s,]', ' ', text)
    return " ".join(text.split())


def extract_keywords_nlp(text: str, top_n: int = 5) -> List[str]:
    """Uses TF-IDF to extract dominant terms from profile text."""
    cleaned = clean_text(text)
    if not cleaned or len(cleaned.split()) < 3:
        return [w.title() for w in cleaned.split(',') if w.strip()]

    try:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=top_n)
        vectorizer.fit_transform([cleaned])
        feature_names = vectorizer.get_feature_names_out()
        return [f.title() for f in feature_names]
    except Exception:
        return [w.title() for w in cleaned.split()[:top_n]]