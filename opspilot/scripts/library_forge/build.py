"""Library Forge — assemble and render the BVTech document library expansion.

Run from opspilot/:  python3 scripts/library_forge/build.py

Renders every doc spec from the content modules into app/library/files/ and
merges them into app/library/manifest.json (existing entries are preserved
verbatim; the forge only appends what is missing). Finishes with a freshly
generated Complete Library Catalog document covering the entire suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import content_compliance   # noqa: E402
import content_ops          # noqa: E402
import content_vertical     # noqa: E402
import layout               # noqa: E402

APP = HERE.parents[1] / "app"
FILES = APP / "library" / "files"
MANIFEST = APP / "library" / "manifest.json"


def main() -> None:
    docs = (content_compliance.build() + content_vertical.build()
            + content_ops.build())
    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids)), "duplicate forge ids"
    manifest = json.loads(MANIFEST.read_text())
    items = manifest.get("items", [])
    have = {it["doc_id"] for it in items}
    clash = [i for i in ids if i in have]
    assert not clash, f"forge ids clash with existing manifest: {clash}"

    rendered = 0
    for d in docs:
        fname = layout.render(d, FILES)
        size = (FILES / fname).stat().st_size
        assert size > 1800, f"{d['id']} rendered suspiciously small ({size}B)"
        items.append({"doc_id": d["id"], "title": d["title"],
                      "category": d["category"],
                      "category_label": d["category_label"],
                      "visibility": d["visibility"], "filename": fname,
                      "size": size})
        rendered += 1

    # complete catalog over the ENTIRE library (old + new)
    by_cat: dict[str, list] = {}
    for it in items:
        by_cat.setdefault(it.get("category_label") or it.get("category", "?"),
                          []).append(it)
    cat_doc = {
        "id": "BVT-CAT-999", "slug": "Complete_Library_Catalog",
        "title": f"Complete Library Catalog ({len(items) + 1} documents)",
        "category": "000", "category_label": "Library Index",
        "visibility": "client", "kind": "policy",
        "summary": "Every document in the BVTech MSP library, grouped by category. "
                   "Internal documents are staff-only in the portal; client-shareable "
                   "documents appear in client accounts automatically.",
        "sections": [],
    }
    for label in sorted(by_cat):
        rows = [[it["doc_id"], it["title"][:76],
                 "Client-shareable" if it["visibility"] == "client" else "Internal"]
                for it in sorted(by_cat[label], key=lambda x: x["doc_id"])]
        cat_doc["sections"].append(
            {"h": f"{label} ({len(rows)})", "kind": "table",
             "headers": ["Doc ID", "Title", "Visibility"],
             "widths": [30, 116, 34], "body": rows})
    fname = layout.render(cat_doc, FILES)
    items = [it for it in items if it["doc_id"] != "BVT-CAT-999"]
    items.append({"doc_id": "BVT-CAT-999", "title": cat_doc["title"],
                  "category": "000", "category_label": "Library Index",
                  "visibility": "client", "filename": fname,
                  "size": (FILES / fname).stat().st_size})

    manifest["items"] = items
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    print(f"forge: rendered {rendered} new documents + catalog; "
          f"library now {len(items)} documents, "
          f"{sum(1 for i in items if i['visibility'] == 'client')} client-shareable")


if __name__ == "__main__":
    main()
