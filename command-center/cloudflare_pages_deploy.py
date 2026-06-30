#!/usr/bin/env python3
"""
BVTech — Cloudflare Pages Direct Upload Deployer  v29.0
==============================================================

This module implements the FULL Cloudflare Pages Direct Upload
protocol — the same five-step dance that `wrangler pages deploy ./`
performs under the hood. It uploads a complete local folder (the
"site root") as one atomic Cloudflare Pages deployment.

WHY THIS EXISTS
---------------
The v25/v26/v27 implementation in tacticalrmm_integration.py was
catastrophically wrong: it called the deployments endpoint with a
single-file dict containing only the new blog post. Cloudflare Pages
Direct Upload *replaces the entire deployment* with whatever is
uploaded — meaning every publish would have wiped the full site
(bvtech.org = 186 files, jordanpolasek.com = 20 files) and left only
the new post live. The bug never fired because a second routing bug
was blocking it. v28 put a hard safety hold on the broken path. v29
(this file) is the real fix.

THE PROTOCOL (what wrangler actually does)
------------------------------------------
1. GET  /accounts/{acct}/pages/projects/{proj}/upload-token
       Returns a short-lived JWT for the asset upload endpoints.

2. POST /pages/assets/check-missing          (Authorization: Bearer JWT)
       Body: {"hashes": ["abc123...", ...]}
       Returns the subset of hashes Cloudflare does NOT already have
       cached from previous deployments. Everything else is dedup'd.

3. POST /pages/assets/upload?base64=true     (Authorization: Bearer JWT)
       Body: [{"base64": true, "key": "<hash>", "value": "<b64-bytes>",
               "metadata": {"contentType": "text/html"}}, ...]
       Uploads the missing file contents. Batch size: keep each POST
       body under ~15 MB to be safe.

4. POST /pages/assets/upsert-hashes          (Authorization: Bearer JWT)
       Body: {"hashes": ["abc123...", ...]}
       Confirms the full hash set is now associated with this account.

5. POST /accounts/{acct}/pages/projects/{proj}/deployments
       multipart/form-data with a "manifest" field containing a JSON
       dict: {"/index.html": "<hash>", "/assets/logo.png": "<hash>", ...}
       Every file that should be served by the deployment MUST be in
       this manifest. Files not in the manifest stop existing.

HASH FORMAT
-----------
SHA-256 of the raw file bytes, truncated to 32 hex characters:
    hashlib.sha256(file_bytes).hexdigest()[:32]

Wrangler historically prepends the file extension to the hash input
in some code paths; our implementation uses the plain content hash
which matches the modern check-missing endpoint.

SAFETY
------
- Refuses to deploy an empty directory.
- Refuses to deploy if site_root does not contain at least an
  index.html at the top level (sanity check — every real site has one).
- Enforces CF's 25 MiB per-file limit before trying to upload.
- Enforces CF's 20,000 file limit before trying to deploy.
- dry_run=True mode: does steps 1-2 (walks the folder, computes hashes,
  asks CF what's missing) but STOPS before uploading or deploying.
  Use this to verify nothing exploded before pressing the real button.
"""

import base64
import hashlib
import io
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError(
        "cloudflare_pages_deploy requires the 'requests' package. "
        "Install it with: pip install requests"
    )


# ============================================================
# LIMITS (from https://developers.cloudflare.com/pages/platform/limits/)
# ============================================================
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024       # 25 MiB per asset
MAX_FILES_PER_SITE_FREE = 20_000             # Free plan limit
MAX_UPLOAD_BATCH_BYTES = 15 * 1024 * 1024    # Keep each upload POST under 15 MB
MAX_HASHES_PER_CHECK = 5_000                 # check-missing batch size


# ============================================================
# FILE FILTERS — what we DON'T upload
# ============================================================
IGNORED_BASENAMES = {
    ".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep",
}
IGNORED_DIR_NAMES = {
    ".git", ".github", ".svn", "node_modules", "__pycache__",
    ".vscode", ".idea", ".cache", "CVS",
}
IGNORED_PREFIXES = (".wrangler",)


