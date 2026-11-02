"""Download the ONNX MiniLM embedding model used by semantic matching.

Run from backend/: python scripts/fetch_embedding_model.py
Render runs this during the build so the image ships the model files.
"""

import hashlib
import http.client
import time
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "all-MiniLM-L6-v2-onnx"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
BASE_URL = (
    "https://huggingface.co/sentence-transformers/"
    f"all-MiniLM-L6-v2/resolve/{REVISION}/"
)
TIMEOUT_SECONDS = 60
ATTEMPTS = 3
FILES = {
    "onnx/model.onnx": (
        "model.onnx",
        "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",
    ),
    "tokenizer.json": (
        "tokenizer.json",
        "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
    ),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url, target):
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        with target.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)


def fetch(remote, name, expected):
    target = MODEL_DIR / name

    if target.exists() and digest(target) == expected:
        print(f"{name}: already present")
        return

    if target.exists():
        target.unlink()

    for attempt in range(1, ATTEMPTS + 1):
        print(f"{name}: downloading (attempt {attempt}/{ATTEMPTS})")

        try:
            download(BASE_URL + remote, target)
        except (OSError, http.client.HTTPException) as exc:
            target.unlink(missing_ok=True)
            error = f"download failed: {exc}"
        else:
            if digest(target) == expected:
                return
            target.unlink()
            error = "SHA-256 mismatch"

        if attempt == ATTEMPTS:
            raise SystemExit(
                f"{name}: {error} after {ATTEMPTS} attempts; rejected"
            )
        time.sleep(attempt)


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    for remote, (name, expected) in FILES.items():
        fetch(remote, name, expected)


if __name__ == "__main__":
    main()
