#!/usr/bin/env python3
"""
BVTech MSP Prospect Scraper — Real Business Data
==================================================
Uses Google Places API to find REAL businesses in Austin, Houston,
and San Antonio. Scores them by MSP-readiness and syncs to HubSpot.

FREE: Google gives $200/month in Places API credits (~10K lookups)

SETUP:
1. Get Google API key from console.cloud.google.com
2. Enable "Places API" in your Google Cloud project
3. Paste key below or set GOOGLE_API_KEY env variable
4. Optional: Add HubSpot token for auto-sync

USAGE:
    python prospect_scraper.py                          # Scrape all markets + industries
    python prospect_scraper.py --market austin          # Single market
    python prospect_scraper.py --industry "law firm"    # Single industry
    python prospect_scraper.py --sync                   # Also sync to HubSpot
    python prospect_scraper.py --max 100                # Limit total results
"""

import json
import csv
import time
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install: pip install requests")
    sys.exit(1)


# ============================================================
# CONFIGURATION
# ============================================================
CONFIG = {
    "google_api_key": os.getenv("GOOGLE_API_KEY", "YOUR_GOOGLE_API_KEY"),
    "hubspot_token": os.getenv("HUBSPOT_TOKEN", "YOUR_HUBSPOT_TOKEN"),

    # Output files
    "output_csv": "prospects.csv",
    "sms_csv": "sms_prospects.csv",
    "raw_json": "raw_places_data.json",
}

# Bridge: Load API keys from GUI settings file (bvtech_config.json)
_gui_config_path = Path("bvtech_config.json")
if _gui_config_path.exists():
    try:
        with open(_gui_config_path, "r") as _f:
            _gui = json.load(_f)
            if _gui.get("google_api_key"):
                CONFIG["google_api_key"] = _gui["google_api_key"]
            if _gui.get("hubspot_token"):
                CONFIG["hubspot_token"] = _gui["hubspot_token"]
    except Exception:
        pass

# Texas MSP target markets with coordinates for Places API
MARKETS = {
    "austin": {
        "name": "Austin",
        "lat": 30.2672,
        "lng": -97.7431,
        "radius": 40000,  # 40km (~25 miles)
    },
    "san_antonio": {
        "name": "San Antonio",
        "lat": 29.4241,
        "lng": -98.4936,
        "radius": 40000,
    },
    "houston": {
        "name": "Houston",
        "lat": 29.7604,
        "lng": -95.3698,
        "radius": 50000,  # Larger — Houston is huge
    },
}

# Industries to search — ranked by MSP-readiness
# Tier 1 (highest need): Compliance-heavy, data-sensitive
# Tier 2 (high need): Tech-dependent, multi-user
# Tier 3 (medium need): Growing, some IT needs
SEARCH_QUERIES = [
    # Tier 1 — Compliance-heavy, highest MSP conversion rates
    {"query": "law firm", "industry": "Law Firms", "score_boost": 22},
    {"query": "attorney office", "industry": "Law Firms", "score_boost": 22},
    {"query": "medical office", "industry": "Medical Offices", "score_boost": 20},
    {"query": "dental office", "industry": "Dental Practices", "score_boost": 18},
    {"query": "accounting firm", "industry": "Accounting / CPA", "score_boost": 18},
    {"query": "CPA firm", "industry": "Accounting / CPA", "score_boost": 18},
    {"query": "financial advisor", "industry": "Financial Advisors", "score_boost": 17},

    # Tier 2 — Tech-dependent, good MSP candidates
    {"query": "insurance agency", "industry": "Insurance", "score_boost": 15},
    {"query": "real estate agency", "industry": "Real Estate", "score_boost": 13},
    {"query": "architecture firm", "industry": "Architecture", "score_boost": 14},
    {"query": "engineering firm", "industry": "Engineering", "score_boost": 14},
    {"query": "property management company", "industry": "Property Management", "score_boost": 15},
    {"query": "staffing agency", "industry": "Staffing", "score_boost": 13},
    {"query": "marketing agency", "industry": "Marketing Agencies", "score_boost": 12},

    # Tier 3 — Operational IT needs
    {"query": "construction company", "industry": "Construction", "score_boost": 10},
    {"query": "manufacturing company", "industry": "Manufacturing", "score_boost": 11},
    {"query": "logistics company", "industry": "Logistics / Freight", "score_boost": 10},
    {"query": "oil and gas company", "industry": "Oil & Gas", "score_boost": 11},
    {"query": "auto dealership", "industry": "Auto Dealers", "score_boost": 9},
    {"query": "veterinary clinic", "industry": "Veterinary Clinics", "score_boost": 10},
]


