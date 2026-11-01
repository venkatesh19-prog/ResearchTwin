"""Compatibility import path for validated researcher CSV ingestion."""

from .services.researcher_import import ResearcherImportError, import_researchers

__all__ = ["ResearcherImportError", "import_researchers"]