def _should_skip(path: Path, site_root: Path) -> bool:
    """Return True if a file under site_root should NOT be uploaded."""
    rel = path.relative_to(site_root)
    parts = rel.parts
    if path.name in IGNORED_BASENAMES:
        return True
    for p in parts[:-1]:
        if p in IGNORED_DIR_NAMES or p.startswith(IGNORED_PREFIXES):
            return True
    return False


def _sha256_32(data: bytes) -> str:
    """CF asset hash: SHA-256 truncated to 32 hex chars."""
    return hashlib.sha256(data).hexdigest()[:32]


def _content_type_for(path: Path) -> str:
    """Best-effort Content-Type. Cloudflare will serve whatever we tell it."""
    # Extensions that mimetypes gets wrong or doesn't know
    overrides = {
        ".js":     "application/javascript; charset=utf-8",
        ".mjs":    "application/javascript; charset=utf-8",
        ".css":    "text/css; charset=utf-8",
        ".html":   "text/html; charset=utf-8",
        ".htm":    "text/html; charset=utf-8",
        ".json":   "application/json; charset=utf-8",
        ".xml":    "application/xml; charset=utf-8",
        ".svg":    "image/svg+xml",
        ".woff":   "font/woff",
        ".woff2":  "font/woff2",
        ".ttf":    "font/ttf",
        ".otf":    "font/otf",
        ".ico":    "image/x-icon",
        ".webmanifest": "application/manifest+json",
        ".txt":    "text/plain; charset=utf-8",
        ".md":     "text/markdown; charset=utf-8",
    }
    ext = path.suffix.lower()
    if ext in overrides:
        return overrides[ext]
    ct, _ = mimetypes.guess_type(str(path))
    return ct or "application/octet-stream"


# ============================================================
# DATA CLASS — one file's metadata for a pending deployment
# ============================================================
class _Asset:
    __slots__ = ("rel_path", "abs_path", "size", "hash", "content_type", "data")

    def __init__(self, rel_path: str, abs_path: Path, size: int,
                 hash_: str, content_type: str):
        self.rel_path = rel_path           # e.g. "/blog/index.html"
        self.abs_path = abs_path           # absolute Path
        self.size = size                   # bytes
        self.hash = hash_                  # 32-hex CF hash
        self.content_type = content_type   # MIME type
        self.data: Optional[bytes] = None  # lazy-loaded bytes (for upload)


