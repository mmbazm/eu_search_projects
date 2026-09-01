"""
EU Project Search - Backend API

Calls the EU "SEDIA" search API, then reshapes the (very verbose) response
into a compact structure the frontend can consume directly:

{
  "results": {
    "projects": [
      {
        "id": "...",
        "title": "...",
        "summary": "...",
        "url": "...",
        "participants": [
          {
            "legalName": "...",
            "city": "...",
            "country": "...",
            "role": "coordinator" | "participant" | ...,
            "latitude": 40.48,
            "longitude": -3.66
          }
        ]
      }
    ]
  }
}

`latitude`/`longitude` are included in addition to the originally requested
fields (legalName, city, country) because the source data already contains
them and they're what let the frontend actually place a pin on a map -
geocoding city/country names would be slower and less reliable.
"""

import asyncio
import json
import logging
import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eu-search-backend")

EU_API_BASE_URL = os.getenv(
    "EU_API_BASE_URL",
    "https://api.tech.ec.europa.eu/search-api/prod/rest/search",
)
EU_API_KEY = os.getenv("EU_API_KEY", "SEDIA_NONH2020_PROD")
REQUEST_TIMEOUT = float(os.getenv("EU_API_TIMEOUT", "60"))
EU_API_PAGE_SIZE = int(os.getenv("EU_API_PAGE_SIZE", "100"))
# Safety cap so one very broad keyword can't page forever; raise via env var
# if you legitimately need more than this per keyword.
EU_API_MAX_RESULTS_PER_KEYWORD = int(os.getenv("EU_API_MAX_RESULTS_PER_KEYWORD", "10000"))

app = FastAPI(title="EU Project Search API", version="1.0.0")

# Not strictly required (the frontend calls this server-side), but kept so
# the API can also be called directly from a browser-based frontend later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Participant(BaseModel):
    legalName: str
    city: Optional[str] = None
    country: Optional[str] = None
    countryCode: Optional[str] = None
    role: Optional[str] = None
    website: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    eu_contribution: Optional[str] = None


class Project(BaseModel):
    id: Optional[str] = None
    title: str
    summary: Optional[str] = None
    acronym: Optional[str] = None
    url: Optional[str] = None
    participants: list[Participant] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    overall_budget: Optional[str] = None
    eu_contribution_amount: Optional[str] = None


class ProjectsPayload(BaseModel):
    projects: list[Project]


class SearchResponse(BaseModel):
    results: ProjectsPayload
    warnings: list[str] = []


def _first(values: Optional[list], default: Optional[str] = None) -> Optional[str]:
    if values and isinstance(values, list) and len(values) > 0:
        return values[0]
    return default


def _date_only(value: Optional[str]) -> Optional[str]:
    """
    Trims a full ISO-8601 timestamp like '2026-09-01T00:00:00.000+0100' down
    to just the date part ('2026-09-01'). Project start/end dates from this
    API always carry a midnight timestamp + timezone offset that has no real
    meaning here, so it's dropped rather than displayed.
    """
    if not value:
        return None
    return str(value).split("T", 1)[0] or None


def _parse_participants(raw_participants: Optional[list]) -> list[Participant]:
    """
    metadata.participants is normally a one-element list, and that single
    element is itself a JSON-encoded string containing an array of
    participant objects. Handles missing / malformed data defensively so
    one bad project never fails the whole search request.
    """
    parsed: list[Participant] = []
    if not raw_participants:
        return parsed

    for entry in raw_participants:
        items = entry
        if isinstance(entry, str):
            try:
                items = json.loads(entry)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Could not parse participants JSON string - skipping")
                continue
        if not isinstance(items, list):
            continue

        for p in items:
            if not isinstance(p, dict):
                continue

            legal_name = p.get("legalName") or "Unknown"
            postal = p.get("postalAddress") or {}
            city = postal.get("city")
            country_info = postal.get("countryCode") or {}
            country = country_info.get("description") or country_info.get("abbreviation")
            country_code = country_info.get("abbreviation")

            lat, lon = p.get("latitude"), p.get("longitude")
            try:
                lat = float(lat) if lat not in (None, "") else None
                lon = float(lon) if lon not in (None, "") else None
            except (TypeError, ValueError):
                lat, lon = None, None

            raw_contribution = p.get("eucontribution")
            try:
                eu_contribution = (
                    str(raw_contribution) if raw_contribution not in (None, "") else None
                )
            except (TypeError, ValueError):
                eu_contribution = None

            parsed.append(
                Participant(
                    legalName=legal_name,
                    city=city,
                    country=country,
                    countryCode=country_code,
                    role=p.get("role"),
                    website=p.get("webLink") or None,
                    latitude=lat,
                    longitude=lon,
                    eu_contribution=eu_contribution
                )
            )
    return parsed


