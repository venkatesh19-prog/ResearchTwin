"""Validate and atomically import the bundled researcher CSV."""

import csv
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import Researcher

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 2000
TEXT_LIMITS = {
    "name": 100,
    "department": 150,
    "designation": 100,
    "research_areas": 10000,
    "expertise": 10000,
    "skills": 10000,
    "publications": 20000,
    "projects": 20000,
    "profile_url": 300,
}
ALLOWED_COLUMNS = frozenset((*TEXT_LIMITS, "experience"))


class ResearcherImportError(ValueError):
    """The import source is not a valid researcher CSV."""


def _parse_row(row: dict, row_number: int) -> dict | None:
    if None in row:
        raise ResearcherImportError(f"Row {row_number} has extra values")

    values = {key: (value or "").strip() for key, value in row.items()}
    if not any(values.values()):
        return None

    name = values.get("name", "")
    if not name:
        raise ResearcherImportError(f"Row {row_number} has no researcher name")

    record = {"name": name}
    for field, limit in TEXT_LIMITS.items():
        if field == "name":
            continue
        value = values.get(field, "")
        if len(value) > limit:
            raise ResearcherImportError(f"Row {row_number} has an oversized {field}")
        record[field] = value or None

    if len(name) > TEXT_LIMITS["name"]:
        raise ResearcherImportError(f"Row {row_number} has an oversized name")

    raw_experience = values.get("experience", "")
    if raw_experience:
        try:
            experience = int(raw_experience)
        except ValueError as exc:
            raise ResearcherImportError(
                f"Row {row_number} has invalid experience"
            ) from exc
        if not 0 <= experience <= 80:
            raise ResearcherImportError(f"Row {row_number} has invalid experience")
        record["experience"] = experience
    else:
        record["experience"] = None

    profile_url = record.get("profile_url")
    if profile_url:
        parsed = urlparse(profile_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ResearcherImportError(f"Row {row_number} has an invalid profile URL")

    return record


def _read_records(path: Path) -> list[Researcher]:
    if path.suffix.lower() != ".csv":
        raise ResearcherImportError("Import source must be a CSV file")
    if not path.is_file():
        raise FileNotFoundError(path.name)
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ResearcherImportError("Import file exceeds the size limit")

    records = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            headers = reader.fieldnames
            if not headers:
                raise ResearcherImportError("Import file has no header row")

            headers = [header.strip() if header else "" for header in headers]
            if any(not header for header in headers) or len(set(headers)) != len(headers):
                raise ResearcherImportError("Import file has invalid column names")
            if "name" not in headers or not set(headers) <= ALLOWED_COLUMNS:
                raise ResearcherImportError("Import file has an unsupported schema")

            reader.fieldnames = headers
            for row_number, row in enumerate(reader, start=2):
                record = _parse_row(row, row_number)
                if record is None:
                    continue
                records.append(Researcher(**record))
                if len(records) > MAX_IMPORT_ROWS:
                    raise ResearcherImportError("Import file contains too many rows")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ResearcherImportError("Import file is not valid UTF-8 CSV") from exc

    if not records:
        raise ResearcherImportError("Import file contains no researcher rows")
    return records


def import_researchers(csv_path: str, db: Session) -> int:
    """Import missing name/department pairs without changing existing records.

    The complete file is validated before any writes. Repeated rows in the CSV
    and records already present in the directory are skipped, making repeated
    sequential imports idempotent.
    """
    records = _read_records(Path(csv_path))
    existing_keys = {
        (
            (name or "").strip().casefold(),
            (department or "").strip().casefold(),
        )
        for name, department in db.query(
            Researcher.name, Researcher.department
        ).yield_per(1000)
    }
    to_insert = []
    for record in records:
        key = (
            (record.name or "").strip().casefold(),
            (record.department or "").strip().casefold(),
        )
        if key in existing_keys:
            continue
        existing_keys.add(key)
        to_insert.append(record)

    try:
        if to_insert:
            db.add_all(to_insert)
            db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(to_insert)