# ============================================================
# MAIN DEPLOYER
# ============================================================
class CloudflarePagesDeployer:
    """Deploys a local folder to a Cloudflare Pages project via the
    Direct Upload API. Stateless — create one per deployment.
    """

    API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, api_token: str, account_id: str, project_name: str,
                 logger: Optional[Callable[[str], None]] = None):
        if not api_token:
            raise ValueError("api_token is required")
        if not account_id:
            raise ValueError("account_id is required")
        if not project_name:
            raise ValueError("project_name is required")
        self.api_token = api_token.strip()
        self.account_id = account_id.strip()
        self.project_name = project_name.strip()
        self.log = logger or (lambda msg: None)
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": "BVTech-MSP-CommandCenter/29.0 (+cloudflare_pages_deploy.py)",
        })

    # ── Public: sanity-check the config without touching files ─────
    def verify_project(self) -> Tuple[bool, str]:
        """GET the project. Verifies API token + account + project all
        line up before we start computing hashes. Returns (ok, message)."""
        url = f"{self.API_BASE}/accounts/{self.account_id}/pages/projects/{self.project_name}"
        try:
            r = self._session.get(url, timeout=20)
            if r.status_code == 200:
                data = r.json().get("result", {}) or {}
                return True, (
                    f"Project '{data.get('name', self.project_name)}' OK  "
                    f"(subdomain={data.get('subdomain', '?')}, "
                    f"domains={len(data.get('domains', []) or [])})"
                )
            if r.status_code == 401:
                return False, "401 Unauthorized — API token invalid or missing 'Cloudflare Pages — Edit' permission"
            if r.status_code == 404:
                return False, f"404 Not Found — project '{self.project_name}' does not exist in account {self.account_id}"
            return False, f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:
            return False, f"Network error: {e}"

    # ── Public: walk a folder and build the asset list ─────────────
    def walk_site(self, site_root: str) -> Tuple[List[_Asset], Dict[str, str]]:
        """Walk site_root, compute hashes, return (assets, manifest).

        manifest is a dict of "/url/path" -> hash, exactly the shape
        Cloudflare expects in the deployments multipart form.

        Raises ValueError on obvious problems (empty folder, missing
        index.html, oversize file, too many files).
        """
        root = Path(site_root).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"site_root does not exist or is not a directory: {site_root}")

        # Sanity check: every real site has a top-level index.html.
        # This guards against accidentally pointing at C:\ or an empty temp folder.
        if not (root / "index.html").exists():
            raise ValueError(
                f"Refusing to deploy: no index.html found at the top of {site_root}. "
                f"If you meant to deploy a subfolder, point site_root there instead. "
                f"This check exists to stop you from nuking your site by pointing at "
                f"the wrong directory."
            )

        assets: List[_Asset] = []
        manifest: Dict[str, str] = {}
        total_bytes = 0

        for abs_path in sorted(root.rglob("*")):
            if not abs_path.is_file():
                continue
            if _should_skip(abs_path, root):
                continue

            size = abs_path.stat().st_size
            if size > MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File too large for Cloudflare Pages: {abs_path} "
                    f"is {size/1024/1024:.1f} MiB (limit {MAX_FILE_SIZE_BYTES/1024/1024:.0f} MiB). "
                    f"Move large files to R2 or remove them before deploying."
                )

            with open(abs_path, "rb") as f:
                data = f.read()
            h = _sha256_32(data)
            ct = _content_type_for(abs_path)

            rel = "/" + abs_path.relative_to(root).as_posix()
            asset = _Asset(rel, abs_path, size, h, ct)
            asset.data = data  # keep in memory — sites are small
            assets.append(asset)
            manifest[rel] = h
            total_bytes += size

        if not assets:
            raise ValueError(f"site_root {site_root} contains no files to deploy")
        if len(assets) > MAX_FILES_PER_SITE_FREE:
            raise ValueError(
                f"{len(assets)} files exceeds Cloudflare Pages free-plan limit "
                f"of {MAX_FILES_PER_SITE_FREE}. Upgrade the plan or prune the tree."
            )

        self.log(f"Walked {site_root}: {len(assets)} files, {total_bytes/1024/1024:.2f} MiB total")
        return assets, manifest

    # ── Step 1: get upload JWT ─────────────────────────────────────
    def _get_upload_token(self) -> str:
        url = f"{self.API_BASE}/accounts/{self.account_id}/pages/projects/{self.project_name}/upload-token"
        r = self._session.get(url, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"upload-token failed: HTTP {r.status_code} {r.text[:300]}")
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"upload-token failed: {data.get('errors')}")
        jwt = (data.get("result") or {}).get("jwt") or ""
        if not jwt:
            raise RuntimeError(f"upload-token response missing jwt: {data}")
        return jwt

    # ── Step 2: check-missing ──────────────────────────────────────
    def _check_missing(self, jwt: str, hashes: List[str]) -> List[str]:
        """Returns the subset of hashes CF does NOT already have."""
        missing: List[str] = []
        # Batch in chunks to avoid huge request bodies
        for i in range(0, len(hashes), MAX_HASHES_PER_CHECK):
            chunk = hashes[i:i + MAX_HASHES_PER_CHECK]
            url = f"{self.API_BASE}/pages/assets/check-missing"
            headers = {"Authorization": f"Bearer {jwt}",
                       "Content-Type": "application/json"}
            r = self._session.post(url, headers=headers,
                                    json={"hashes": chunk}, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"check-missing failed: HTTP {r.status_code} {r.text[:300]}")
            data = r.json()
            if not data.get("success"):
                raise RuntimeError(f"check-missing failed: {data.get('errors')}")
            missing.extend(data.get("result") or [])
        return missing

    # ── Step 3: upload missing file contents ──────────────────────
    def _upload_assets(self, jwt: str, assets_by_hash: Dict[str, _Asset],
                       missing_hashes: List[str]) -> None:
        """Upload the file contents for each missing hash, batched."""
        if not missing_hashes:
            self.log("No new files to upload — Cloudflare already has everything.")
            return

        self.log(f"Uploading {len(missing_hashes)} new/changed files...")

        url = f"{self.API_BASE}/pages/assets/upload"
        headers = {"Authorization": f"Bearer {jwt}",
                   "Content-Type": "application/json"}

        batch: List[dict] = []
        batch_bytes = 0
        uploaded = 0
        failed: List[str] = []

        def flush():
            nonlocal batch, batch_bytes, uploaded
            if not batch:
                return
            # Retry up to 3 times with exponential backoff
            for attempt in range(3):
                try:
                    r = self._session.post(url, headers=headers,
                                            json=batch, timeout=180)
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("success"):
                            uploaded += len(batch)
                            self.log(f"  Batch OK: {uploaded}/{len(missing_hashes)} files uploaded")
                            batch = []
                            batch_bytes = 0
                            return
                        raise RuntimeError(f"upload batch failed: {data.get('errors')}")
                    if r.status_code in (429, 500, 502, 503, 504):
                        wait = 2 ** attempt
                        self.log(f"  Batch got HTTP {r.status_code}, retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"upload failed: HTTP {r.status_code} {r.text[:300]}")
                except requests.RequestException as e:
                    wait = 2 ** attempt
                    self.log(f"  Network error: {e}, retrying in {wait}s...")
                    time.sleep(wait)
            # Out of retries
            for item in batch:
                failed.append(item["key"])
            batch = []
            batch_bytes = 0

        for h in missing_hashes:
            asset = assets_by_hash.get(h)
            if asset is None:
                # Should not happen — we built the map from the same list
                continue
            if asset.data is None:
                with open(asset.abs_path, "rb") as f:
                    asset.data = f.read()
            b64 = base64.b64encode(asset.data).decode("ascii")
            item = {
                "base64": True,
                "key": h,
                "value": b64,
                "metadata": {"contentType": asset.content_type},
            }
            # Approximate body cost (b64 is ~1.33x the raw size)
            item_cost = len(b64) + 128
            if batch and batch_bytes + item_cost > MAX_UPLOAD_BATCH_BYTES:
                flush()
            batch.append(item)
            batch_bytes += item_cost

        flush()

        if failed:
            raise RuntimeError(
                f"Failed to upload {len(failed)} assets after retries: "
                f"{failed[:5]}{'...' if len(failed) > 5 else ''}"
            )

    # ── Step 4: upsert-hashes ──────────────────────────────────────
    def _upsert_hashes(self, jwt: str, all_hashes: List[str]) -> None:
        """Confirm the full hash set for this deployment."""
        # Dedup — same file referenced twice should only appear once here
        unique = sorted(set(all_hashes))
        url = f"{self.API_BASE}/pages/assets/upsert-hashes"
        headers = {"Authorization": f"Bearer {jwt}",
                   "Content-Type": "application/json"}
        # Batch to be safe
        for i in range(0, len(unique), MAX_HASHES_PER_CHECK):
            chunk = unique[i:i + MAX_HASHES_PER_CHECK]
            r = self._session.post(url, headers=headers,
                                    json={"hashes": chunk}, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"upsert-hashes failed: HTTP {r.status_code} {r.text[:300]}")
            data = r.json()
            if not data.get("success"):
                raise RuntimeError(f"upsert-hashes failed: {data.get('errors')}")

    # ── Step 5: create deployment ──────────────────────────────────
    def _create_deployment(self, manifest: Dict[str, str],
                            branch: Optional[str] = None) -> dict:
        """Create the actual deployment with the full manifest."""
        url = f"{self.API_BASE}/accounts/{self.account_id}/pages/projects/{self.project_name}/deployments"

        manifest_json = json.dumps(manifest, separators=(",", ":"))
        files = {
            "manifest": (None, manifest_json, "application/json"),
        }
        if branch:
            files["branch"] = (None, branch)

        # IMPORTANT: use the session's bearer auth, do NOT override with the JWT.
        # The deployments endpoint wants the account API token, not the upload JWT.
        r = self._session.post(url, files=files, timeout=300)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create deployment failed: HTTP {r.status_code} {r.text[:500]}")
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"create deployment failed: {data.get('errors')}")
        return data.get("result") or {}

    # ── Public: do the whole dance ─────────────────────────────────
    def deploy_folder(self, site_root: str, branch: str = "main",
                       dry_run: bool = False) -> dict:
        """Deploy an entire local folder to Cloudflare Pages.

        Args:
            site_root: absolute path to the folder to deploy. Must contain
                       index.html at the top level.
            branch:    'main' for production, or another branch name
                       for a preview deployment.
            dry_run:   if True, walks the folder, verifies the project,
                       and asks check-missing what it WOULD upload —
                       but stops before uploading or creating the
                       deployment. Returns the same shape with
                       {"dry_run": True, ...}.

        Returns:
            On success: the CF deployment result dict, plus extra keys
            {"files_total", "files_uploaded", "bytes_total",
             "deploy_mode": "cf_direct_v29"}.

        Raises:
            ValueError on config / folder validation errors.
            RuntimeError on API failures.
        """
        t0 = time.time()
        self.log(f"=== Cloudflare Pages Deploy: {self.project_name} ===")
        self.log(f"Site root: {site_root}")
        self.log(f"Branch:    {branch}")
        self.log(f"Dry run:   {dry_run}")

        # Step 0: verify the project exists and token works BEFORE reading files
        ok, msg = self.verify_project()
        if not ok:
            raise RuntimeError(f"Project verification failed: {msg}")
        self.log(f"Project verified: {msg}")

        # Walk the folder
        assets, manifest = self.walk_site(site_root)
        all_hashes = [a.hash for a in assets]
        assets_by_hash: Dict[str, _Asset] = {}
        for a in assets:
            assets_by_hash.setdefault(a.hash, a)
        total_bytes = sum(a.size for a in assets)

        # Step 1: get upload token
        self.log("Requesting upload token...")
        jwt = self._get_upload_token()

        # Step 2: check-missing
        self.log(f"Checking which of {len(all_hashes)} files Cloudflare already has...")
        missing = self._check_missing(jwt, all_hashes)
        new_count = len(missing)
        cached_count = len(all_hashes) - new_count
        self.log(f"  {cached_count} files already cached, {new_count} need upload")

        if dry_run:
            self.log("DRY RUN complete — stopping before upload/deploy.")
            elapsed = time.time() - t0
            return {
                "dry_run": True,
                "deploy_mode": "cf_direct_v29",
                "project_name": self.project_name,
                "site_root": str(site_root),
                "files_total": len(assets),
                "files_would_upload": new_count,
                "files_cached": cached_count,
                "bytes_total": total_bytes,
                "elapsed_sec": round(elapsed, 2),
                "sample_would_upload": [
                    assets_by_hash[h].rel_path for h in missing[:10]
                ],
            }

        # Step 3: upload missing contents
        self._upload_assets(jwt, assets_by_hash, missing)

        # Step 4: upsert-hashes
        self.log("Confirming hash set...")
        self._upsert_hashes(jwt, all_hashes)

        # Step 5: create the deployment (uses account token, not JWT)
        self.log("Creating deployment...")
        result = self._create_deployment(manifest, branch=branch)

        elapsed = time.time() - t0
        self.log(f"=== Deploy complete in {elapsed:.1f}s ===")
        self.log(f"    Deployment URL: {result.get('url', '(none)')}")

        # Pack extra info onto the result
        result.setdefault("deploy_mode", "cf_direct_v29")
        result["files_total"] = len(assets)
        result["files_uploaded"] = new_count
        result["files_cached"] = cached_count
        result["bytes_total"] = total_bytes
        result["elapsed_sec"] = round(elapsed, 2)
        return result


