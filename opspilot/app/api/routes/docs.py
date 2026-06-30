"""v0.54 Documentation & password vault — the IT Glue/Hudu surface.

Per-client documentation: knowledge articles, network/config notes, and an
encrypted password vault. Credentials are Fernet-encrypted at rest and only
returned via an explicit, audited reveal. Passwords/keys are staff-only; the
client's own users may read non-secret docs for their client.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Client, Document, DOC_KINDS, Role, User
from ...services import audit, crypto

router = APIRouter(prefix="/api/docs", tags=["documentation"])

_SECRET_KINDS = {"password", "license_key"}


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(d: Document) -> dict:
    return {
        "id": d.id, "client_id": d.client_id, "kind": d.kind, "title": d.title,
        "content": d.content, "username": d.username, "url": d.url,
        "tags": d.tags or [], "has_secret": bool(d.secret_enc),
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


@router.get("")
def list_docs(client_id: int | None = Query(None), kind: str | None = Query(None),
              q: str | None = Query(None), db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    query = db.query(Document)
    if is_staff(user):
        if client_id:
            query = query.filter(Document.client_id == client_id)
    else:
        # Client users: only their own client, and never the secret (password) kinds.
        query = query.filter(Document.client_id == user.client_id,
                             ~Document.kind.in_(list(_SECRET_KINDS)))
    if kind:
        query = query.filter(Document.kind == kind)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Document.title.ilike(like), Document.username.ilike(like),
                                 Document.content.ilike(like)))
    rows = query.order_by(Document.kind, Document.title).limit(500).all()
    return {"documents": [_serialize(d) for d in rows], "kinds": list(DOC_KINDS)}


class DocIn(BaseModel):
    client_id: int | None = None
    kind: str = "article"
    title: str
    content: str | None = None
    username: str | None = None
    url: str | None = None
    secret: str | None = None        # plaintext credential — encrypted on save
    tags: list[str] | None = None


@router.post("", status_code=201)
def create_doc(body: DocIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.title.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "title is required")
    if body.kind not in DOC_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"kind must be one of {DOC_KINDS}")
    if body.client_id is not None and not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    d = Document(client_id=body.client_id, kind=body.kind, title=body.title.strip(),
                 content=body.content, username=body.username, url=body.url,
                 tags=body.tags or [], created_by_user_id=user.id,
                 secret_enc=crypto.encrypt(body.secret) if body.secret else None)
    db.add(d)
    db.commit()
    db.refresh(d)
    audit.record(db, action="doc.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="document", target_id=str(d.id),
                 client_id=d.client_id, ip=_ip(request), detail=f"{d.kind}: {d.title}")
    return _serialize(d)


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not is_staff(user):
        assert_client_access(user, d.client_id)
        if d.kind in _SECRET_KINDS:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    return _serialize(d)


@router.post("/{doc_id}/reveal")
def reveal_secret(doc_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Return the decrypted credential — staff-only and AUDITED (who saw what)."""
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not d.secret_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This item has no stored secret")
    secret = crypto.decrypt(d.secret_enc)
    audit.record(db, action="doc.reveal", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="document", target_id=str(d.id),
                 client_id=d.client_id, ip=_ip(request), detail=f"revealed {d.title}")
    return {"id": d.id, "username": d.username, "secret": secret, "url": d.url}


class DocUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    username: str | None = None
    url: str | None = None
    secret: str | None = None        # set to update; omit to keep existing
    tags: list[str] | None = None


@router.patch("/{doc_id}")
def update_doc(doc_id: int, body: DocUpdate, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    data = body.model_dump(exclude_unset=True)
    if "secret" in data:
        secret = data.pop("secret")
        d.secret_enc = crypto.encrypt(secret) if secret else None
    for k, v in data.items():
        setattr(d, k, v)
    db.commit()
    audit.record(db, action="doc.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="document", target_id=str(d.id),
                 client_id=d.client_id, ip=_ip(request), detail=",".join(data.keys()) or "secret")
    return _serialize(d)


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER))):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    cid = d.client_id
    db.delete(d)
    db.commit()
    audit.record(db, action="doc.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="document", target_id=str(doc_id),
                 client_id=cid, ip=_ip(request))
