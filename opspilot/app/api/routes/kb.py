"""IT documentation / knowledge base.

Articles are authored by staff. Scope rules:
  - client_id NULL  => global article (applies to all clients)
  - client_id set   => specific to that client
  - visibility 'internal' => staff only
  - visibility 'client'   => visible to that client's portal users (and staff)

A client user sees: client-visible globals + client-visible articles for THEIR
client. They never see internal docs or other clients' docs. Staff see all.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Client, KBArticle, Role, User
from ...services import audit

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])

VISIBILITIES = ("internal", "client")


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(a: KBArticle, include_body: bool = True) -> dict:
    d = {
        "id": a.id, "client_id": a.client_id, "title": a.title, "category": a.category,
        "visibility": a.visibility, "author_email": a.author_email,
        "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(),
    }
    if include_body:
        d["body"] = a.body
    return d


def _visible_filter(user: User):
    """SQLAlchemy filter limiting a client user to docs they're allowed to read."""
    return (KBArticle.visibility == "client") & (
        KBArticle.client_id.is_(None) | (KBArticle.client_id == user.client_id)
    )


class ArticleIn(BaseModel):
    title: str
    body: str
    category: str | None = None
    client_id: int | None = None
    visibility: str = "internal"


@router.get("")
def list_articles(category: str | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    q = db.query(KBArticle)
    if not is_staff(user):
        q = q.filter(_visible_filter(user))
    if category:
        q = q.filter(KBArticle.category == category)
    rows = q.order_by(KBArticle.category, KBArticle.title).all()
    # List view omits the (potentially large) body.
    return [_serialize(a, include_body=False) for a in rows]


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    a = db.get(KBArticle, article_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    if not is_staff(user):
        visible = a.visibility == "client" and a.client_id in (None, user.client_id)
        if not visible:
            # Don't reveal existence of internal/other-client docs.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    return _serialize(a)


@router.post("", status_code=201)
def create_article(body: ArticleIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.visibility not in VISIBILITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid visibility")
    if not body.title.strip() or not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Title and body required")
    if body.client_id is not None and not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    a = KBArticle(title=body.title.strip(), body=body.body, category=body.category,
                  client_id=body.client_id, visibility=body.visibility,
                  created_by_user_id=user.id, author_email=user.email)
    db.add(a)
    db.commit()
    audit.record(db, action="kb.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="kb_article", target_id=str(a.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"title={a.title[:60]}")
    return {"id": a.id}


class ArticleUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    category: str | None = None
    visibility: str | None = None
    client_id: int | None = None


@router.patch("/{article_id}")
def update_article(article_id: int, body: ArticleUpdate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    a = db.get(KBArticle, article_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    if body.visibility is not None:
        if body.visibility not in VISIBILITIES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid visibility")
        a.visibility = body.visibility
    if body.title is not None:
        a.title = body.title.strip()
    if body.body is not None:
        a.body = body.body
    if body.category is not None:
        a.category = body.category
    if body.client_id is not None:
        a.client_id = body.client_id or None
    db.commit()
    audit.record(db, action="kb.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="kb_article", target_id=str(a.id),
                 client_id=a.client_id, ip=_ip(request))
    return {"ok": True}


@router.delete("/{article_id}")
def delete_article(article_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    """Hard delete — owner only. KB docs aren't an audit record, so unlike the
    audit log they may be removed; the deletion itself is audited."""
    a = db.get(KBArticle, article_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    cid, title = a.client_id, a.title
    db.delete(a)
    db.commit()
    audit.record(db, action="kb.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="kb_article", target_id=str(article_id),
                 client_id=cid, ip=_ip(request), detail=f"title={title[:60]}")
    return {"ok": True}