# ============================================================
# GOOGLE PLACES API CLIENT
# ============================================================
class GooglePlacesClient:
    """Search for businesses using Google Places API (Text Search)."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"

    def text_search(self, query, lat, lng, radius, page_token=None):
        """
        Search for businesses by text query near a location.
        Returns up to 20 results per call, with next_page_token for pagination.
        Cost: $0.032 per request (covered by $200 free monthly credit)
        """
        params = {
            "query": query,
            "location": f"{lat},{lng}",
            "radius": radius,
            "key": self.api_key,
            "type": "establishment",
        }
        if page_token:
            params["pagetoken"] = page_token

        response = requests.get(
            f"{self.base_url}/textsearch/json",
            params=params,
            timeout=15,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                return data.get("results", []), data.get("next_page_token")
            elif data.get("status") == "ZERO_RESULTS":
                return [], None
            else:
                print(f"  API status: {data.get('status')} - {data.get('error_message', '')}")
                return [], None
        else:
            print(f"  HTTP {response.status_code}")
            return [], None

    def get_place_details(self, place_id):
        """
        Get detailed info for a specific place (phone, website, hours).
        Cost: $0.017 per request
        """
        params = {
            "place_id": place_id,
            "fields": "name,formatted_phone_number,international_phone_number,website,formatted_address,address_components,rating,user_ratings_total,business_status,opening_hours,types",
            "key": self.api_key,
        }

        response = requests.get(
            f"{self.base_url}/details/json",
            params=params,
            timeout=15,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                return data.get("result", {})
        return {}


# ============================================================
# HUBSPOT SYNC
# ============================================================
class HubSpotSync:
    """Push prospects to HubSpot CRM."""

    BASE_URL = "https://api.hubapi.com"

    def __init__(self, token):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def create_contact(self, prospect):
        """Create a contact in HubSpot. Skip if exists."""
        properties = {
            "email": prospect.get("email", ""),
            "firstname": prospect.get("first_name", ""),
            "lastname": prospect.get("last_name", ""),
            "company": prospect.get("company", ""),
            "phone": prospect.get("phone", ""),
            "city": prospect.get("city", ""),
            "state": "TX",
            "zip": prospect.get("zip", ""),
            "website": prospect.get("website", ""),
            "industry": prospect.get("industry", ""),
            "hs_lead_status": "NEW",
            "lifecyclestage": "lead",
        }

        # Remove empty values
        properties = {k: v for k, v in properties.items() if v}

        payload = {"properties": properties}
        response = requests.post(
            f"{self.BASE_URL}/crm/v3/objects/contacts",
            headers=self.headers,
            json=payload,
            timeout=15,
        )

        if response.status_code == 201:
            return True, "created"
        elif response.status_code == 409:
            return True, "exists"
        else:
            return False, f"{response.status_code}"

    def create_company(self, prospect):
        """Create a company record in HubSpot."""
        properties = {
            "name": prospect.get("company", ""),
            "phone": prospect.get("phone", ""),
            "city": prospect.get("city", ""),
            "state": "TX",
            "zip": prospect.get("zip", ""),
            "website": prospect.get("website", ""),
            "industry": prospect.get("industry", ""),
            "description": f"Found via Google Places. Rating: {prospect.get('rating', 'N/A')} ({prospect.get('reviews', 0)} reviews). MSP Score: {prospect.get('score', 0)}",
        }
        properties = {k: v for k, v in properties.items() if v}

        payload = {"properties": properties}
        response = requests.post(
            f"{self.BASE_URL}/crm/v3/objects/companies",
            headers=self.headers,
            json=payload,
            timeout=15,
        )

        if response.status_code == 201:
            return True, "created"
        elif response.status_code == 409:
            return True, "exists"
        return False, f"{response.status_code}"


# ============================================================
# PROSPECT SCORING
# ============================================================
def score_prospect(place, details, industry_boost=0):
    """
    Score a business 0-100 on MSP-readiness.
    Higher score = better prospect for managed IT services.
    """
    score = 30  # Base score for any real business

    # Has a phone number (+15 — means you can call them)
    if details.get("formatted_phone_number"):
        score += 15

    # Has a website (+10 — means they use technology)
    if details.get("website"):
        score += 10

    # Google rating quality (higher rated = more established)
    rating = place.get("rating", 0)
    if rating >= 4.5:
        score += 8
    elif rating >= 4.0:
        score += 5
    elif rating >= 3.5:
        score += 3

    # Number of reviews (more = bigger business usually)
    reviews = place.get("user_ratings_total", 0)
    if reviews >= 100:
        score += 10
    elif reviews >= 50:
        score += 7
    elif reviews >= 20:
        score += 4
    elif reviews >= 5:
        score += 2

    # Business is operational
    if place.get("business_status") == "OPERATIONAL":
        score += 5

    # Industry boost (some industries need MSPs more)
    score += industry_boost

    return min(100, score)


def extract_zip_from_address(address_components):
    """Pull zip code from Google's address components."""
    if not address_components:
        return ""
    for comp in address_components:
        if "postal_code" in comp.get("types", []):
            return comp.get("long_name", "")
    return ""


