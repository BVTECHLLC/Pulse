#!/usr/bin/env python3
"""
BVTech MSP SUPER SCRAPER  v1.0
==============================================================
Decision-maker discovery engine for the BVTech Command Center.

WHAT THIS DOES (vs the old prospect_scraper.py):
  Old:  Google Places -> business name + phone + info@guess email
  New:  Google Places  +  website deep-crawl  +  LinkedIn discovery
        +  multi-source web search  +  decision-maker name/title/email
        extraction  ->  HubSpot (with associations + custom props)
        ->  Dialpad contacts (real humans, not info@).

KEY UPGRADES
  1. Reuses the proven Google Places logic from prospect_scraper.py
     (same markets, same scoring, same cache file -> no duplicate work)
  2. Deep-crawls each company's site: /, /about, /team, /contact,
     /leadership, /staff, /our-team, /attorneys, /providers, /agents
     -> pulls REAL emails (not info@), phones, names, titles
  3. LinkedIn discovery via Google site: operators
     (this is how every real scraper does it -- LinkedIn's official
      /v2 API does NOT expose people-search; it only lets you read
      the authed user + orgs they admin. We use the auth token for
      what it CAN do, and use site:linkedin.com search for the rest.)
  4. Decision-maker title scoring: Owner / Founder / Partner / CEO /
     President / Managing Partner / Practice Manager / Office Manager
     / IT Director / General Counsel / COO -- these get +30 score.
  5. Email pattern generation: first.last@, flast@, first@, f.last@
     With optional Hunter.io verification if HUNTER_API_KEY is set.
  6. Phone extraction from any page (multi-format regex).
  7. HubSpot sync: companies + contacts + associations + custom
     properties (msp_score, decision_maker_title, linkedin_url,
     discovery_source, deep_crawl_pages).
  8. Dialpad sync: pushes the discovered humans straight into the
     power dialer with names + titles, not "info@".

CONFIG (reads bvtech_config.json -- same file the GUI writes):
  google_api_key       (required, you already have this)
  hubspot_token        (optional, for CRM sync)
  dialpad_api_key      (optional, for dialer sync)
  linkedin_access_token(optional, for LinkedIn org enrichment)
  hunter_api_key       (optional, for email verification)
  bing_api_key         (optional, adds Bing as a search source)

CLI
  python super_scraper.py                          # all markets, all industries
  python super_scraper.py --market austin --max 50
  python super_scraper.py --industry "law firm" --sync --dialer
  python super_scraper.py --deep                   # max-depth crawl + LI lookup
  python super_scraper.py --titles-only            # only keep prospects where we found a real decision maker
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

try:
    import requests
except ImportError:
    print("Install: pip install requests")
    sys.exit(1)

# Reuse the proven pieces of the existing scraper instead of duplicating them.
# This means: same markets, same MSP-readiness scoring base, same cache file.
try:
    from prospect_scraper import (
        GooglePlacesClient,
        MARKETS,
        SEARCH_QUERIES,
        score_prospect,
        extract_zip_from_address,
        extract_city_from_address,
    )
except Exception as e:
    print(f"FATAL: super_scraper.py must live next to prospect_scraper.py ({e})")
    sys.exit(1)


# ============================================================
# CONFIG
# ============================================================
CONFIG = {
    "google_api_key":      os.getenv("GOOGLE_API_KEY", ""),
    "hubspot_token":       os.getenv("HUBSPOT_TOKEN", ""),
    "dialpad_api_key":     os.getenv("DIALPAD_API_KEY", ""),
    "linkedin_access_token": os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
    "hunter_api_key":      os.getenv("HUNTER_API_KEY", ""),
    "bing_api_key":        os.getenv("BING_API_KEY", ""),
    "output_csv":          "prospects.csv",          # same file the dialer reads
    "super_csv":           "super_prospects.csv",    # full enriched record
    "raw_json":            "super_raw.json",
    "cache_file":          "super_scrape_cache.json",
}

_gui_config_path = Path("bvtech_config.json")
if _gui_config_path.exists():
    try:
        with open(_gui_config_path, "r") as f:
            gui = json.load(f)
        for k in ("google_api_key", "hubspot_token", "dialpad_api_key",
                  "linkedin_access_token", "hunter_api_key", "bing_api_key"):
            if gui.get(k):
                CONFIG[k] = gui[k]
    except Exception:
        pass


# ============================================================
# DECISION-MAKER TITLE INTELLIGENCE
# ============================================================
# Ranked highest -> lowest. Higher = more likely to be a real buyer.
DECISION_MAKER_TITLES = [
    # Tier S — owner-operators, sign the check themselves
    ("owner",                  35),
    ("founder",                35),
    ("co-founder",             34),
    ("president",              33),
    ("ceo",                    33),
    ("chief executive",        33),
    ("managing partner",       32),
    ("managing member",        31),
    ("principal",              30),
    ("partner",                28),
    # Tier A — operationally responsible, often pick the IT vendor
    ("coo",                    27),
    ("chief operating",        27),
    ("general manager",        25),
    ("practice manager",       25),
    ("office manager",         24),
    ("operations manager",     24),
    ("administrator",          22),
    ("office administrator",   24),
    ("practice administrator", 25),
    # Tier B — IT decision influencers
    ("it director",            26),
    ("director of it",         26),
    ("director of technology", 25),
    ("it manager",             22),
    ("cto",                    25),
    # Tier C — vertical-specific buyers
    ("general counsel",        24),  # law firms
    ("controller",             22),  # finance / multi-location
    ("cfo",                    24),
    ("medical director",       22),  # medical
    ("dental director",        22),
    ("clinic manager",         22),
    ("project manager",        15),  # construction (lower — usually not the buyer)
    ("estimator",              12),
]

# Industries where the OWNER is almost always the buyer (small shops)
OWNER_DRIVEN_INDUSTRIES = {
    "Law Firms", "Medical Offices", "Dental Practices",
    "Accounting / CPA", "Insurance", "Real Estate",
    "Construction", "Financial Advisors", "Veterinary Clinics",
}


_SHORT_ACRONYMS = {"ceo", "coo", "cfo", "cto", "it director", "it manager"}


def title_score(title: str) -> int:
    """Return the highest matching decision-maker boost for a title string.

    Short acronyms (CEO, COO, CFO, CTO) must match on word boundaries so
    'Coordinator' does not score as 'COO'.
    """
    if not title:
        return 0
    t = title.lower()
    best = 0
    for needle, points in DECISION_MAKER_TITLES:
        if needle in _SHORT_ACRONYMS or len(needle) <= 4:
            if re.search(r"\b" + re.escape(needle) + r"\b", t):
                if points > best:
                    best = points
        else:
            if needle in t and points > best:
                best = points
    return best


# ============================================================
# REGEX TOOLBOX
# ============================================================
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
# Catches obfuscated forms: "name [at] domain dot com"
EMAIL_OBFUSCATED_RE = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*[\[\(]?\s*(?:at|@)\s*[\]\)]?\s*([A-Za-z0-9.-]+)\s*[\[\(]?\s*(?:dot|\.)\s*[\]\)]?\s*([A-Za-z]{2,})",
    re.IGNORECASE,
)
PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})\b"
)
LINKEDIN_PROFILE_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?",
    re.IGNORECASE,
)
LINKEDIN_COMPANY_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?",
    re.IGNORECASE,
)
# Person + title near each other -- "John Smith, Owner" / "Jane Doe — Managing Partner"
# Title capture stops at sentence-ending punctuation or another capital-letter word
# that doesn't fit a title (prevents "Managing Partner Contact" type drift).
NAME_TITLE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s[A-Z]\.)?\s[A-Z][a-z]+)\s*[,\-—–|]\s*"
    r"((?:Chief\s|Managing\s|General\s|Office\s|Practice\s|Operations\s|Co[- ])?"
    r"(?:Owner|Founder|President|CEO|COO|CFO|CTO|Partner|Principal|Member|"
    r"Manager|Administrator|Director|Counsel|Officer|Attorney|Physician))"
)
# Generic / role inboxes we want to DOWN-rank (but not throw away)
GENERIC_LOCAL_PARTS = {
    "info", "contact", "hello", "admin", "office", "sales",
    "support", "team", "mail", "inquiries", "reception", "frontdesk",
    "general", "marketing", "service", "help", "noreply", "no-reply",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


def clean_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"


def domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        d = urlparse(url if "://" in url else "http://" + url).netloc.lower()
        return d.replace("www.", "").strip()
    except Exception:
        return ""


def is_generic_email(email: str) -> bool:
    if not email or "@" not in email:
        return True
    local = email.split("@", 1)[0].lower()
    return local in GENERIC_LOCAL_PARTS


# ============================================================
# WEBSITE DEEP CRAWLER
# ============================================================
class WebsiteCrawler:
    """Pull every email, phone, LinkedIn link, and name+title pair off a site."""

    # Priority pages to try after the homepage. Order matters -- contact and
    # team pages are where decision-makers hide.
    CANDIDATE_PATHS = [
        "/contact", "/contact-us", "/contact.html",
        "/about", "/about-us", "/about.html",
        "/team", "/our-team", "/meet-the-team", "/staff", "/people",
        "/leadership", "/management",
        "/attorneys", "/lawyers", "/our-attorneys",         # law
        "/providers", "/physicians", "/doctors", "/our-doctors",  # medical
        "/agents", "/our-agents",                            # insurance / RE
        "/partners",
    ]

    def __init__(self, timeout=12, max_pages=8):
        self.timeout = timeout
        self.max_pages = max_pages
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch(self, url):
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if r.status_code == 200 and "text/html" in r.headers.get("content-type", "").lower():
                return r.text
        except Exception:
            return None
        return None

    def crawl(self, base_url):
        """Return a dict with all signals extracted from the site."""
        result = {
            "pages_crawled": [],
            "emails": set(),
            "phones": set(),
            "linkedin_profiles": set(),
            "linkedin_company": "",
            "people": [],   # list of {name, title}
        }
        if not base_url:
            return result
        if "://" not in base_url:
            base_url = "http://" + base_url

        base_domain = domain_of(base_url)
        if not base_domain:
            return result

        urls_to_try = [base_url] + [urljoin(base_url, p) for p in self.CANDIDATE_PATHS]
        for url in urls_to_try[: self.max_pages]:
            html = self.fetch(url)
            if not html:
                continue
            result["pages_crawled"].append(url)
            self._extract_from_html(html, base_domain, result)
            time.sleep(0.25)  # be polite

        # convert sets to lists for JSON-friendliness
        result["emails"] = sorted(result["emails"])
        result["phones"] = sorted(result["phones"])
        result["linkedin_profiles"] = sorted(result["linkedin_profiles"])
        return result

    def _extract_from_html(self, html, base_domain, result):
        # 1. Emails — only keep ones on the company's own domain (filters out
        #    cdn/cloudflare/wix junk and image filenames that look email-like)
        for m in EMAIL_RE.findall(html):
            m = m.strip().rstrip(".,;:)>\"'")
            if "@" not in m or "." not in m:
                continue
            dom = m.split("@", 1)[1].lower()
            # Allow same-domain OR a parent/subdomain match
            if base_domain in dom or dom.endswith("." + base_domain):
                result["emails"].add(m.lower())

        # 2. Obfuscated emails (name [at] domain dot com)
        for local, dom, tld in EMAIL_OBFUSCATED_RE.findall(html):
            cand = f"{local}@{dom}.{tld}".lower()
            if base_domain in cand:
                result["emails"].add(cand)

        # 3. Phones
        for area, mid, end in PHONE_RE.findall(html):
            phone = clean_phone(f"{area}{mid}{end}")
            if phone:
                result["phones"].add(phone)

        # 4. LinkedIn
        for li in LINKEDIN_PROFILE_RE.findall(html):
            result["linkedin_profiles"].add(li.rstrip("/"))
        m = LINKEDIN_COMPANY_RE.search(html)
        if m and not result["linkedin_company"]:
            result["linkedin_company"] = m.group(0).rstrip("/")

        # 5. Name + title pairs in nearby text
        # Strip tags first so "Jane Doe</h3><p>Owner" still matches
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        for name, title in NAME_TITLE_RE.findall(text):
            t_clean = title.strip().rstrip(".,;:")
            if title_score(t_clean) > 0:
                # avoid duplicates
                key = (name.strip(), t_clean.lower())
                if not any((p["name"], p["title"].lower()) == key for p in result["people"]):
                    result["people"].append({"name": name.strip(), "title": t_clean})


# ============================================================
# LINKEDIN DISCOVERY
# ============================================================
# IMPORTANT NOTE / NO BS:
# LinkedIn's official /v2 API does NOT expose people-search, lead lookup,
# or company employee lists. Those endpoints require Marketing Developer
# Platform or Sales Navigator partnership and are not granted to most apps.
#
# What we DO with the linkedin_access_token from your config:
#   - Validate the token + cache "me" profile (free, /v2/userinfo)
#   - Read organizations the authed user administers (if any)
#
# What we do for ACTUAL lead discovery:
#   - Google site: search ("site:linkedin.com/in" + company + title)
#     This is exactly how Apollo, ZoomInfo, RocketReach, and every
#     other commercial scraper actually finds these profiles.
#   - We surface the profile URL + the title we matched on, so a human
#     can verify before HubSpot push.

class LinkedInDiscovery:
    def __init__(self, google_api_key, linkedin_token=""):
        self.google_api_key = google_api_key
        self.linkedin_token = linkedin_token
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def validate_token(self):
        if not self.linkedin_token:
            return False, "no token"
        try:
            r = requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {self.linkedin_token}"},
                timeout=10,
            )
            if r.status_code == 200:
                return True, r.json()
        except Exception as e:
            return False, str(e)
        return False, f"http {r.status_code}"

    def find_decision_makers(self, company_name, city, max_results=5):
        """
        Use Google Custom Search-style operators to find LinkedIn profiles
        that look like decision makers at this company. Falls back to
        public Google search HTML scraping if no Custom Search key is set.
        """
        if not company_name:
            return []
        title_clause = '("Owner" OR "Founder" OR "President" OR "CEO" OR "Managing Partner" OR "Principal" OR "Office Manager" OR "Practice Manager")'
        query = f'site:linkedin.com/in "{company_name}" {title_clause}'
        if city:
            query += f' "{city}"'

        results = self._google_text_search(query, max_results)
        # Each result -> try to detect title from snippet
        out = []
        for r in results:
            title_text = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            if "linkedin.com/in/" not in url:
                continue
            # LinkedIn titles render as "Name - Title - Company | LinkedIn"
            person_name = ""
            person_title = ""
            parts = re.split(r"\s[-–|]\s", title_text)
            if parts:
                person_name = parts[0].strip()
                if len(parts) > 1:
                    person_title = parts[1].strip()
            if not person_title:
                # try snippet
                m = re.search(r"(Owner|Founder|President|CEO|Managing Partner|Principal|Office Manager|Practice Manager|Partner|COO)", snippet, re.I)
                if m:
                    person_title = m.group(0)
            out.append({
                "name": person_name,
                "title": person_title,
                "linkedin_url": url.split("?")[0].rstrip("/"),
                "snippet": snippet[:200],
                "source": "linkedin_via_google",
            })
        return out

    def _google_text_search(self, query, max_results):
        """
        We don't want to require a separate Custom Search Engine config.
        Strategy:
          1. Try Google Custom Search JSON API only if a CSE id is set.
          2. Otherwise, hit Bing if a Bing key is in config.
          3. Otherwise, hit DuckDuckGo HTML (no key, no auth) as a free fallback.
        """
        cse_id = os.getenv("GOOGLE_CSE_ID", "")
        if self.google_api_key and cse_id:
            try:
                r = requests.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": self.google_api_key, "cx": cse_id, "q": query, "num": min(max_results, 10)},
                    timeout=15,
                )
                if r.status_code == 200:
                    items = r.json().get("items", [])
                    return [{"title": i.get("title", ""), "url": i.get("link", ""),
                             "snippet": i.get("snippet", "")} for i in items]
            except Exception:
                pass

        bing_key = CONFIG.get("bing_api_key", "")
        if bing_key:
            try:
                r = requests.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    headers={"Ocp-Apim-Subscription-Key": bing_key},
                    params={"q": query, "count": max_results},
                    timeout=15,
                )
                if r.status_code == 200:
                    items = r.json().get("webPages", {}).get("value", [])
                    return [{"title": i.get("name", ""), "url": i.get("url", ""),
                             "snippet": i.get("snippet", "")} for i in items]
            except Exception:
                pass

        # Free fallback: DuckDuckGo HTML
        try:
            r = self.session.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                timeout=15,
            )
            if r.status_code == 200:
                return self._parse_ddg(r.text, max_results)
        except Exception:
            pass
        return []

    def _parse_ddg(self, html, max_results):
        out = []
        # crude but works: result blocks have class="result__a" links + result__snippet
        link_re = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
        snip_re = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S)
        links = link_re.findall(html)
        snips = snip_re.findall(html)
        for i, (url, title) in enumerate(links[:max_results]):
            # DDG wraps real URLs in /l/?uddg=...
            real = url
            m = re.search(r"uddg=([^&]+)", url)
            if m:
                from urllib.parse import unquote
                real = unquote(m.group(1))
            title_clean = re.sub(r"<[^>]+>", "", title).strip()
            snippet = re.sub(r"<[^>]+>", "", snips[i]).strip() if i < len(snips) else ""
            out.append({"title": title_clean, "url": real, "snippet": snippet})
        return out


# ============================================================
# EMAIL PATTERN GENERATION + VERIFICATION
# ============================================================
def generate_email_candidates(first, last, domain):
    if not (first and last and domain):
        return []
    f = re.sub(r"[^a-z]", "", first.lower())
    l = re.sub(r"[^a-z]", "", last.lower())
    if not (f and l):
        return []
    return [
        f"{f}.{l}@{domain}",
        f"{f}{l}@{domain}",
        f"{f[0]}{l}@{domain}",
        f"{f}@{domain}",
        f"{f}_{l}@{domain}",
        f"{f}.{l[0]}@{domain}",
        f"{l}@{domain}",
    ]


def hunter_verify(email, hunter_key):
    if not (email and hunter_key):
        return None
    try:
        r = requests.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": hunter_key},
            timeout=12,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            return {
                "result": d.get("result", ""),     # deliverable / risky / undeliverable
                "score": d.get("score", 0),
                "status": d.get("status", ""),
            }
    except Exception:
        pass
    return None


def hunter_domain_search(domain, hunter_key, limit=10):
    """Returns Hunter's known emails for a domain (often includes named people)."""
    if not (domain and hunter_key):
        return []
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": hunter_key, "limit": limit},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            out = []
            for e in d.get("emails", []):
                out.append({
                    "email": e.get("value", ""),
                    "first_name": e.get("first_name", "") or "",
                    "last_name": e.get("last_name", "") or "",
                    "title": e.get("position", "") or "",
                    "linkedin_url": e.get("linkedin", "") or "",
                    "phone": e.get("phone_number", "") or "",
                    "confidence": e.get("confidence", 0),
                    "source": "hunter",
                })
            return out
    except Exception:
        pass
    return []


