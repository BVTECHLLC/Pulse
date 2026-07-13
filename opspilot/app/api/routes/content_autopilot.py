"""v1.20 Content Autopilot API — one-click daily posting to all four channels."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, content_autopilot, jp_site

router = APIRouter(prefix="/api/content-autopilot", tags=["content-autopilot"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


@router.get("/status")
def get_status(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return content_autopilot.status(db)


class SettingsIn(BaseModel):
    enabled: bool | None = None
    hour_utc: int | None = None
    channels: dict[str, bool] | None = None


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    return content_autopilot.save_config(db, enabled=body.enabled,
                                         hour_utc=body.hour_utc, channels=body.channels)


class JpIn(BaseModel):
    project: str | None = None
    token: str | None = None
    branch: str | None = None


@router.put("/jp-site")
def put_jp(body: JpIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER))):
    if body.project is None and body.token is None and body.branch is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to save.")
    return jp_site.save_config(db, site="jp", project=body.project, token=body.token,
                               branch=body.branch)


class SitesIn(BaseModel):
    token: str | None = None            # ONE token connects both sites
    jp_project: str | None = None
    bvtech_project: str | None = None
    branch: str | None = None


@router.put("/sites")
def put_sites(body: SitesIn, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER))):
    """One-paste connect: a single GitLab token (api scope) lights up BOTH site
    publishers. Projects default to the known repos; override if they move."""
    if not any([body.token, body.jp_project, body.bvtech_project, body.branch]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to save.")
    if body.token:
        jp_site.save_shared_token(db, body.token)
    if body.jp_project or body.branch:
        jp_site.save_config(db, site="jp", project=body.jp_project, branch=body.branch)
    if body.bvtech_project or body.branch:
        jp_site.save_config(db, site="bvtech", project=body.bvtech_project,
                            branch=body.branch)
    return {"jp": jp_site.get_config(db, "jp")["configured"],
            "bvtech": jp_site.get_config(db, "bvtech")["configured"],
            "jp_project": jp_site.get_config(db, "jp")["project"],
            "bvtech_project": jp_site.get_config(db, "bvtech")["project"]}


@router.post("/test-sites")
def test_sites(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Prove the GitLab token works against BOTH site repos — read-only, and the
    per-site error explains exactly what's wrong (bad token, wrong scope, no
    access to a repo) instead of failing at tomorrow's post."""
    out = {}
    for site in ("bvtech", "jp"):
        cfg = jp_site.get_config(db, site)
        if not cfg["configured"]:
            out[site] = {"ok": False, "error": "no token found (paste one above, or "
                                               "add it to the server env)"}
            continue
        try:
            import urllib.parse as _up
            proj = jp_site._HTTP("GET", f"{cfg['base']}/api/v4/projects/"
                                 f"{_up.quote_plus(cfg['project'])}", cfg["token"])
            out[site] = {"ok": True, "project": proj.get("path_with_namespace") or cfg["project"],
                         "default_branch": proj.get("default_branch")}
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "401" in msg:
                msg = "token rejected (401) — expired or wrong token"
            elif "403" in msg:
                msg = "token lacks access (403) — needs `api` scope + repo access"
            elif "404" in msg:
                msg = f"repo not found ({cfg['project']}) — token can't see it or path is wrong"
            out[site] = {"ok": False, "error": msg[:200]}
    return out


@router.post("/run-now")
def run_now(request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER))):
    """Post to every enabled channel right now (ignores hour + daily dedupe)."""
    out = content_autopilot.run_daily(db, force=True)
    audit.record(db, action="content_autopilot.run_now", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="content", ip=_ip(request),
                 detail=str({k: v["ok"] for k, v in out.get("results", {}).items()})[:200])
    return out


_TICK_STATE = {"last": 0.0}   # in-memory rate limit for the external tick


@router.post("/tick")
def external_tick(request: Request, db: Session = Depends(get_db)):
    """External daily trigger — the belt-and-braces twin of the in-process
    scheduler. A GitHub Actions cron (daily-content.yml) calls this every day;
    even if the portal's background thread ever dies, the day's posts still go
    out. SAFE WITHOUT AUTH BY DESIGN: it only runs the NON-FORCE daily path, so
    every gate applies (enabled, hour window, once-per-day dedupe) — hammering
    it can never post twice or post early. Optional shared secret: set
    CONTENT_TICK_KEY in the server env and the same value as a GitHub secret,
    and the header becomes required. Rate-limited to one attempt/minute."""
    import os as _os
    import time as _time
    required = _os.environ.get("CONTENT_TICK_KEY")
    if required and request.headers.get("x-tick-key") != required:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad or missing X-Tick-Key")
    now_m = _time.monotonic()
    if now_m - _TICK_STATE["last"] < 60:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Tick already ran <60s ago")
    _TICK_STATE["last"] = now_m
    out = content_autopilot.run_daily(db)          # non-force: all gates apply
    return {"ran": out.get("ran"), "reason": out.get("reason"),
            "results": {k: v.get("ok") for k, v in (out.get("results") or {}).items()}}