def extract_city_from_address(address_components):
    """Pull city from address components."""
    if not address_components:
        return ""
    for comp in address_components:
        if "locality" in comp.get("types", []):
            return comp.get("long_name", "")
    return ""


def guess_email_from_website(website, company_name):
    """
    Try to guess a contact email from the company website.
    Common patterns: info@, contact@, hello@, admin@
    This is a starting point — you can verify with Hunter.io later.
    """
    if not website:
        return ""

    # Extract domain from URL
    domain = website.replace("https://", "").replace("http://", "").replace("www.", "")
    domain = domain.split("/")[0].strip()

    if not domain or "." not in domain:
        return ""

    # Most common B2B email pattern
    return f"info@{domain}"


# ============================================================
# MAIN SCRAPER
# ============================================================
def scrape_prospects(config, markets=None, industry_filter=None, max_results=500, sync_hubspot=False, filters=None):
    """
    Main scraper function with quality filters.
    """
    if filters is None:
        filters = {}

    SOLO_KEYWORDS = ["solo", "freelance", "freelancer", "one man", "1 man", "individual",
                     "mobile notary", "personal", "sole proprietor"]

    api_key = config["google_api_key"]
    if api_key == "YOUR_GOOGLE_API_KEY":
        print("ERROR: Please set your Google API key in the CONFIG section.")
        print("Get one at: console.cloud.google.com -> APIs & Services -> Credentials")
        return []

    places = GooglePlacesClient(api_key)

    if markets is None:
        markets = MARKETS
    elif isinstance(markets, str):
        markets = {markets: MARKETS[markets]}

    queries = SEARCH_QUERIES
    if industry_filter:
        queries = [q for q in queries if industry_filter.lower() in q["query"].lower()
                   or industry_filter.lower() in q["industry"].lower()]
        if not queries:
            print(f"No matching industries for '{industry_filter}'. Available:")
            for q in SEARCH_QUERIES:
                print(f"  - {q['query']} ({q['industry']})")
            return []

    all_prospects = []
    seen_places = set()  # Deduplicate by place_id
    total_api_calls = 0
    filtered_count = 0
    skipped_cached = 0

    # Load persistent cache — never re-scrape businesses we already found
    CACHE_FILE = "scrape_cache.json"
    try:
        if Path(CACHE_FILE).exists():
            with open(CACHE_FILE, "r") as _cf:
                cache_data = json.load(_cf)
                seen_places = set(cache_data.get("seen_place_ids", []))
                print(f"Loaded scrape cache: {len(seen_places)} businesses already scraped (will skip)", flush=True)
        else:
            cache_data = {"seen_place_ids": []}
    except Exception:
        cache_data = {"seen_place_ids": []}

    def save_cache():
        cache_data["seen_place_ids"] = list(seen_places)
        cache_data["last_updated"] = datetime.now().isoformat()
        with open(CACHE_FILE, "w") as _cf:
            json.dump(cache_data, _cf)

    print("=" * 60)
    print("BVTech MSP Prospect Scraper")
    print(f"Markets: {', '.join(m['name'] for m in markets.values())}")
    print(f"Industries: {len(queries)}")
    print(f"Max results: {max_results}")
    print(f"Cache: {len(seen_places)} businesses already in memory (will skip)")
    print("=" * 60)

    for market_key, market in markets.items():
        print(f"\n--- {market['name']}, TX ---")

        for search in queries:
            if len(all_prospects) >= max_results:
                break

            query = f"{search['query']} in {market['name']} Texas"
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Searching: {query}...", flush=True)

            results, next_token = places.text_search(
                query, market["lat"], market["lng"], market["radius"]
            )
            total_api_calls += 1

            new_count = 0
            for place in results:
                if len(all_prospects) >= max_results:
                    break

                place_id = place.get("place_id")
                if place_id in seen_places:
                    skipped_cached += 1
                    continue
                seen_places.add(place_id)

                biz_name = place.get("name", "Unknown")
                print(f"    Checking: {biz_name}...", flush=True)

                # Get detailed info
                details = places.get_place_details(place_id)
                total_api_calls += 1
                time.sleep(0.1)  # Rate limit protection

                # Build prospect record
                phone = details.get("formatted_phone_number", "")
                website = details.get("website", "")
                address = place.get("formatted_address", "")
                address_components = details.get("address_components", [])
                city = extract_city_from_address(address_components) or market["name"]
                zipcode = extract_zip_from_address(address_components)

                # Score this prospect
                score = score_prospect(place, details, search["score_boost"])

                # Guess email from website
                email = guess_email_from_website(website, place.get("name", ""))

                prospect = {
                    "id": f"G{len(all_prospects)+1:05d}",
                    "first_name": "",  # Google doesn't give owner names
                    "last_name": "",
                    "email": email,
                    "phone": phone,
                    "company": place.get("name", ""),
                    "industry": search["industry"],
                    "city": city,
                    "state": "TX",
                    "zip": zipcode,
                    "employees": "",
                    "market": market_key,
                    "score": score,
                    "website": website,
                    "address": address,
                    "rating": place.get("rating", ""),
                    "reviews": place.get("user_ratings_total", 0),
                    "place_id": place_id,
                    "source": "google_places",
                    "scraped_date": datetime.now().isoformat(),
                    "opted_in_date": "",  # Empty — TCPA requires opt-in for SMS
                }

                # Apply quality filters
                skip = False
                rating_val = place.get("rating", 0) or 0
                review_val = place.get("user_ratings_total", 0) or 0
                name_lower = place.get("name", "").lower()

                if filters.get("require_phone") and not phone:
                    skip = True
                if filters.get("require_website") and not website:
                    skip = True
                if filters.get("min_rating") and rating_val < filters["min_rating"]:
                    skip = True
                if filters.get("min_reviews") and review_val < filters["min_reviews"]:
                    skip = True
                if filters.get("min_score") and score < filters["min_score"]:
                    skip = True
                if filters.get("skip_solo"):
                    if any(kw in name_lower for kw in SOLO_KEYWORDS):
                        skip = True

                if skip:
                    filtered_count += 1
                    print(f"      SKIP: {prospect['company']} (filtered out)", flush=True)
                    continue

                all_prospects.append(prospect)
                new_count += 1
                print(f"      PASS: {prospect['company']} | Score:{score} | {phone} | {prospect.get('rating','')} stars", flush=True)

            print(f"    -> {new_count} new | {skipped_cached} already cached | total: {len(all_prospects)}/{max_results}", flush=True)

            # Pagination — get more results if available
            if next_token and len(all_prospects) < max_results:
                time.sleep(2)  # Google requires 2s delay for next page
                results2, _ = places.text_search(
                    query, market["lat"], market["lng"], market["radius"],
                    page_token=next_token,
                )
                total_api_calls += 1

                for place in results2:
                    if len(all_prospects) >= max_results:
                        break
                    place_id = place.get("place_id")
                    if place_id in seen_places:
                        continue
                    seen_places.add(place_id)

                    details = places.get_place_details(place_id)
                    total_api_calls += 1
                    time.sleep(0.1)

                    phone = details.get("formatted_phone_number", "")
                    website = details.get("website", "")
                    address = place.get("formatted_address", "")
                    address_components = details.get("address_components", [])
                    city = extract_city_from_address(address_components) or market["name"]
                    zipcode = extract_zip_from_address(address_components)
                    score = score_prospect(place, details, search["score_boost"])
                    email = guess_email_from_website(website, place.get("name", ""))

                    prospect = {
                        "id": f"G{len(all_prospects)+1:05d}",
                        "first_name": "",
                        "last_name": "",
                        "email": email,
                        "phone": phone,
                        "company": place.get("name", ""),
                        "industry": search["industry"],
                        "city": city,
                        "state": "TX",
                        "zip": zipcode,
                        "employees": "",
                        "market": market_key,
                        "score": score,
                        "website": website,
                        "address": address,
                        "rating": place.get("rating", ""),
                        "reviews": place.get("user_ratings_total", 0),
                        "place_id": place_id,
                        "source": "google_places",
                        "scraped_date": datetime.now().isoformat(),
                        "opted_in_date": "",
                    }
                    all_prospects.append(prospect)

    # Sort by score (best prospects first)
    all_prospects.sort(key=lambda x: x["score"], reverse=True)

    # Save to CSV
    if all_prospects:
        fieldnames = all_prospects[0].keys()

        with open(config["output_csv"], "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_prospects)

        # Also save SMS version (same data, reminder about opt-in)
        with open(config["sms_csv"], "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_prospects)

        # Save raw JSON for reference
        with open(config["raw_json"], "w", encoding="utf-8") as f:
            json.dump(all_prospects, f, indent=2)

    # Save persistent cache
    save_cache()

    # Summary
    print("\n" + "=" * 60)
    print(f"SCRAPING COMPLETE")
    print(f"=" * 60)
    print(f"NEW prospects found: {len(all_prospects)}")
    print(f"Skipped (already cached): {skipped_cached}")
    print(f"Filtered out (low quality): {filtered_count}")
    print(f"Total in cache now: {len(seen_places)} businesses")
    print(f"API calls made: {total_api_calls}")
    est_cost = total_api_calls * 0.025
    saved_cost = skipped_cached * 0.017  # Saved by not calling place details
    print(f"Estimated API cost: ${est_cost:.2f} (saved ${saved_cost:.2f} from cache)")
    print(f"")

    # Stats
    with_phone = sum(1 for p in all_prospects if p["phone"])
    with_website = sum(1 for p in all_prospects if p["website"])
    with_email = sum(1 for p in all_prospects if p["email"])
    avg_score = sum(p["score"] for p in all_prospects) / max(len(all_prospects), 1)

    print(f"With phone number: {with_phone} ({with_phone/max(len(all_prospects),1)*100:.0f}%)")
    print(f"With website: {with_website} ({with_website/max(len(all_prospects),1)*100:.0f}%)")
    print(f"With email (guessed): {with_email} ({with_email/max(len(all_prospects),1)*100:.0f}%)")
    print(f"Average MSP score: {avg_score:.0f}/100")
    print(f"")

    by_market = {}
    by_industry = {}
    for p in all_prospects:
        by_market[p["city"]] = by_market.get(p["city"], 0) + 1
        by_industry[p["industry"]] = by_industry.get(p["industry"], 0) + 1

    print("By Market:")
    for m, c in sorted(by_market.items(), key=lambda x: -x[1]):
        print(f"  {m}: {c}")

    print("\nTop Industries:")
    for ind, c in sorted(by_industry.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ind}: {c}")

    print(f"\nTop 5 Prospects (highest score):")
    for p in all_prospects[:5]:
        print(f"  [{p['score']}] {p['company']} | {p['city']} | {p['industry']} | {p['phone']} | {p['website']}")

    print(f"\nSaved to: {config['output_csv']}")
    print(f"SMS list: {config['sms_csv']} (REMINDER: opt-in dates required for TCPA)")

    # HubSpot sync
    if sync_hubspot:
        hs_token = config.get("hubspot_token", "")
        if hs_token and hs_token != "YOUR_HUBSPOT_TOKEN":
            print(f"\nSyncing {len(all_prospects)} prospects to HubSpot...")
            hs = HubSpotSync(hs_token)
            created = 0
            existed = 0
            failed = 0

            for i, p in enumerate(all_prospects):
                # Create company
                hs.create_company(p)

                # Create contact (if we have an email)
                if p.get("email"):
                    ok, status = hs.create_contact(p)
                    if status == "created":
                        created += 1
                    elif status == "exists":
                        existed += 1
                    else:
                        failed += 1

                if (i + 1) % 25 == 0:
                    print(f"  Progress: {i+1}/{len(all_prospects)}")
                    time.sleep(0.2)

            print(f"HubSpot sync: {created} new contacts, {existed} existing, {failed} failed")
            print(f"Companies also synced to HubSpot CRM.")
        else:
            print("\nHubSpot sync skipped (no token configured)")

    return all_prospects


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BVTech MSP Prospect Scraper")
    parser.add_argument("--market", choices=["austin", "san_antonio", "houston"],
                        help="Scrape single market only")
    parser.add_argument("--industry", help="Filter by industry keyword (e.g. 'law', 'medical')")
    parser.add_argument("--max", type=int, default=500, help="Max prospects to find (default: 500)")
    parser.add_argument("--sync", action="store_true", help="Sync results to HubSpot CRM")
    parser.add_argument("--min-rating", type=float, default=0, help="Min Google star rating (e.g. 4.0)")
    parser.add_argument("--min-reviews", type=int, default=0, help="Min number of Google reviews")
    parser.add_argument("--require-phone", action="store_true", help="Only include businesses with phone")
    parser.add_argument("--require-website", action="store_true", help="Only include businesses with website")
    parser.add_argument("--min-score", type=int, default=0, help="Min MSP-readiness score (0-100)")
    parser.add_argument("--skip-solo", action="store_true", help="Skip solo/freelance businesses")
    args = parser.parse_args()

    markets = None
    if args.market:
        if args.market in MARKETS:
            markets = args.market
        else:
            print(f"Unknown market: {args.market}")
            return

    filters = {
        "min_rating": args.min_rating,
        "min_reviews": args.min_reviews,
        "require_phone": args.require_phone,
        "require_website": args.require_website,
        "min_score": args.min_score,
        "skip_solo": args.skip_solo,
    }

    scrape_prospects(
        config=CONFIG,
        markets=markets,
        industry_filter=args.industry,
        max_results=args.max,
        sync_hubspot=args.sync,
        filters=filters,
    )


if __name__ == "__main__":
    main()
