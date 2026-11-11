"""Optional free external funding sources.

The only built-in adapter is the public Grants.gov search API. It is disabled
unless ``FUNDING_GRANTS_GOV_ENABLED`` is set, keeps no credentials, and maps
only fields that the source actually returned. Imported records are created as
drafts for administrator review; empty fields are never invented.
"""

import calendar
import json
import os
import urllib.request
from datetime import datetime

ENABLED_ENV = "FUNDING_GRANTS_GOV_ENABLED"
SOURCE_NAME = "grants_gov"
SEARCH_URL = "https://api.grants.gov/v1/api/search2"
TIMEOUT_SECONDS = 8

_TRUE_VALUES = {"1", "true", "yes", "on"}


class FundingSourceError(Exception):
    """Raised when an external source is disabled or cannot be reached."""


def is_enabled() -> bool:
    return os.getenv(ENABLED_ENV, "").strip().lower() in _TRUE_VALUES


def sources_payload() -> dict:
    return {
        "sources": [
            {
                "name": SOURCE_NAME,
                "enabled": is_enabled(),
                "description": (
                    "Grants.gov public opportunity search; imports are "
                    "created as drafts for administrator review."
                ),
            }
        ]
    }


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _epoch(value) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return int(calendar.timegm(parsed.timetuple()))
    return None


def _map_hit(hit) -> dict | None:
    """Map one Grants.gov hit, dropping records that lack an id or title."""
    if not isinstance(hit, dict):
        return None
    external_id = _clean(hit.get("id") or hit.get("number"))
    title = _clean(hit.get("title"))
    if not external_id or not title:
        return None

    url = _clean(hit.get("link") or hit.get("url"))
    if url and not url.startswith(("http://", "https://")):
        url = ""

    return {
        "external_source": SOURCE_NAME,
        "external_id": external_id,
        "title": title,
        "description": _clean(hit.get("synopsis") or hit.get("description")),
        "organization": _clean(hit.get("agencyName") or hit.get("agency")),
        "location": _clean(hit.get("location")),
        "url": url,
        "deadline_at": _epoch(hit.get("closeDate") or hit.get("close_date")),
        "required_skills": "",
        "required_research_areas": "",
        "required_expertise": "",
        "eligibility": _clean(
            hit.get("eligibilityDescription") or hit.get("eligibility")
        ),
    }


def fetch(query: str, limit: int) -> list[dict]:
    """Fetch and map live records; raise on any failure instead of faking data."""
    if not is_enabled():
        raise FundingSourceError("Grants.gov funding source is disabled")

    body = json.dumps(
        {
            "keyword": query,
            "oppStatuses": "forecasted|posted",
            "rows": limit,
            "startRecordNum": 0,
            "sortBy": "closeDate",
            "orderBy": "asc",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        SEARCH_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ResearchTwin/2.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except Exception as exc:  # noqa: BLE001 - normalize every transport failure
        raise FundingSourceError(
            "Grants.gov funding source is unavailable"
        ) from exc

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FundingSourceError(
            "Grants.gov funding source returned an invalid response"
        ) from exc

    if not isinstance(parsed, dict):
        raise FundingSourceError("Grants.gov funding source returned no data")
    if parsed.get("errorcode") not in (0, "0", None):
        raise FundingSourceError("Grants.gov funding source returned an error")

    data = parsed.get("data")
    if not isinstance(data, dict):
        raise FundingSourceError("Grants.gov funding source returned no data")
    hits = data.get("oppHits")
    if not isinstance(hits, list):
        raise FundingSourceError(
            "Grants.gov funding source returned an unexpected response"
        )
    records = []
    for hit in hits:
        mapped = _map_hit(hit)
        if mapped is not None:
            records.append(mapped)
    return records[:limit]
