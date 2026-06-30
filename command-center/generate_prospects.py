#!/usr/bin/env python3
"""
BVTech Prospect List Generator
================================
Generates prospect lists for Austin, San Antonio, and Houston markets.

In PRODUCTION, this would connect to:
  - Google Maps Places API (business names, phones, websites)
  - Hunter.io / Apollo.io (verified email addresses)
  - LinkedIn Sales Navigator (decision maker names)
  - Texas SOS SOSDirect bulk data (registered businesses)

For NOW, this generates realistic sample data you can test with,
then swap in real APIs when ready.

USAGE:
    python3 generate_prospects.py                    # Generate 500 prospects
    python3 generate_prospects.py --count 1000       # Custom count
    python3 generate_prospects.py --market austin     # Single market
"""

import csv
import random
import argparse
from pathlib import Path

MARKETS = {
    "austin": {"name": "Austin", "area_code": "512", "zips": [
        "78701","78702","78703","78704","78705","78721","78723","78741","78745",
        "78748","78749","78750","78751","78752","78753","78757","78758","78759"
    ]},
    "sanAntonio": {"name": "San Antonio", "area_code": "210", "zips": [
        "78201","78202","78204","78205","78207","78210","78211","78212","78213",
        "78214","78215","78216","78217","78218","78220","78221","78223","78224",
        "78225","78227","78228","78229","78230","78231","78232","78233","78240",
        "78245","78247","78248","78249","78250","78251","78253","78254","78256"
    ]},
    "houston": {"name": "Houston", "area_code": "713", "zips": [
        "77001","77002","77003","77004","77005","77006","77007","77008","77009",
        "77010","77011","77019","77020","77021","77024","77025","77027","77030",
        "77035","77036","77040","77042","77043","77055","77056","77057","77058",
        "77059","77060","77062","77063","77064","77065","77070","77077","77079",
        "77080","77082","77084","77090","77094","77095","77096","77098","77099"
    ]},
}

INDUSTRIES = [
    "Accounting & CPA Firms", "Law Firms", "Medical Offices",
    "Dental Offices", "Real Estate Agencies", "Insurance Agencies",
    "Construction Companies", "Manufacturing", "Financial Advisors",
    "Architecture Firms", "Engineering Firms", "Marketing Agencies",
    "Logistics & Freight", "Oil & Gas Services", "Property Management",
    "Staffing Agencies", "Auto Dealerships", "Veterinary Clinics",
    "Restaurants (Multi-location)", "Retail (Local Chain)"
]

FIRST_NAMES = [
    "James","Robert","Michael","David","William","Richard","Joseph","Thomas",
    "Christopher","Daniel","Matthew","Anthony","Mark","Steven","Paul","Andrew",
    "Kenneth","Joshua","Kevin","Brian","George","Timothy","Ronald","Edward",
    "Jason","Jeffrey","Ryan","Jacob","Gary","Nicholas","Eric","Jonathan",
    "Stephen","Larry","Justin","Scott","Brandon","Benjamin","Samuel","Raymond",
    "Maria","Jennifer","Linda","Patricia","Elizabeth","Barbara","Susan","Jessica",
    "Sarah","Karen","Lisa","Nancy","Betty","Margaret","Sandra","Ashley",
    "Kimberly","Emily","Donna","Michelle","Dorothy","Carol","Amanda","Melissa",
    "Carlos","Jose","Juan","Miguel","Luis","Rafael","Alejandro","Fernando",
]

LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
    "Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson",
    "White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker",
    "Young","Allen","King","Wright","Torres","Nguyen","Hill","Flores","Green",
    "Adams","Nelson","Baker","Rivera","Campbell","Mitchell","Carter","Roberts",
]

COMPANY_PREFIXES = [
    "Texas","Lone Star","Gulf Coast","Metro","Capital","Alamo","Hill Country",
    "Frontier","Summit","Horizon","Pinnacle","Apex","Sterling","Heritage",
    "Legacy","Premier","Elite","Prime","Central","Pacific","Southern",
    "Crossroads","Bluebonnet","Brazos","Trinity","Pecan","Magnolia",
]