def transform_response(raw: dict) -> SearchResponse:
    # The search API indexes several documents per project (the project
    # record itself, its deliverables, its reports, ...), so the same
    # project can legitimately appear many times in raw "results". Dedupe
    # by project id (falling back to title when the id is missing) and
    # merge instead of listing each match separately. Relies on dict
    # preserving insertion order (Python 3.7+) to keep first-seen ordering.
    projects_by_key: dict[str, Project] = {}

    for item in raw.get("results", []) or []:
        metadata = item.get("metadata") or {}

        title = _first(metadata.get("title")) or item.get("reference") or "Untitled project"
        summary = item.get("summary") or _first(metadata.get("summaries"))
        project_id = _first(metadata.get("projectId"))
        url = item.get("url") or _first(metadata.get("url"))
        acronym = _first(metadata.get("acronym"))
        start_date = _date_only(_first(metadata.get("startDate")))
        end_date = _date_only(_first(metadata.get("endDate")))
        participants = _parse_participants(metadata.get("participants"))
        status = _first(metadata.get("status"))
        overall_budget = _first(metadata.get("overallBudget") or metadata.get("euContributionAmount"))
        eu_contribution_amount = _first(metadata.get("euContributionAmount"))

        key = project_id or title

        if key not in projects_by_key:
            projects_by_key[key] = Project(
                id=project_id,
                title=title,
                summary=summary,
                acronym=acronym,
                url=url,
                participants=participants,
                start_date=start_date,
                end_date=end_date,
                status=status,
                overall_budget=overall_budget,
                eu_contribution_amount=eu_contribution_amount
            )
        else:
            existing = projects_by_key[key]
            if not existing.summary and summary:
                existing.summary = summary
            if not existing.url and url:
                existing.url = url
            if not existing.acronym and acronym:
                existing.acronym = acronym
            if not existing.start_date and start_date:
                existing.start_date = start_date
            if not existing.end_date and end_date:
                existing.end_date = end_date
            if not existing.status and status:
                existing.status = status
            if not existing.overall_budget and overall_budget:
                existing.overall_budget = overall_budget
            if not existing.eu_contribution_amount and eu_contribution_amount:
                existing.eu_contribution_amount = eu_contribution_amount
            seen = {(p.legalName, p.city, p.country) for p in existing.participants}
            for p in participants:
                p_key = (p.legalName, p.city, p.country)
                if p_key not in seen:
                    existing.participants.append(p)
                    seen.add(p_key)

    return SearchResponse(results=ProjectsPayload(projects=list(projects_by_key.values())))

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


async def _fetch_one_keyword(
    client: httpx.AsyncClient,
    keyword: str,
) -> tuple[list[dict], Optional[str]]:
    """
    Fetches all available pages for a single keyword from the EU API.

    - Uses POST with query-string parameters (as required by this EU endpoint).
    - Paginates until:
        * no more results are returned, or
        * accumulated results >= totalResults, or
        * a safety cap (EU_API_MAX_RESULTS_PER_KEYWORD) is hit.
    - On any error, returns whatever was successfully fetched so far plus
      an error message, instead of raising.

    Returns:
        (raw_results, error_message)
        - raw_results: list of raw result dicts fetched for this keyword
        - error_message: None if everything went fine, otherwise a string
    """
    all_results: list[dict] = []
    page_number = 1
    error: Optional[str] = None

    while True:
        params = {
            "apiKey": EU_API_KEY,
            "text": keyword,
            "pageSize": EU_API_PAGE_SIZE,
            "pageNumber": page_number,
        }

        try:
            # POST required, but parameters are sent in the query string
            resp = await client.post(EU_API_BASE_URL, params=params)
        except httpx.RequestError as exc:
            logger.exception(
                "Error contacting EU search API for keyword %r (page %d)",
                keyword,
                page_number,
            )
            error = f"Could not reach EU search API for '{keyword}': {exc}"
            # Return whatever we have so far
            return all_results, error

        if resp.status_code != 200:
            logger.error(
                "EU search API returned non-200 for keyword %r (page %d): %s",
                keyword,
                page_number,
                resp.status_code,
            )
            error = f"EU search API returned an error for '{keyword}': {resp.text[:300]}"
            # Still return what we managed to fetch before this failure
            return all_results, error

        try:
            data = resp.json()
        except ValueError:
            logger.exception("EU search API returned invalid JSON for keyword %r", keyword)
            error = f"EU search API returned invalid JSON for '{keyword}'"
            return all_results, error

        page_results = data.get("results") or []
        if page_results:
            all_results.extend(page_results)

        total_results = data.get("totalResults")

        # Log progress for debugging
        logger.info(
            "Keyword %r page %d: %d new results, totalResults=%s, accumulated=%d, cap=%d",
            keyword,
            page_number,
            len(page_results),
            total_results,
            len(all_results),
            EU_API_MAX_RESULTS_PER_KEYWORD,
        )

        # Decide whether to stop pagination
        reached_total = (
            isinstance(total_results, (int, float)) and len(all_results) >= total_results
        )
        hit_safety_cap = len(all_results) >= EU_API_MAX_RESULTS_PER_KEYWORD

        if not page_results or reached_total or hit_safety_cap:
            if hit_safety_cap:
                logger.warning(
                    "Hit EU_API_MAX_RESULTS_PER_KEYWORD cap for keyword %r after %d results",
                    keyword,
                    len(all_results),
                )
            break

        page_number += 1

    return all_results, error

@app.get("/api/search", response_model=SearchResponse)
async def search(
    text: str = Query(
        ...,
        min_length=1,
        description="One keyword, or several separated by commas, e.g. 'telco,5G,edge computing'",
    ),
) -> SearchResponse:
    keywords = [k.strip() for k in text.split(",") if k.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="No valid search keywords provided")

    # Each keyword is queried separately (rather than joined into one string)
    # so results don't depend on undocumented AND/OR query-syntax behaviour
    # on the EU API's side. Results across all keywords are then merged and
    # deduped by project, same as duplicate matches within a single keyword.
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        fetched = await asyncio.gather(*(_fetch_one_keyword(client, kw) for kw in keywords))

    combined_raw_results: list[dict] = []
    warnings: list[str] = []
    for raw_results, error in fetched:
        # Always keep whatever was fetched, even if a later page for this
        # keyword failed - partial results are still better than none.
        combined_raw_results.extend(raw_results)
        if error:
            warnings.append(error)

    if not combined_raw_results and warnings:
        raise HTTPException(status_code=502, detail="; ".join(warnings))

    response = transform_response({"results": combined_raw_results})
    response.warnings = warnings

    return response
