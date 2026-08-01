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
    "sugar_land": {"name": "Sugar Land", "lat": 29.6197, "lng": -95.6349, "radius": 35000},
    # v1.88: widen the net across Texas so the tank never runs dry and the same
    # metro isn't hit every rotation.
    "new_braunfels": {"name": "New Braunfels", "lat": 29.7030, "lng": -98.1245, "radius": 30000},
    "the_woodlands": {"name": "The Woodlands", "lat": 30.1658, "lng": -95.4613, "radius": 30000},
    "round_rock": {"name": "Round Rock", "lat": 30.5083, "lng": -97.6789, "radius": 30000},
    "dallas": {"name": "Dallas", "lat": 32.7767, "lng": -96.7970, "radius": 45000},
    "fort_worth": {"name": "Fort Worth", "lat": 32.7555, "lng": -97.3308, "radius": 40000},
    "corpus_christi": {"name": "Corpus Christi", "lat": 27.8006, "lng": -97.3964, "radius": 35000},
    "waco": {"name": "Waco", "lat": 31.5493, "lng": -97.1467, "radius": 35000},
    "el_campo": {"name": "El Campo", "lat": 29.1966, "lng": -96.2697, "radius": 45000},
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
    # v1.88: more MSP-ready verticals (compliance / data-heavy, book-of-business).
    {"query": "veterinary clinic", "industry": "Veterinary", "boost": 13},
    {"query": "chiropractor", "industry": "Chiropractic", "boost": 12},
    {"query": "optometrist", "industry": "Optometry", "boost": 13},
    {"query": "physical therapy", "industry": "Physical Therapy", "boost": 12},
    {"query": "title company", "industry": "Title / Escrow", "boost": 16},
    {"query": "credit union", "industry": "Credit Unions", "boost": 16},
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


# --------------------------------------------------------------------------- #
# FREE lead source (v1.78) — OpenStreetMap Overpass. No API key, no billing, no
# quota card. It returns real local businesses (with website/phone/email tags)
# by category within a radius, shaped to the SAME text_search/place_details
# interface as PlacesClient so the whole scrape→score→enrich→email pipeline is
# reused unchanged. When a Google Places key IS configured, the engine still
# prefers it (richer ratings/reviews); this is the zero-cost default so the lead
# tank fills — and cold email actually goes out — with no paid API at all.
# Host is fixed (overpass-api.de) so there's no SSRF surface, same as Places.
# --------------------------------------------------------------------------- #
# Industry query -> OpenStreetMap tag selectors. Businesses are tagged in OSM
# under office=/amenity=/craft=/shop=; we cast a couple of nets per vertical.
OSM_SELECTORS: dict[str, list[str]] = {
    "law firm": ['["office"="lawyer"]'],
    "medical office": ['["amenity"="doctors"]', '["healthcare"="clinic"]'],
    "dental office": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
    "accounting firm": ['["office"="accountant"]', '["office"="tax_advisor"]'],
    "financial advisor": ['["office"="financial"]', '["office"="financial_advisor"]'],
    "insurance agency": ['["office"="insurance"]'],
    "property management company": ['["office"="property_management"]',
                                    '["office"="estate_agent"]'],
    "architecture firm": ['["office"="architect"]'],
    "engineering firm": ['["office"="engineer"]', '["office"="engineering"]'],
    "real estate agency": ['["office"="estate_agent"]'],
    "marketing agency": ['["office"="advertising_agency"]', '["office"="it"]'],
    "manufacturing company": ['["office"="company"]', '["craft"="metal_construction"]'],
    "construction company": ['["craft"="builder"]', '["office"="construction_company"]'],
    "veterinary clinic": ['["amenity"="veterinary"]'],
    "chiropractor": ['["healthcare"="chiropractor"]', '["healthcare:speciality"="chiropractic"]'],
    "optometrist": ['["shop"="optician"]', '["healthcare"="optometrist"]'],
    "physical therapy": ['["healthcare"="physiotherapist"]'],
    "title company": ['["office"="company"]', '["office"="notary"]'],
    "credit union": ['["amenity"="bank"]'],
}
_OSM_DEFAULT_SELECTORS = ['["office"="company"]']