# ============================================================
# HIGH-LEVEL HELPER — used by the ORM publisher path
# ============================================================
def write_blog_post_and_deploy(
    site_root: str,
    slug: str,
    html: str,
    api_token: str,
    account_id: str,
    project_name: str,
    branch: str = "main",
    dry_run: bool = False,
    regenerate_index: bool = False,
    logger: Optional[Callable[[str], None]] = None,
) -> dict:
    """Write a new blog post into the local site_root and deploy the
    whole folder to Cloudflare Pages.

    v29 FILE LAYOUT NOTE:
    The existing bvtech.org site uses FLAT blog files:
        /blog/some-slug.html           <-- existing convention
    NOT subfolder style:
        /blog/some-slug/index.html     <-- would break existing links

    This function matches the existing convention. If your site uses
    the other style, rename the written file before calling.

    By default `regenerate_index=False` because the existing
    /blog/index.html is a handcrafted 35KB listing page — auto-replacing
    it would destroy your design. Set `regenerate_index=True` ONLY if
    you know your index is disposable (or if you've added the marker
    data-blog-index="auto" / data-blog-index="manual" to control it).

    Args:
        site_root:  absolute path to the local mirror of the site
                    (e.g. C:\\BVTech2\\Website\\bvtech.org)
        slug:       URL slug for the new post (e.g. "how-to-pick-an-msp")
        html:       the full HTML of the new post
        api_token:  Cloudflare API token with Pages:Edit permission
        account_id: Cloudflare account ID
        project_name: Cloudflare Pages project name
        branch:     production branch ("main" unless you know otherwise)
        dry_run:    if True, write the file locally + walk + check-missing
                    but do NOT upload or deploy. Good for the Test button.
        regenerate_index: DEFAULT FALSE — only regenerate blog/index.html
                          if your site uses the auto-index convention.
                          DO NOT set True on bvtech.org — the existing
                          index is a handcrafted page you don't want to
                          overwrite.
        logger:     optional log callback

    Returns: the deploy_folder() result dict.
    """
    log = logger or (lambda msg: None)
    root = Path(site_root).resolve()
    if not root.exists():
        raise ValueError(f"site_root does not exist: {site_root}")

    blog_dir = root / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    # v29: Flat-file layout matching existing bvtech.org convention
    # Also sanitize the slug defensively — no path traversal
    safe_slug = "".join(c for c in slug if c.isalnum() or c in "-_").strip("-_")
    if not safe_slug:
        raise ValueError(f"slug '{slug}' sanitized to empty string — use alphanumeric + dashes only")
    if safe_slug != slug:
        log(f"Sanitized slug: {slug!r} -> {safe_slug!r}")

    post_path = blog_dir / f"{safe_slug}.html"
    log(f"Writing new post: {post_path}")
    post_path.write_text(html, encoding="utf-8")

    # v29: Only regenerate index if explicitly asked AND the marker allows it
    if regenerate_index:
        _regenerate_blog_index(blog_dir, log)
    else:
        log(f"  Skipping blog/index.html regeneration (pass regenerate_index=True to enable)")

    # Deploy the whole folder
    deployer = CloudflarePagesDeployer(
        api_token=api_token,
        account_id=account_id,
        project_name=project_name,
        logger=log,
    )
    return deployer.deploy_folder(str(root), branch=branch, dry_run=dry_run)


