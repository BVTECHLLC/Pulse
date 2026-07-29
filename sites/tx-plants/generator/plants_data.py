#!/usr/bin/env python3
"""Texas Roots — build the full PLANTS dataset for v4.
Merges the 17 hand-authored rich entries (plants.py) with the ~111 structured
entries (plants_table.py), expanding the compact table rows into full dicts
that match the rendering schema. Exposes ALL_PLANTS and PLANT_CATS.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from plants import PLANTS as RICH_PLANTS, PLANT_CATS
from plants_table import PLANTS_TABLE
try:
    from new_plants import NEW_PLANTS
    PLANTS_TABLE = list(PLANTS_TABLE) + list(NEW_PLANTS)
except ImportError:
    pass
try:
    from more_plants import MORE_PLANTS
    PLANTS_TABLE = list(PLANTS_TABLE) + list(MORE_PLANTS)
except ImportError:
    pass

# field positions in each table row
(F_SLUG, F_COMMON, F_LATIN, F_FAMILY, F_CAT, F_TAGS, F_SUN, F_WATER, F_SOIL,
 F_PH, F_HARDY, F_HEIGHT, F_SPACING, F_DAYS, F_SUMMARY, F_USES, F_EPARTS,
 F_ECAUTION, F_ID1, F_ID2, F_ID3, F_COMP, F_INSHOP) = range(23)

def expand(row):
    tags = [t for t in row[F_TAGS].split() if t]
    in_shop = row[F_INSHOP].strip().lower() == "true"
    if in_shop and "in-shop" not in tags:
        tags.append("in-shop")

    # quick at-a-glance dict (skip empties)
    quick = {}
    for label, idx in [("Sun", F_SUN), ("Water", F_WATER), ("Soil", F_SOIL),
                       ("pH", F_PH), ("Hardiness", F_HARDY), ("Height", F_HEIGHT),
                       ("Spacing", F_SPACING), ("Days to harvest", F_DAYS)]:
        v = row[idx].strip()
        if v and v.upper() != "N/A":
            quick[label] = v

    # build long-form sections from the structured facts (varied, useful prose)
    common = row[F_COMMON]
    cat = row[F_CAT]
    sections = []
    sections.append(("What it is",
        f"{common} ({row[F_LATIN]}) is in the {row[F_FAMILY]} family. {row[F_SUMMARY]}"))
    grow_bits = []
    if row[F_SUN].strip(): grow_bits.append(f"It wants {row[F_SUN].lower()}")
    if row[F_WATER].strip(): grow_bits.append(f"water it {row[F_WATER].lower()}")
    if row[F_SOIL].strip(): grow_bits.append(f"and give it {row[F_SOIL].lower()} soil")
    if grow_bits:
        ph = f" Target a soil pH around {row[F_PH]}." if row[F_PH].strip() else ""
        sp = f" Space plants about {row[F_SPACING]} apart." if row[F_SPACING].strip() and row[F_SPACING].upper()!="N/A" else ""
        dh = f" Expect roughly {row[F_DAYS]}." if row[F_DAYS].strip() and row[F_DAYS].upper()!="N/A" else ""
        sections.append(("How to grow it",
            f"{', '.join(grow_bits)}.{ph}{sp}{dh} {row[F_HARDY]}."))
    if row[F_USES].strip():
        sections.append(("How it's used", f"{common} is used: {row[F_USES].lower()}."))

    # id marks
    id_marks = [m for m in (row[F_ID1], row[F_ID2], row[F_ID3]) if m.strip()]

    # edible
    eparts = row[F_EPARTS].strip()
    edible = None
    if eparts and "not a food" not in eparts.lower() and "not edible" not in eparts.lower() and "not for eating" not in eparts.lower():
        edible = {"parts": eparts, "uses": row[F_USES].strip(),
                  "caution": row[F_ECAUTION].strip() or "None of note."}

    companions = [c.strip() for c in row[F_COMP].split(";") if c.strip()]

    return {
        "slug": row[F_SLUG], "common": common, "latin": row[F_LATIN],
        "family": row[F_FAMILY], "category": cat, "tags": tags,
        "summary": row[F_SUMMARY], "quick": quick, "sections": sections,
        "id_marks": id_marks,
        "lookalikes": [],   # rich entries have these; table entries focus elsewhere
        "edible": edible, "companion": companions,
        "in_shop": in_shop, "sku_hint": (row[F_USES][:40] if in_shop else ""),
    }

# merge: rich first, then table — dedupe by slug (rich wins)
seen = {p["slug"] for p in RICH_PLANTS}
expanded = []
for row in PLANTS_TABLE:
    if row[F_SLUG] in seen:
        continue
    seen.add(row[F_SLUG])
    expanded.append(expand(row))

ALL_PLANTS = list(RICH_PLANTS) + expanded

if __name__ == "__main__":
    from collections import Counter
    print("rich:", len(RICH_PLANTS), "table-expanded:", len(expanded),
          "total:", len(ALL_PLANTS))
    print(Counter(p["category"] for p in ALL_PLANTS))
    print("in_shop:", sum(1 for p in ALL_PLANTS if p["in_shop"]))