def _osm_clean_url(url: str | None) -> str | None:
    u = (url or "").strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def _osm_address(tags: dict) -> str | None:
    """Assemble a human address from addr:* tags (best-effort)."""
    hn, street = tags.get("addr:housenumber"), tags.get("addr:street")
    line1 = " ".join(p for p in (hn, street) if p)
    city = tags.get("addr:city")
    st = tags.get("addr:state")
    pc = tags.get("addr:postcode")
    tail = " ".join(p for p in (st, pc) if p)
    parts = [p for p in (line1, city, tail) if p]
    return ", ".join(parts) or None


class OverpassClient:
    """Free OpenStreetMap business finder, PlacesClient-compatible (no key)."""

    ENDPOINT = "https://overpass-api.de/api/interpreter"

    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint or self.ENDPOINT
        self._by_id: dict[str, dict] = {}

    def _post(self, query: str) -> dict:
        body = parse.urlencode({"data": query}).encode()
        req = urlrequest.Request(self.endpoint, data=body, headers={
            "User-Agent": "BVTech-Pulse/1.0 (+https://bvtech.org)",
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlrequest.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            raise ProspectingError(f"Overpass request failed: {e}")

    def text_search(self, query: str, lat: float, lng: float, radius: int) -> list[dict]:
        selectors = OSM_SELECTORS.get(query, _OSM_DEFAULT_SELECTORS)
        blocks = []
        for sel in selectors:
            for typ in ("node", "way"):
                blocks.append(f'{typ}{sel}(around:{int(radius)},{lat},{lng});')
        q = f"[out:json][timeout:25];({''.join(blocks)});out center tags 80;"
        data = self._post(q)
        results: list[dict] = []
        for el in data.get("elements", []):
            tags = el.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue
            website = _osm_clean_url(tags.get("website") or tags.get("contact:website")
                                     or tags.get("url"))
            email = (tags.get("email") or tags.get("contact:email") or "").strip().lower() or None
            # Must be reachable: a website to scrape an email from, or a listed email.
            if not (website or email):
                continue
            phone = tags.get("phone") or tags.get("contact:phone")
            addr = _osm_address(tags)
            pid = f"osm/{el.get('type')}/{el.get('id')}"
            self._by_id[pid] = {
                "website": website, "formatted_phone_number": phone,
                "formatted_address": addr, "email": email,
                "business_status": "OPERATIONAL",
            }
            results.append({"name": name, "place_id": pid,
                            "business_status": "OPERATIONAL",
                            "formatted_address": addr})
        return results

    def place_details(self, place_id: str) -> dict:
        return self._by_id.get(place_id, {})


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
        # v1.59: keep the human-relevant facts — the outreach personalizer turns
        # "Google rating 4.8 (212 reviews)" into a specific, warm first line.
        rating = place.get("rating") or details.get("rating")
        reviews = place.get("user_ratings_total")
        facts = (f"Google rating {rating} ({reviews} reviews)"
                 if rating and reviews else (f"Google rating {rating}" if rating else None))
        contact = CrmContact(
            name=name, company=name,
            # Free OSM source sometimes lists a public email directly -> instantly
            # emailable, no website scrape needed. Places never sets this (stays None).
            email=(details.get("email") or None),
            phone=details.get("formatted_phone_number"),
            website=details.get("website"),
            address=details.get("formatted_address") or place.get("formatted_address"),
            source="scrape", status="new", score=score, market=market,
            tags=[meta["industry"]], notes=facts, owner_user_id=user_id,
        )
        db.add(contact)
        created += 1
        if len(samples) < 10:
            samples.append({"name": name, "score": score, "phone": contact.phone})
    db.commit()
    return {"market": market, "industry": meta["industry"], "found": len(results),
            "created": created, "skipped_existing": skipped, "samples": samples}
