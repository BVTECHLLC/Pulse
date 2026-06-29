"""v0.34 Content Studio API — generate publish-ready BVTech.org pages.

Staff compose a blog/advisory (title + lightweight-markdown body); we return the
finished, on-brand HTML plus the filename/URL it should publish to. The actual
push to the live site is a separate, infra-specific step (git push → Cloudflare
Pages, or rsync to the box) wired once the website repo is connected.

Public-safe by construction: these are threat/advisory/insight articles — no
tenant data is ever embedded.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ...core.deps import require_roles
from ...models import Role, User
from ...services import content_studio as cs

router = APIRouter(prefix="/api/content", tags=["content-studio"])


class PostIn(BaseModel):
    title: str
    body: str = ""
    kind: str = "blog"            # blog | advisory
    slug: str | None = None
    description: str | None = None
    keywords: str | None = None
    author: str | None = None
    date: str | None = None


def _meta(post: PostIn) -> dict:
    p = cs.normalize_post(post.model_dump())
    return {"slug": p["slug"], "filename": f"{p['slug']}.html",
            "url": p["url"], "title": p["title"], "description": p["description"],
            "publish_path": f"blog/{p['slug']}.html"}


@router.post("/render")
def render_post(post: PostIn, user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Return the finished HTML + where it publishes to (JSON)."""
    try:
        html = cs.render_standalone(post.model_dump())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return {**_meta(post), "html": html, "bytes": len(html)}


@router.post("/preview", response_class=HTMLResponse)
def preview_post(post: PostIn, request: Request,
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Render the post as a live HTML page for an in-portal preview iframe."""
    try:
        return HTMLResponse(cs.render_standalone(post.model_dump()))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/stage")
def stage_post(post: PostIn, user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Compute the publish target for a post (slug, filename, path, URL). The
    audit middleware logs this POST automatically; the deploy step (git push →
    Cloudflare Pages / rsync to the box) consumes the returned path so that
    publishing to the public site is always an explicit, logged action."""
    try:
        return {"staged": True, **_meta(post)}
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