# ============================================================
# HUBSPOT SYNC (with associations + custom props)
# ============================================================
class HubSpotSync:
    BASE = "https://api.hubapi.com"

    def __init__(self, token):
        self.h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def upsert_company(self, prospect):
        props = {
            "name":     prospect.get("company", ""),
            "phone":    prospect.get("phone", ""),
            "city":     prospect.get("city", ""),
            "state":    prospect.get("state", "TX"),
            "zip":      prospect.get("zip", ""),
            "website":  prospect.get("website", ""),
            "industry": prospect.get("industry", ""),
            "description": (
                f"BVTech Super Scraper. MSP score {prospect.get('score',0)}. "
                f"Source: {prospect.get('discovery_source','')}. "
                f"Decision maker: {prospect.get('decision_maker_name','(unknown)')} "
                f"({prospect.get('decision_maker_title','')})."
            ),
            "linkedin_company_page": prospect.get("linkedin_company", ""),
        }
        props = {k: v for k, v in props.items() if v}
        try:
            r = requests.post(f"{self.BASE}/crm/v3/objects/companies",
                              headers=self.h, json={"properties": props}, timeout=15)
            if r.status_code == 201:
                return r.json().get("id"), "created"
            if r.status_code == 409:
                return None, "exists"
            return None, f"err {r.status_code}"
        except Exception as e:
            return None, str(e)

    def upsert_contact(self, prospect, company_id=None):
        first = prospect.get("first_name", "")
        last = prospect.get("last_name", "")
        email = prospect.get("email", "")
        if not (email or (first and last)):
            return None, "no identity"
        props = {
            "email":     email,
            "firstname": first,
            "lastname":  last,
            "company":   prospect.get("company", ""),
            "phone":     prospect.get("phone", ""),
            "jobtitle":  prospect.get("decision_maker_title", "") or prospect.get("title", ""),
            "city":      prospect.get("city", ""),
            "state":     "TX",
            "zip":       prospect.get("zip", ""),
            "website":   prospect.get("website", ""),
            "industry":  prospect.get("industry", ""),
            "hs_lead_status": "NEW",
            "lifecyclestage": "lead",
            "linkedin_url":   prospect.get("linkedin_url", ""),
            "msp_score":      prospect.get("score", 0),
            "discovery_source": prospect.get("discovery_source", ""),
        }
        props = {k: v for k, v in props.items() if v not in ("", None)}
        try:
            r = requests.post(f"{self.BASE}/crm/v3/objects/contacts",
                              headers=self.h, json={"properties": props}, timeout=15)
            if r.status_code == 201:
                contact_id = r.json().get("id")
                if company_id and contact_id:
                    self.associate(contact_id, company_id)
                return contact_id, "created"
            if r.status_code == 409:
                return None, "exists"
            return None, f"err {r.status_code} {r.text[:120]}"
        except Exception as e:
            return None, str(e)

    def associate(self, contact_id, company_id):
        try:
            requests.put(
                f"{self.BASE}/crm/v3/objects/contacts/{contact_id}/associations/companies/{company_id}/contact_to_company",
                headers=self.h, timeout=10,
            )
        except Exception:
            pass