COMPANY_SUFFIXES = {
    "Accounting & CPA Firms": ["Accounting","CPA Group","Tax Advisory","Financial Services"],
    "Law Firms": ["Law Group","Legal Associates","Law Firm","Attorneys at Law"],
    "Medical Offices": ["Medical Group","Health Partners","Medical Associates","Wellness"],
    "Dental Offices": ["Dental Care","Dental Group","Dentistry","Smile Center"],
    "Real Estate Agencies": ["Realty","Real Estate Group","Properties","Homes"],
    "Insurance Agencies": ["Insurance","Insurance Group","Risk Advisors","Coverage"],
    "Construction Companies": ["Construction","Builders","General Contractors","Development"],
    "Manufacturing": ["Manufacturing","Industries","Fabrication","Products Inc"],
    "Financial Advisors": ["Financial Advisors","Wealth Management","Capital","Investments"],
    "Architecture Firms": ["Architecture","Design Studio","Architects","Design Group"],
    "Engineering Firms": ["Engineering","Engineers","Technical Services","Engineering Group"],
    "Marketing Agencies": ["Marketing","Creative Agency","Media Group","Digital Agency"],
    "Logistics & Freight": ["Logistics","Freight","Transport","Supply Chain"],
    "Oil & Gas Services": ["Energy Services","Oil & Gas","Petroleum","Energy Solutions"],
    "Property Management": ["Property Management","PM Group","Asset Management"],
    "Staffing Agencies": ["Staffing","Talent Solutions","Recruitment","Personnel"],
    "Auto Dealerships": ["Motors","Auto Group","Automotive","Auto Sales"],
    "Veterinary Clinics": ["Vet Clinic","Animal Hospital","Pet Care","Veterinary"],
    "Restaurants (Multi-location)": ["Restaurant Group","Dining","Food Co","Hospitality"],
    "Retail (Local Chain)": ["Retail","Stores","Marketplace","Trading Co"],
}


def generate_email(first, last, company):
    """Generate a realistic business email."""
    domain = company.lower().replace(" ", "").replace("&","").replace(",","")
    domain = domain[:20] + ".com"
    formats = [
        f"{first.lower()}.{last.lower()}@{domain}",
        f"{first[0].lower()}{last.lower()}@{domain}",
        f"{first.lower()}@{domain}",
        f"{first.lower()}{last[0].lower()}@{domain}",
    ]
    return random.choice(formats)


def generate_phone(area_code):
    """Generate a realistic phone number."""
    return f"+1{area_code}{random.randint(2000000, 9999999)}"


def generate_prospects(count, markets=None, industries=None):
    """Generate a list of prospect dictionaries."""
    if markets is None:
        markets = list(MARKETS.keys())
    if industries is None:
        industries = INDUSTRIES

    prospects = []
    for i in range(count):
        market_key = markets[i % len(markets)]
        market = MARKETS[market_key]
        industry = random.choice(industries)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        prefix = random.choice(COMPANY_PREFIXES)
        suffixes = COMPANY_SUFFIXES.get(industry, ["Services"])
        suffix = random.choice(suffixes)
        company = f"{prefix} {suffix}"
        employees = random.randint(5, 150)
        score = random.randint(10, 100)

        prospects.append({
            "id": f"P{i+1:05d}",
            "first_name": first,
            "last_name": last,
            "email": generate_email(first, last, company),
            "phone": generate_phone(market["area_code"]),
            "company": company,
            "industry": industry,
            "city": market["name"],
            "state": "TX",
            "zip": random.choice(market["zips"]),
            "employees": employees,
            "market": market_key,
            "score": score,
            "opted_in_date": "",  # Must be filled for SMS (TCPA)
            "source": "generated",
        })

    return prospects


def save_csv(prospects, filename):
    """Save prospects to CSV."""
    if not prospects:
        return
    fieldnames = prospects[0].keys()
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(prospects)
    print(f"✅ Saved {len(prospects)} prospects to {filename}")


def main():
    parser = argparse.ArgumentParser(description="BVTech Prospect List Generator")
    parser.add_argument("--count", type=int, default=500, help="Number of prospects")
    parser.add_argument("--market", help="Single market (austin/sanAntonio/houston)")
    args = parser.parse_args()

    markets = [args.market] if args.market else None
    prospects = generate_prospects(args.count, markets)

    # Save main prospects file (used by email + dialer)
    save_csv(prospects, "prospects.csv")

    # Save SMS-specific file (reminder about opt-in)
    save_csv(prospects, "sms_prospects.csv")
    print("\n⚠️  IMPORTANT: sms_prospects.csv has empty 'opted_in_date' fields.")
    print("   You MUST fill in actual opt-in dates for TCPA compliance.")
    print("   The SMS engine will skip contacts without opt-in dates.\n")

    # Print summary
    by_market = {}
    by_industry = {}
    for p in prospects:
        m = p["city"]
        by_market[m] = by_market.get(m, 0) + 1
        ind = p["industry"]
        by_industry[ind] = by_industry.get(ind, 0) + 1

    print(f"\n📊 Summary: {len(prospects)} total prospects\n")
    print("By Market:")
    for m, c in sorted(by_market.items()):
        print(f"  {m}: {c}")
    print("\nTop Industries:")
    for ind, c in sorted(by_industry.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ind}: {c}")


if __name__ == "__main__":
    main()