@router.post("/diagnose")
def diagnose(db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Publishing Doctor: walk the whole publish chain per site (token -> repo ->
    listing structure -> orphaned posts -> deploy pipeline -> Cloudflare purge)
    and the autopilot schedule, and say exactly what to fix. Read-only."""
    cfg = content_autopilot.get_config(db)
    # Scheduler pulse: is the background engine actually ticking on this box?
    from datetime import datetime, timezone
    from ...models import SchedulerRun
    _last = db.query(SchedulerRun).order_by(SchedulerRun.id.desc()).first()
    _age = None
    if _last and _last.ran_at:
        _ran = _last.ran_at if _last.ran_at.tzinfo else _last.ran_at.replace(tzinfo=timezone.utc)
        _age = int((datetime.now(timezone.utc) - _ran).total_seconds())
    scheduler_ok = _age is not None and _age < 360
    out = {"scheduler": {
               "ok": scheduler_ok,
               "detail": (f"ticking - last heartbeat {_age}s ago" if scheduler_ok else
                          "NOT ticking" + (f" - last heartbeat {_age}s ago" if _age is not None
                                           else " - no heartbeat recorded yet")),
               **({} if scheduler_ok else
                  {"fix": "the app's background scheduler isn't running - the daily GitHub "
                          "cron still posts, but restart the api container to restore full "
                          "automation (docker compose restart api)"})},
           "sites": [jp_site.diagnose(db, s) for s in ("bvtech", "jp")],
           "autopilot": {
               "enabled": cfg["enabled"],
               "hour_utc": cfg["hour_utc"],
               "detail": ("daily posting is ON - posts go out at "
                          f"{cfg['hour_utc']:02d}:00 UTC" if cfg["enabled"] else
                          "daily posting is OFF - only 'Post to all now' publishes; "
                          "flip the Autopilot toggle to post every day automatically"),
               "last": cfg["last"], "last_error": cfg["last_error"]}}
    from ...services import ai as _ai
    out["ai"] = {"ok": _ai.enabled(),
                 "detail": "Claude connected" if _ai.enabled() else
                           "Claude NOT connected - the writers can't generate (Connection Center -> Claude)"}
    # Social channels — live checks so errors like Google's "invalid_client"
    # show up HERE with the fix, not buried in a failed post's result string.
    from ...services import integration_health, secure_config
    from ...models import OAuthToken
    channels = []
    li_conn = secure_config.get_platform(db, "pub_linkedin")
    li_cfg = (li_conn.config if li_conn else None) or {}
    li_ok = bool(secure_config.get_secret(li_cfg, "access_token")
                 or db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count())
    channels.append({"name": "LinkedIn", "ok": li_ok,
                     "detail": "connected" if li_ok else "not connected",
                     **({} if li_ok else {"fix": "Settings -> One-click Connect -> LinkedIn"})})
    gbp_conn = secure_config.get_platform(db, "gbp")
    gbp_cfg = (gbp_conn.config if gbp_conn else None) or {}
    try:
        st, det = integration_health.CHECKERS["gbp"](gbp_cfg)
        gbp_ok, gbp_det = (st == "ok"), det
    except Exception as e:  # noqa: BLE001
        gbp_ok, gbp_det = False, str(e)[:220]
    fix = None
    if not gbp_ok:
        low = gbp_det.lower()
        if "invalid_client" in low or "oauth client was not found" in low:
            fix = ("Google rejected the OAuth client (invalid_client) - the client id/secret "
                   "stored here no longer exist in Google Cloud. Re-create an OAuth client "
                   "(console.cloud.google.com -> APIs & Services -> Credentials), update the "
                   "Google Business connector, then reconnect via Settings -> One-click Connect.")
        elif "invalid_grant" in low:
            fix = "The Google refresh token was revoked/expired - reconnect via Settings -> One-click Connect."
        elif "not configured" in low:
            fix = "Settings -> Google Business Profile: connect + pick your location."
    channels.append({"name": "Google Business", "ok": gbp_ok, "detail": gbp_det,
                     **({"fix": fix} if fix else {})})
    out["channels"] = channels
    return out


@router.post("/sync-listings")
def sync_listings(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    """Backfill: add every published-but-unlisted post to the blog listings
    (one commit per site) and purge the Cloudflare cache. Fixes posts published
    before v1.28 that are live at their URL but invisible in navigation."""
    out = {}
    for site in ("bvtech", "jp"):
        out[site] = jp_site.sync_listings(db, site)
    audit.record(db, action="content_autopilot.sync_listings", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="content", ip=_ip(request),
                 detail=str({k: len(v.get("added", [])) if v.get("ok") else v.get("error", "?")[:40]
                             for k, v in out.items()})[:200])
    return out


class CustomPostIn(BaseModel):
    channel: str                       # bvtech | jp | linkedin | gbp
    title: str | None = None           # required for site posts
    html: str | None = None            # rendered article body (sites) or post text
    body: str | None = None            # lightweight markdown (sites) or post text
    excerpt: str | None = None
    slug: str | None = None
    keywords: str | None = None
    kind: str | None = None            # blog | advisory
    link: str | None = None


@router.post("/publish-custom")
def publish_custom(body: CustomPostIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    """Publish ONE specific, hand-written post to ONE channel through the exact
    same publishers the daily autopilot uses. This is how you ship content you
    wrote (a security report, a founder note) rather than AI-generated daily
    posts — with all the same guards, retries and Cloudflare build verification."""
    out = content_autopilot.publish_custom(
        db, body.channel, title=body.title, html=body.html, body=body.body,
        excerpt=body.excerpt, slug=body.slug, keywords=body.keywords,
        kind=body.kind, link=body.link or "")
    audit.record(db, action="content_autopilot.publish_custom", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="content", ip=_ip(request),
                 detail=f"{body.channel}:{out.get('ok')}:{(body.title or '')[:80]}")
    return out
