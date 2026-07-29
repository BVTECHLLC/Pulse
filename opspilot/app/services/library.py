"""v0.97 Document Library — the BVTech MSP/MSSP document suite, permission-scoped.

Files live in ``app/library/files``; a ``LibraryDoc`` row per file carries the
metadata + a visibility that gates access:
    internal → staff (OWNER/TECH) only
    client   → staff AND client users

The catalog is seeded from ``app/library/manifest.json`` on boot (missing entries
only, so an owner re-classifying a doc in the UI is never overwritten). Downloads
are streamed through an authenticated route that re-checks visibility and only
serves a filename that exists in the catalog (no path traversal).
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import is_staff
from ..models import LibraryDoc, User

_BASE = Path(__file__).resolve().parents[1] / "library"
FILES_DIR = _BASE / "files"
MANIFEST = _BASE / "manifest.json"

VISIBILITIES = ("internal", "client")

# Category display order for the grouped view. v1.60 adds the Library Forge
# sets: NIST 800-171 (CMP), CSF 2.0 (CSF), standards (STD), vertical packs
# (VRT), Texas legal (TXL), checklists (CHK), extended SOPs, awareness (TRN),
# forms (FRM), and service descriptions (SVC).
_CAT_ORDER = ["000", "LGL", "TXL", "SEC", "CMP", "CSF", "STD", "VRT", "POL",
              "IRP", "CHK", "OPS", "SOP", "RUN", "TRN", "FRM", "SVC", "INT"]


def load_manifest() -> list[dict]:
    try:
        return (json.loads(MANIFEST.read_text()) or {}).get("items", [])
    except Exception:
        return []


def seed(db: Session) -> int:
    """Insert any manifest doc not yet in the table. Returns how many were added.
    Never updates existing rows, so owner visibility edits persist."""
    items = load_manifest()
    if not items:
        return 0
    have = {d for (d,) in db.execute(select(LibraryDoc.doc_id)).all()}
    added = 0
    for it in items:
        if it.get("doc_id") in have:
            continue
        vis = it.get("visibility") if it.get("visibility") in VISIBILITIES else "internal"
        db.add(LibraryDoc(
            doc_id=it["doc_id"], title=it.get("title", it["doc_id"])[:200],
            category=it.get("category", "")[:20], category_label=it.get("category_label", "")[:80],
            visibility=vis, filename=it["filename"][:200], size=it.get("size")))
        added += 1
    if added:
        db.commit()
    return added


def _serialize(d: LibraryDoc, *, staff: bool) -> dict:
    out = {
        "id": d.id, "doc_id": d.doc_id, "title": d.title,
        "category": d.category, "category_label": d.category_label,
        "size": d.size, "download_url": f"/api/library/{d.doc_id}/download",
    }
    if staff:
        out["visibility"] = d.visibility     # only staff see/manage the classification
    return out


def list_for(db: Session, user: User) -> dict:
    """Docs the user may see, grouped by category (in a sensible order)."""
    staff = is_staff(user)
    q = select(LibraryDoc).order_by(LibraryDoc.doc_id)
    if not staff:
        q = q.where(LibraryDoc.visibility == "client")
    rows = db.execute(q).scalars().all()
    groups: dict[str, dict] = {}
    for d in rows:
        g = groups.setdefault(d.category, {"category": d.category,
                                           "category_label": d.category_label, "docs": []})
        g["docs"].append(_serialize(d, staff=staff))
    ordered = sorted(groups.values(),
                     key=lambda g: (_CAT_ORDER.index(g["category"]) if g["category"] in _CAT_ORDER else 99))
    counts = {"total": len(rows)}
    if staff:
        counts["client_visible"] = sum(1 for d in rows if d.visibility == "client")
        counts["internal"] = sum(1 for d in rows if d.visibility == "internal")
    return {"groups": ordered, "counts": counts}


def get_doc(db: Session, doc_id: str) -> LibraryDoc | None:
    return db.execute(select(LibraryDoc).where(LibraryDoc.doc_id == doc_id)).scalar_one_or_none()


def can_access(user: User, doc: LibraryDoc) -> bool:
    return is_staff(user) or doc.visibility == "client"


def resolve_path(doc: LibraryDoc) -> Path | None:
    """Safe absolute path to the doc's file — only within FILES_DIR, only a
    basename (defensive against traversal via a tampered filename)."""
    name = Path(doc.filename).name          # strip any directory components
    p = (FILES_DIR / name).resolve()
    try:
        p.relative_to(FILES_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def set_visibility(db: Session, doc: LibraryDoc, visibility: str) -> LibraryDoc:
    if visibility not in VISIBILITIES:
        raise ValueError("visibility must be 'internal' or 'client'")
    doc.visibility = visibility
    db.commit()
    db.refresh(doc)
    return doc
