#!/usr/bin/env python3
"""Publish a blog/advisory to the BVTech.org website repo.

Designed to run on the Linode box (or in CI) as the last step of the daily
content job: Claude writes the post, this script wraps it in the exact site
template and drops it into <website-repo>/blog/<slug>.html, then (optionally)
commits + pushes so Cloudflare Pages auto-deploys.

Pixel-perfect by default: it clones the most recent existing /blog/*.html as the
skeleton (real header/footer/CSS) and transplants the new content + SEO/schema.
If the repo has no posts yet, it falls back to the self-contained on-brand page.

Usage:
  # from a JSON file: {"title": "...", "kind": "advisory", "body": "## ...", "keywords": "..."}
  python scripts/publish_post.py --repo /srv/bvtech-website --infile post.json
  # or inline:
  python scripts/publish_post.py --repo /srv/bvtech-website \
      --title "Patch Tuesday — June 2026" --kind advisory --body-file body.md
  # add --git to commit & push (Cloudflare Pages deploys on push):
  python scripts/publish_post.py --repo /srv/bvtech-website --infile post.json --git

Exit codes: 0 ok · 2 bad input · 3 repo/IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import content_studio as cs   # noqa: E402


def _update_sitemap(repo: Path, meta: dict) -> bool:
    """Insert a <url> entry for the new post into sitemap.xml (idempotent).
    Safe + high-SEO: this is what gets Google to crawl the post. Returns True
    if the sitemap was changed."""
    sm = repo / "sitemap.xml"
    if not sm.is_file():
        return False
    try:
        xml = sm.read_text(encoding="utf-8")
    except Exception:
        return False
    if meta["url"] in xml:
        return False  # already listed
    entry = (f'  <url><loc>{meta["url"]}</loc><lastmod>{meta["date"]}</lastmod>'
             f'<changefreq>weekly</changefreq><priority>0.9</priority></url>\n')
    if "</urlset>" not in xml:
        return False
    xml = xml.replace("</urlset>", entry + "</urlset>", 1)
    sm.write_text(xml, encoding="utf-8")
    return True


def _newest_skeleton(repo: Path, glob: str) -> str | None:
    """Newest existing post to clone for pixel-parity. `glob` is relative to the
    repo root so it works for both 'blog/*.html' (bvtech.org) and '*/index.html'
    (jordanpolasek.com's per-post folders). Skips obvious non-post pages."""
    skip_dirs = {"", ".", "blog", "about-jordan-polasek", "certifications", "book", "contact"}
    posts = [p for p in repo.glob(glob)
             if p.is_file() and not (p.name == "index.html" and p.parent.name in skip_dirs)]
    if not posts:
        return None
    newest = max(posts, key=lambda p: p.stat().st_mtime)
    try:
        return newest.read_text(encoding="utf-8")
    except Exception:
        return None


def _load_post(args) -> dict:
    if args.infile:
        data = json.loads(Path(args.infile).read_text(encoding="utf-8"))
    else:
        data = {}
    if args.title:
        data["title"] = args.title
    if args.kind:
        data["kind"] = args.kind
    if args.keywords:
        data["keywords"] = args.keywords
    if args.slug:
        data["slug"] = args.slug
    if args.body_file:
        data["body"] = Path(args.body_file).read_text(encoding="utf-8")
    # Site/brand overrides so this publishes correctly to bvtech.org OR
    # jordanpolasek.com (CLI flag wins over any value in the infile).
    if args.site:
        data["site"] = args.site
    if args.org:
        data["org"] = args.org
    if args.author_url:
        data["author_url"] = args.author_url
    if not data.get("title"):
        print("error: a title is required (via --title or --infile)", file=sys.stderr)
        sys.exit(2)
    return data


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a post to the BVTech.org repo")
    ap.add_argument("--repo", required=True, help="path to the website working copy")
    ap.add_argument("--infile", help="JSON file with the post fields")
    ap.add_argument("--title")
    ap.add_argument("--kind", choices=["blog", "advisory"])
    ap.add_argument("--body-file", help="markdown-lite body file")
    ap.add_argument("--keywords")
    ap.add_argument("--slug")
    ap.add_argument("--blog-subdir", default="blog", help="posts dir within the repo")
    ap.add_argument("--site", help="canonical site base, e.g. https://jordanpolasek.com")
    ap.add_argument("--org", help="brand/org name shown on the page, e.g. 'Jordan Polasek'")
    ap.add_argument("--author-url", dest="author_url", help="author profile URL for schema")
    ap.add_argument("--skeleton-glob", dest="skeleton_glob",
                    help="glob (repo-relative) for the post to clone; "
                         "default 'blog/*.html'. JP folders: '*/index.html'")
    ap.add_argument("--post-path", choices=["blog-file", "slug-folder"], default="blog-file",
                    help="blog-file -> blog/<slug>.html (bvtech.org); "
                         "slug-folder -> <slug>/index.html (jordanpolasek.com)")
    ap.add_argument("--content-class",
                    help="content-wrapper class to transplant into (e.g. 'content' for JP)")
    ap.add_argument("--git", action="store_true", help="commit & push after writing")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--dry-run", action="store_true", help="render but don't write")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: repo path {repo} does not exist", file=sys.stderr)
        return 3

    post = _load_post(args)
    post["path_style"] = args.post_path   # drives the canonical URL convention
    glob = args.skeleton_glob or (f"{args.blog_subdir}/*.html")
    skeleton = _newest_skeleton(repo, glob)
    content_classes = (args.content_class,) if args.content_class else None
    try:
        html = cs.render(post, skeleton_html=skeleton, content_classes=content_classes)
        meta = cs.normalize_post(post)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Where the post file lands: bvtech.org uses blog/<slug>.html; jordanpolasek.com
    # uses per-post folders <slug>/index.html (matches its existing posts + URLs).
    if args.post_path == "slug-folder":
        out = repo / meta["slug"] / "index.html"
    else:
        out = repo / args.blog_subdir / f"{meta['slug']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    mode = "clone (pixel-perfect)" if skeleton else "standalone"
    if args.dry_run:
        print(f"[dry-run] would write {out} ({len(html)} bytes, {mode})")
        return 0
    try:
        out.write_text(html, encoding="utf-8")
    except Exception as e:
        print(f"error writing {out}: {e}", file=sys.stderr)
        return 3
    print(f"wrote {out}  ({len(html)} bytes, {mode})")
    print(f"url:   {meta['url']}")
    sitemap_changed = _update_sitemap(repo, meta)
    if sitemap_changed:
        print("updated sitemap.xml")

    if args.git:
        try:
            _git(repo, "add", str(out.relative_to(repo)))
            if sitemap_changed:
                _git(repo, "add", "sitemap.xml")
            _git(repo, "commit", "-m", f"blog: {meta['title']}")
            _git(repo, "push", "origin", args.branch)
            print("pushed — Cloudflare Pages will deploy shortly.")
        except subprocess.CalledProcessError as e:
            print(f"git step failed: {e}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
