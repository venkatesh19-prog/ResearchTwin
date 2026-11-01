"""Compatibility ASGI entry point for the canonical authenticated API.

Older local launch commands use ``uvicorn main:app`` from the repository
root. Keep that import path, but route it to the same application used by the
backend deployment instead of exposing the retired CSV-backed API.
"""

from pathlib import Path
import sys


_BACKEND_DIR = str(Path(__file__).resolve().parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.main import app  # noqa: E402,F401
