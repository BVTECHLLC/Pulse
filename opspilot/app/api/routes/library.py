"""v0.97 Document Library routes.

  GET  /api/library                     list docs the caller may see (grouped)
  GET  /api/library/{doc_id}/download   stream the PDF (visibility-checked)
  PATCH/api/library/{doc_id}/visibility  owner: reclassify internal<->client

Any authenticated user can read; clients only ever see + download `client` docs.
Reclassification is owner-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, require_roles
from ...models import Role, User
from ...services import audit, library

router = APIRouter(prefix="/api/library", tags=["library"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


@router.get("")
def list_library(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return library.list_for(db, user)


@router.get("/{doc_id}/download")
def download(doc_id: str, request: Request, db: Session = Depends(get_db),
             user: User = Depends(current_user)):
    doc = library.get_doc(db, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not library.can_access(user, doc):
        # Don't reveal that an internal doc exists to a client.
        raise HTTPException(404, "Document not found")
    path = library.resolve_path(doc)
    if not path:
        raise HTTPException(404, "File not available")
    audit.record(db, action="library.download", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="library_doc", target_id=doc.doc_id,
                 client_id=user.client_id, ip=_ip(request), detail=doc.title[:120])
    return FileResponse(str(path), media_type="application/pdf",
                        filename=doc.filename, content_disposition_type="inline")


class VisibilityIn(BaseModel):
    visibility: str


@router.patch("/{doc_id}/visibility")
def set_visibility(doc_id: str, body: VisibilityIn, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER))):
    doc = library.get_doc(db, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    try:
        library.set_visibility(db, doc, body.visibility)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.record(db, action="library.visibility", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="library_doc", target_id=doc.doc_id,
                 ip=_ip(request), detail=f"{doc.doc_id} -> {doc.visibility}")
    return {"doc_id": doc.doc_id, "visibility": doc.visibility}
