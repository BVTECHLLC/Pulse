"""v0.44 Prospecting — Google Places lead discovery → scored CRM contacts.

Ported from the Command Center's prospect_scraper. Finds real businesses in a
target market + industry via the Google Places API, scores each on MSP-readiness
(0-100), and creates CRM contacts (deduped). Google's host is fixed
(maps.googleapis.com) so there's no SSRF surface; the API key lives in the
secure vault.

`run(db, client, market, industry, max_results, user_id)` takes any object with
`text_search` + `place_details`, so the scoring/dedup path is unit-testable with
a fake client (no network / no key).
"""
from __future__ import annotations

import json
from urllib import parse
from urllib import request as urlrequest

from sqlalchemy.orm import Session

from ..models import CrmContact

MARKETS = {
    "austin": {"name": "Austin", "lat": 30.2672, "lng": -97.7431, "radius": 40000},
    "san_antonio": {"name": "San Antonio", "lat": 29.4241, "lng": -98.4936, "radius": 40000},
    "houston": {"name": "Houston", "lat": 29.7604, "lng": -95.3698, "radius": 50000},
    "el_campo": {"name": "El Campo", "lat": 29.1972, "lng": -96.2697, "radius": 30000},
}

# Industry → MSP-readiness boost (compliance/data-heavy verticals convert best).
INDUSTRIES = [
    {"query": "law firm", "industry": "Law Firms", "boost": 22},
    {"query": "medical office", "industry": "Medical Offices", "boost": 20},
    {"query": "dental office", "industry": "Dental Practices", "boost": 18},
    {"query": "accounting firm", "industry": "Accounting / CPA", "boost": 18},
    {"query": "financial advisor", "industry": "Financial Advisors", "boost": 17},
    {"query": "insurance agency", "industry": "Insurance", "boost": 15},
    {"query": "property management company", "industry": "Property Management", "boost": 15},
    {"query": "architecture firm", "industry": "Architecture", "boost": 14},
    {"query": "engineering firm", "industry": "Engineering", "boost": 14},
    {"query": "real estate agency", "industry": "Real Estate", "boost": 13},
    {"query": "marketing agency", "industry": "Marketing Agencies", "boost": 12},
    {"query": "manufacturing company", "industry": "Manufacturing", "boost": 11},
    {"query": "construction company", "industry": "Construction", "boost": 10},
]
_INDUSTRY_BY_QUERY = {i["query"]: i for i in INDUSTRIES}


class ProspectingError(Exception):
    pass


class PlacesClient:
    """Thin Google Places client (Text Search + Details)."""

    BASE = "https://maps.googleapis.com/maps/api/place"

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ProspectingError("Google API key is not configured")

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        url = f"{self.BASE}/{path}?{parse.urlencode(params)}"
        try:
            with urlrequest.urlopen(url, timeout=30) as r:
                data = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            raise ProspectingError(f"Google Places request failed: {e}")
        st = data.get("status")
        if st not in ("OK", "ZERO_RESULTS"):
            raise ProspectingError(f"Google Places error: {st} {data.get('error_message','')}".strip())
        return data

    def text_search(self, query: str, lat: float, lng: float, radius: int) -> list[dict]:
        data = self._get("textsearch/json", {
            "query": query, "location": f"{lat},{lng}", "radius": radius,
        })
        return data.get("results", [])

    def place_details(self, place_id: str) -> dict:
        data = self._get("details/json", {
            "place_id": place_id,
            "fields": "name,formatted_phone_number,website,formatted_address,business_status,rating,user_ratings_total",
        })
        return data.get("result", {})


def score_prospect(place: dict, details: dict, boost: int = 0) -> int:
    """0-100 MSP-readiness score."""
    score = 30
    if details.get("formatted_phone_number"):
        score += 15
    if details.get("website"):
        score += 10
    rating = place.get("rating") or details.get("rating") or 0
    if rating >= 4.5:
        score += 8
    elif rating >= 4.0:
        score += 5
    elif rating >= 3.5:
        score += 3
    reviews = place.get("user_ratings_total") or 0
    if reviews >= 100:
        score += 10
    elif reviews >= 50:
        score += 7
    elif reviews >= 20:
        score += 4
    elif reviews >= 5:
        score += 2
    if place.get("business_status") == "OPERATIONAL":
        score += 5
    return min(100, score + boost)


def run(db: Session, client, market: str, industry_query: str, max_results: int = 20,
        user_id: int | None = None) -> dict:
    """Search → score → create CRM contacts (deduped by company+market). Commits."""
    mk = MARKETS.get(market)
    if not mk:
        raise ProspectingError(f"unknown market '{market}' (choose: {', '.join(MARKETS)})")
    meta = _INDUSTRY_BY_QUERY.get(industry_query, {"industry": industry_query, "boost": 0})
    results = client.text_search(industry_query, mk["lat"], mk["lng"], mk["radius"])

    created, skipped, samples = 0, 0, []
    for place in results[: max(1, min(max_results, 60))]:
        name = (place.get("name") or "").strip()
        if not name:
            continue
        # Dedup: same company already in this market.
        exists = (db.query(CrmContact)
                  .filter(CrmContact.company == name, CrmContact.market == market).first())
        if exists:
            skipped += 1
            continue
        details = {}
        pid = place.get("place_id")
        if pid:
            try:
                details = client.place_details(pid)
            except ProspectingError:
                details = {}
        score = score_prospect(place, details, meta["boost"])
        contact = CrmContact(
            name=name, company=name,
            phone=details.get("formatted_phone_number"),
            website=details.get("website"),
            address=details.get("formatted_address") or place.get("formatted_address"),
            source="scrape", status="new", score=score, market=market,
            tags=[meta["industry"]], owner_user_id=user_id,
        )
        db.add(contact)
        created += 1
        if len(samples) < 10:
            samples.append({"name": name, "score": score, "phone": contact.phone})
    db.commit()
    return {"market": market, "industry": meta["industry"], "found": len(results),
            "created": created, "skipped_existing": skipped, "samples": samples}