def _regenerate_blog_index(blog_dir: Path, log: Callable[[str], None]) -> None:
    """Rebuild blog/index.html with a simple listing of every *.html
    post in the blog folder.

    SAFETY: if blog/index.html already exists AND it does NOT contain
    the marker data-blog-index="auto", we REFUSE to overwrite it and
    log a warning. This protects handcrafted blog listing pages.
    The marker must be added by the user (or by the auto-generated
    listing itself on the next write) before this function will touch it.
    """
    index_path = blog_dir / "index.html"
    if index_path.exists():
        try:
            existing = index_path.read_text(encoding="utf-8", errors="ignore")
            if 'data-blog-index="auto"' not in existing and "data-blog-index='auto'" not in existing:
                log("  REFUSING to overwrite blog/index.html — no data-blog-index='auto' marker")
                log("  (Add the marker to the top of the file if you want this auto-regenerated.)")
                return
        except Exception:
            log("  Could not read existing blog/index.html — leaving it alone")
            return

    import html as html_mod
    import re

    entries: List[Tuple[str, str, float]] = []  # (slug, title, mtime)
    for post_file in sorted(blog_dir.iterdir()):
        if not post_file.is_file():
            continue
        if post_file.name == "index.html":
            continue
        if not post_file.suffix.lower() == ".html":
            continue
        slug = post_file.stem
        title = slug.replace("-", " ").title()
        try:
            content = post_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"<title[^>]*>([^<]+)</title>", content, re.IGNORECASE)
            if m:
                title = m.group(1).strip()
        except Exception:
            pass
        mtime = post_file.stat().st_mtime
        entries.append((slug, title, mtime))

    # Newest first
    entries.sort(key=lambda e: e[2], reverse=True)

    rows_html = "\n".join(
        f'    <li><a href="/blog/{html_mod.escape(slug)}.html">{html_mod.escape(title)}</a></li>'
        for slug, title, _ in entries
    )

    page = f"""<!DOCTYPE html>
<html lang="en" data-blog-index="auto">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blog — BVTech</title>
<meta name="description" content="Latest posts from the BVTech blog.">
<link rel="canonical" href="/blog/">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:780px;margin:2rem auto;padding:0 1.25rem;color:#1a1a1a;line-height:1.6;}}
h1{{font-size:2rem;margin-bottom:0.5rem;}}
ul{{list-style:none;padding:0;}}
li{{padding:0.6rem 0;border-bottom:1px solid #eee;}}
a{{color:#6d28d9;text-decoration:none;font-weight:600;}}
a:hover{{text-decoration:underline;}}
.post-count{{color:#666;font-size:0.9rem;margin-bottom:1.5rem;}}
</style>
</head>
<body>
<h1>Blog</h1>
<p class="post-count">{len(entries)} post{'' if len(entries) == 1 else 's'}</p>
<ul>
{rows_html}
</ul>
<p style="margin-top:2rem;"><a href="/">← Home</a></p>
</body>
</html>
"""
    index_path.write_text(page, encoding="utf-8")
    log(f"  Regenerated blog/index.html ({len(entries)} post{'s' if len(entries) != 1 else ''})")


if __name__ == "__main__":
    # CLI smoke test: python cloudflare_pages_deploy.py <site_root> <token> <account> <project> [--dry-run]
    import argparse, sys
    p = argparse.ArgumentParser(description="Cloudflare Pages Direct Upload deployer")
    p.add_argument("site_root", help="Path to local site folder (must contain index.html)")
    p.add_argument("api_token", help="Cloudflare API token with Pages:Edit")
    p.add_argument("account_id", help="Cloudflare account ID")
    p.add_argument("project_name", help="Cloudflare Pages project name")
    p.add_argument("--branch", default="main")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    def _p(msg): print(msg, flush=True)
    try:
        d = CloudflarePagesDeployer(args.api_token, args.account_id, args.project_name, logger=_p)
        result = d.deploy_folder(args.site_root, branch=args.branch, dry_run=args.dry_run)
        print("\nRESULT:")
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