# ============================================================
# DIALPAD SYNC (push named decision-makers into the dialer)
# ============================================================
class DialpadSync:
    BASE = "https://dialpad.com/api/v2"

    def __init__(self, api_key):
        self.h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def create_contact(self, p):
        phone = p.get("phone", "")
        if not phone:
            return False, "no phone"
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            digits = "1" + digits
        payload = {
            "first_name": p.get("first_name", "") or p.get("company", "")[:30],
            "last_name":  p.get("last_name", "") or "",
            "phones":     [f"+{digits}"],
            "company_name": p.get("company", ""),
            "job_title":  p.get("decision_maker_title", "") or p.get("title", ""),
        }
        if p.get("email"):
            payload["emails"] = [p["email"]]
        try:
            r = requests.post(f"{self.BASE}/contacts", headers=self.h, json=payload, timeout=15)
            if r.status_code in (200, 201):
                return True, "ok"
            if r.status_code == 409:
                return True, "exists"
            return False, f"{r.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================
# THE SUPER PIPELINE
# ============================================================
def run_super_scraper(
    market_filter=None,
    industry_filter=None,
    max_results=200,
    deep=False,
    titles_only=False,
    sync_hubspot=False,
    sync_dialer=False,
    require_phone=False,
    skip_solo=False,
    min_score=0,
):
    if not CONFIG["google_api_key"] or CONFIG["google_api_key"] == "YOUR_GOOGLE_API_KEY":
        print("ERROR: google_api_key not set. Configure it in the BVTech GUI -> Settings.")
        return []

    print("=" * 64)
    print("BVTech SUPER SCRAPER  v1.0")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'DEEP (LinkedIn + crawl)' if deep else 'STANDARD (crawl only)'}")
    print(f"Max results: {max_results}  |  HubSpot sync: {sync_hubspot}  |  Dialer sync: {sync_dialer}")
    print("=" * 64)

    places   = GooglePlacesClient(CONFIG["google_api_key"])
    crawler  = WebsiteCrawler(max_pages=8 if deep else 4)
    li       = LinkedInDiscovery(CONFIG["google_api_key"], CONFIG.get("linkedin_access_token", ""))
    hs       = HubSpotSync(CONFIG["hubspot_token"]) if sync_hubspot and CONFIG.get("hubspot_token") else None
    dp       = DialpadSync(CONFIG["dialpad_api_key"]) if sync_dialer and CONFIG.get("dialpad_api_key") else None

    if li.linkedin_token:
        ok, info = li.validate_token()
        print(f"LinkedIn token: {'OK -- ' + info.get('name','authed') if ok else 'INVALID -- ' + str(info)}")
    if CONFIG.get("hunter_api_key"):
        print("Hunter.io: enabled (will domain-search + verify emails)")
    if hs:
        print("HubSpot: ENABLED")
    if dp:
        print("Dialpad: ENABLED")
    print("-" * 64)

    # ---- 1. seed list from Google Places (reuse existing logic) ----
    markets = MARKETS
    if market_filter:
        markets = {market_filter: MARKETS[market_filter]}

    queries = SEARCH_QUERIES
    if industry_filter:
        f = industry_filter.lower()
        queries = [q for q in SEARCH_QUERIES
                   if f in q["query"].lower() or f in q["industry"].lower()]
        if not queries:
            print(f"No industry matches for '{industry_filter}'")
            return []

    # cache (separate from old scraper so they don't fight each other)
    seen = set()
    cf = Path(CONFIG["cache_file"])
    if cf.exists():
        try:
            seen = set(json.loads(cf.read_text()).get("seen", []))
            print(f"Cache: {len(seen)} place_ids already enriched (will skip)")
        except Exception:
            seen = set()

    enriched = []
    api_calls = 0

    for mk, market in markets.items():
        print(f"\n=== {market['name']}, TX ===")
        for search in queries:
            if len(enriched) >= max_results:
                break
            q = f"{search['query']} in {market['name']} Texas"
            print(f"  [PLACES] {q}")
            results, next_token = places.text_search(
                q, market["lat"], market["lng"], market["radius"]
            )
            api_calls += 1

            page_results = list(results)
            if next_token and len(enriched) < max_results:
                time.sleep(2)
                more, _ = places.text_search(
                    q, market["lat"], market["lng"], market["radius"], page_token=next_token
                )
                api_calls += 1
                page_results.extend(more)

            for place in page_results:
                if len(enriched) >= max_results:
                    break
                pid = place.get("place_id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)

                name = place.get("name", "")
                print(f"    -> {name}")

                # Place details (phone, website, address)
                details = places.get_place_details(pid)
                api_calls += 1
                time.sleep(0.1)

                phone = details.get("formatted_phone_number", "")
                website = details.get("website", "")
                addr_components = details.get("address_components", [])
                city = extract_city_from_address(addr_components) or market["name"]
                zipcode = extract_zip_from_address(addr_components)
                base_score = score_prospect(place, details, search["score_boost"])

                # ---- skip filters BEFORE we spend crawl time ----
                if require_phone and not phone:
                    continue
                if skip_solo:
                    nl = name.lower()
                    if any(k in nl for k in ("solo", "freelance", "1 man", "one man", "individual", "mobile notary")):
                        continue

                prospect = {
                    "id": f"S{len(enriched)+1:05d}",
                    "company": name,
                    "industry": search["industry"],
                    "phone": phone,
                    "website": website,
                    "address": place.get("formatted_address", ""),
                    "city": city,
                    "state": "TX",
                    "zip": zipcode,
                    "market": mk,
                    "rating": place.get("rating", ""),
                    "reviews": place.get("user_ratings_total", 0),
                    "place_id": pid,
                    "score": base_score,
                    "discovery_source": "google_places",
                    "scraped_date": datetime.now().isoformat(),
                    # decision-maker fields, filled below
                    "first_name": "",
                    "last_name": "",
                    "email": "",
                    "decision_maker_name": "",
                    "decision_maker_title": "",
                    "linkedin_url": "",
                    "linkedin_company": "",
                    "all_emails": "",
                    "all_phones": "",
                    "deep_crawl_pages": 0,
                    "title": "",
                    "opted_in_date": "",
                }

                # ---- 2. deep-crawl the website ----
                site_signals = {}
                if website:
                    print(f"       crawling {domain_of(website)}...")
                    site_signals = crawler.crawl(website)
                    prospect["deep_crawl_pages"] = len(site_signals.get("pages_crawled", []))
                    prospect["all_emails"] = "; ".join(site_signals.get("emails", []))
                    extra_phones = [p for p in site_signals.get("phones", []) if p != phone]
                    prospect["all_phones"] = "; ".join(extra_phones)
                    prospect["linkedin_company"] = site_signals.get("linkedin_company", "")

                    # First non-generic email beats info@
                    real_email = ""
                    for e in site_signals.get("emails", []):
                        if not is_generic_email(e):
                            real_email = e
                            break
                    if not real_email and site_signals.get("emails"):
                        real_email = site_signals["emails"][0]  # info@ as fallback
                    prospect["email"] = real_email

                    # Best person from site
                    if site_signals.get("people"):
                        best = max(site_signals["people"],
                                   key=lambda p: title_score(p["title"]))
                        prospect["decision_maker_name"] = best["name"]
                        prospect["decision_maker_title"] = best["title"]
                        parts = best["name"].split()
                        if len(parts) >= 2:
                            prospect["first_name"] = parts[0]
                            prospect["last_name"] = " ".join(parts[1:])

                    # Best LinkedIn profile from site
                    if site_signals.get("linkedin_profiles"):
                        prospect["linkedin_url"] = site_signals["linkedin_profiles"][0]

                    if not phone and site_signals.get("phones"):
                        prospect["phone"] = site_signals["phones"][0]

                # ---- 3. Hunter.io domain search (if key present) ----
                if CONFIG.get("hunter_api_key") and website:
                    dom = domain_of(website)
                    if dom:
                        hunter_people = hunter_domain_search(dom, CONFIG["hunter_api_key"], limit=8)
                        if hunter_people:
                            # pick the highest-title person
                            best = max(hunter_people, key=lambda p: title_score(p.get("title", "")))
                            if title_score(best.get("title", "")) > title_score(prospect["decision_maker_title"]):
                                prospect["decision_maker_name"] = f"{best['first_name']} {best['last_name']}".strip()
                                prospect["decision_maker_title"] = best["title"]
                                prospect["first_name"] = best["first_name"]
                                prospect["last_name"] = best["last_name"]
                                if best.get("email") and is_generic_email(prospect.get("email", "")):
                                    prospect["email"] = best["email"]
                                if best.get("linkedin_url") and not prospect.get("linkedin_url"):
                                    prospect["linkedin_url"] = best["linkedin_url"]
                                if best.get("phone") and not prospect.get("phone"):
                                    prospect["phone"] = best["phone"]
                            prospect["discovery_source"] = "google_places + hunter"

                # ---- 4. LinkedIn discovery (deep mode) ----
                if deep:
                    print(f"       linkedin lookup...")
                    li_people = li.find_decision_makers(name, city, max_results=4)
                    if li_people:
                        best = max(li_people, key=lambda p: title_score(p.get("title", "")))
                        if title_score(best.get("title", "")) > title_score(prospect["decision_maker_title"]):
                            prospect["decision_maker_name"] = best["name"]
                            prospect["decision_maker_title"] = best["title"]
                            parts = best["name"].split()
                            if len(parts) >= 2 and not prospect["first_name"]:
                                prospect["first_name"] = parts[0]
                                prospect["last_name"] = " ".join(parts[1:])
                            if not prospect.get("linkedin_url"):
                                prospect["linkedin_url"] = best["linkedin_url"]
                            prospect["discovery_source"] = prospect["discovery_source"] + " + linkedin"
                    time.sleep(0.5)  # be nice to the search backend

                # ---- 5. email pattern fallback ----
                if (not prospect["email"] or is_generic_email(prospect["email"])) \
                        and prospect["first_name"] and prospect["last_name"] and website:
                    dom = domain_of(website)
                    if dom:
                        cands = generate_email_candidates(prospect["first_name"],
                                                          prospect["last_name"], dom)
                        # If hunter is configured, verify the top candidate
                        if CONFIG.get("hunter_api_key"):
                            for c in cands[:3]:
                                v = hunter_verify(c, CONFIG["hunter_api_key"])
                                if v and v.get("result") in ("deliverable", "risky"):
                                    prospect["email"] = c
                                    break
                        else:
                            prospect["email"] = cands[0]   # best-guess pattern

                # ---- 6. owner-driven industry boost ----
                if prospect["industry"] in OWNER_DRIVEN_INDUSTRIES:
                    prospect["score"] = min(100, prospect["score"] + 5)

                # ---- 7. decision-maker score boost ----
                dm_boost = title_score(prospect["decision_maker_title"])
                prospect["score"] = min(100, prospect["score"] + dm_boost)

                # ---- 8. enforce min_score / titles_only filters ----
                if titles_only and not prospect["decision_maker_title"]:
                    continue
                if min_score and prospect["score"] < min_score:
                    continue

                enriched.append(prospect)
                tag = "DM" if prospect["decision_maker_title"] else "  "
                print(f"       [{tag}] score={prospect['score']:>3}  "
                      f"{prospect['decision_maker_name'] or '(no name)':20s}  "
                      f"{prospect['decision_maker_title'] or '-':22s}  "
                      f"{prospect['email'] or '(no email)'}")

    # ---- save cache ----
    try:
        cf.write_text(json.dumps({"seen": list(seen), "updated": datetime.now().isoformat()}))
    except Exception:
        pass

    # ---- write CSVs ----
    if enriched:
        enriched.sort(key=lambda p: p["score"], reverse=True)

        # Full enriched record
        super_fields = list(enriched[0].keys())
        with open(CONFIG["super_csv"], "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=super_fields)
            w.writeheader()
            w.writerows(enriched)

        # Drop-in replacement for prospects.csv (the dialer reads this)
        legacy_fields = ["id", "first_name", "last_name", "email", "phone",
                         "company", "industry", "city", "state", "zip", "employees",
                         "market", "score", "website", "address", "rating", "reviews",
                         "place_id", "source", "scraped_date", "opted_in_date"]
        legacy_rows = []
        for p in enriched:
            legacy_rows.append({
                "id":          p["id"],
                "first_name":  p["first_name"],
                "last_name":   p["last_name"],
                "email":       p["email"],
                "phone":       p["phone"],
                "company":     p["company"],
                "industry":    p["industry"],
                "city":        p["city"],
                "state":       p["state"],
                "zip":         p["zip"],
                "employees":   "",
                "market":      p["market"],
                "score":       p["score"],
                "website":     p["website"],
                "address":     p["address"],
                "rating":      p["rating"],
                "reviews":     p["reviews"],
                "place_id":    p["place_id"],
                "source":      p["discovery_source"],
                "scraped_date": p["scraped_date"],
                "opted_in_date": "",
            })
        # Merge with existing prospects.csv so we never overwrite earlier work
        existing = []
        if Path(CONFIG["output_csv"]).exists():
            try:
                with open(CONFIG["output_csv"], "r", encoding="utf-8-sig") as f:
                    existing = list(csv.DictReader(f))
            except Exception:
                existing = []
        existing_ids = {r.get("place_id", "") for r in existing}
        merged = existing + [r for r in legacy_rows if r["place_id"] not in existing_ids]
        with open(CONFIG["output_csv"], "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=legacy_fields)
            w.writeheader()
            w.writerows(merged)

        with open(CONFIG["raw_json"], "w", encoding="utf-8") as f:
            json.dump(enriched, f, indent=2)

    # ---- summary ----
    print("\n" + "=" * 64)
    print("SUPER SCRAPE COMPLETE")
    print("=" * 64)
    n = len(enriched)
    print(f"NEW enriched prospects:    {n}")
    print(f"Google Places API calls:   {api_calls}  (~${api_calls*0.025:.2f})")
    if n:
        with_phone   = sum(1 for p in enriched if p["phone"])
        with_email   = sum(1 for p in enriched if p["email"])
        with_real_email = sum(1 for p in enriched if p["email"] and not is_generic_email(p["email"]))
        with_dm      = sum(1 for p in enriched if p["decision_maker_title"])
        with_li      = sum(1 for p in enriched if p["linkedin_url"])
        avg          = sum(p["score"] for p in enriched) / n
        print(f"With phone:                {with_phone}/{n} ({with_phone*100//n}%)")
        print(f"With ANY email:            {with_email}/{n} ({with_email*100//n}%)")
        print(f"With NAMED email (not info@): {with_real_email}/{n} ({with_real_email*100//n}%)")
        print(f"With decision-maker title: {with_dm}/{n} ({with_dm*100//n}%)")
        print(f"With LinkedIn profile:     {with_li}/{n} ({with_li*100//n}%)")
        print(f"Avg MSP score:             {avg:.0f}/100")

        print("\nTop 10 prospects:")
        for p in enriched[:10]:
            who = p["decision_maker_name"] or "(unknown)"
            title = p["decision_maker_title"] or "-"
            print(f"  [{p['score']:>3}] {p['company'][:32]:32s} | {who[:22]:22s} | {title[:20]:20s} | {p['email']}")

    # ---- HubSpot push ----
    if hs and enriched:
        print("\nSyncing to HubSpot...")
        c_made = c_assoc = errs = 0
        for p in enriched:
            cid, cstatus = hs.upsert_company(p)
            if cstatus == "created":
                c_made += 1
            if p.get("email") or (p.get("first_name") and p.get("last_name")):
                _, status = hs.upsert_contact(p, company_id=cid)
                if status == "created":
                    c_assoc += 1
                elif status.startswith("err"):
                    errs += 1
            time.sleep(0.1)
        print(f"  HubSpot: {c_made} new companies, {c_assoc} new contacts, {errs} errors")

    # ---- Dialpad push ----
    if dp and enriched:
        print("\nSyncing to Dialpad...")
        d_ok = d_skip = 0
        for p in enriched:
            if not p.get("phone"):
                d_skip += 1; continue
            ok, _ = dp.create_contact(p)
            if ok:
                d_ok += 1
            else:
                d_skip += 1
            time.sleep(0.1)
        print(f"  Dialpad: {d_ok} contacts pushed, {d_skip} skipped")

    print(f"\nFiles written:")
    print(f"  {CONFIG['super_csv']}   (full enriched data — open in Excel)")
    print(f"  {CONFIG['output_csv']}  (merged into your dialer feed)")
    print(f"  {CONFIG['raw_json']}    (raw JSON for debugging)")
    print(f"\nDone at {datetime.now().strftime('%H:%M:%S')}")
    return enriched


# ============================================================
# CLI
# ============================================================
def main():
    p = argparse.ArgumentParser(description="BVTech MSP SUPER SCRAPER")
    p.add_argument("--market", choices=["austin", "san_antonio", "houston"])
    p.add_argument("--industry", help="filter by industry keyword (law, medical, ...)")
    p.add_argument("--max", type=int, default=100)
    p.add_argument("--deep", action="store_true",
                   help="Enable LinkedIn discovery + max-depth website crawl")
    p.add_argument("--titles-only", action="store_true",
                   help="Only keep prospects where we found a real decision-maker title")
    p.add_argument("--sync", action="store_true", help="Push results to HubSpot")
    p.add_argument("--dialer", action="store_true", help="Push results to Dialpad")
    p.add_argument("--require-phone", action="store_true")
    p.add_argument("--skip-solo", action="store_true")
    p.add_argument("--min-score", type=int, default=0)
    args = p.parse_args()

    run_super_scraper(
        market_filter=args.market,
        industry_filter=args.industry,
        max_results=args.max,
        deep=args.deep,
        titles_only=args.titles_only,
        sync_hubspot=args.sync,
        sync_dialer=args.dialer,
        require_phone=args.require_phone,
        skip_solo=args.skip_solo,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    main()
