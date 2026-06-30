#!/usr/bin/env python3
"""
BVTech — Retroactive Backlinks Injector  v32.0
==============================================================

Walks a local site folder (bvtech.org or jordanpolasek.com), finds
every blog/*.html file, and injects a "Related Posts" block into
each one using the posts_index.json cross-linking data.

UNLIKE the runtime enrichment in posts_index.py (which only adds
backlinks to NEW posts going forward), this script retroactively
mutates EXISTING post files. That's why it's a standalone
command-line tool instead of being built into the main app:

  - You run it ONCE, when you decide you want the old posts to
    link to newer content.
  - It runs with --dry-run BY DEFAULT. You have to explicitly
    pass --commit to actually write files.
  - It's IDEMPOTENT. Posts that already have a
    data-bvtech-related="v30" or "v32-retro" marker are skipped,
    so re-running does nothing.
  - It commits per-file, so if something crashes halfway through
    the posts it did touch are still valid HTML.

USAGE
-----
    # Dry run — show what would happen, write nothing
    python retroactive_backlinks.py --site bvtech \\
        --site-root "C:/BVTech2/Website/bvtech.org"

    # Commit — actually modify files
    python retroactive_backlinks.py --site bvtech \\
        --site-root "C:/BVTech2/Website/bvtech.org" --commit

    # Limit to N files (for testing against a small subset first)
    python retroactive_backlinks.py --site bvtech \\
        --site-root "C:/BVTech2/Website/bvtech.org" --limit 3

    # Use a specific app dir (where posts_index.json lives)
    python retroactive_backlinks.py --site bvtech \\
        --site-root "C:/BVTech2/Website/bvtech.org" \\
        --app-dir "C:/BVTech2" --commit

SAFETY NOTES
------------
- Before running with --commit, COMMIT YOUR WORKING SITE FOLDER
  TO GIT. This tool modifies HTML files in place and the undo
  path is "git checkout -- .".
- Files are only modified if we can successfully inject the
  block. Files where the byline marker can't be found and the
  </body> tag can't be found are skipped entirely.
- A backup of the original file is written to
  <site-root>/.bvtech_backups/<slug>.html.bak before each
  modification, unless --no-backup is passed.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Add app dir to path so we can import posts_index
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from posts_index import (
        PostsIndex, build_related_block, build_cross_site_block,
        inject_related_blocks,
    )
except ImportError as e:
    print(f"ERROR: could not import posts_index: {e}")
    print(f"Make sure this script is in the same directory as posts_index.py")
    sys.exit(2)


BACKUP_DIR_NAME = ".bvtech_backups"
RETRO_MARKER = 'data-bvtech-related="v30"'  # both v30 and v32 use this
RETRO_V32_MARKER = 'data-bvtech-retro="v32"'


def is_already_enriched(html: str) -> bool:
    """Check if a post already has a related-posts block."""
    return (RETRO_MARKER in html
            or RETRO_V32_MARKER in html
            or 'bvtech-related-posts' in html)


def find_blog_files(site_root: Path) -> list:
    """Find all blog/*.html files excluding index.html."""
    blog_dir = site_root / "blog"
    if not blog_dir.is_dir():
        return []
    files = []
    for f in sorted(blog_dir.glob("*.html")):
        if f.name == "index.html":
            continue  # never touch the handcrafted index
        files.append(f)
    return files


def infer_slug_from_path(path: Path) -> str:
    """blog/foo-bar.html → foo-bar"""
    return path.stem


def infer_title_from_html(html: str, fallback: str) -> str:
    """Best-effort title extraction from <title> or first <h1>."""
    import re
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        t = m.group(1).strip()
        # Strip common site suffix patterns
        for sep in [" | ", " — ", " - "]:
            if sep in t:
                t = t.split(sep)[0].strip()
        return t or fallback
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() or fallback
    return fallback


def backup_file(src: Path, backup_dir: Path) -> Path:
    """Copy src to backup_dir, preserving name + .bak suffix."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / (src.name + ".bak")
    # Don't clobber existing backups — append a counter if needed
    counter = 1
    while dst.exists():
        dst = backup_dir / f"{src.name}.{counter}.bak"
        counter += 1
    shutil.copy2(src, dst)
    return dst


def process_file(path: Path, site: str, index: PostsIndex,
                  commit: bool, backup: bool,
                  backup_dir: Path) -> dict:
    """Process one blog file. Returns a dict with the outcome."""
    result = {
        "path": str(path),
        "slug": infer_slug_from_path(path),
        "action": "",
        "related_count": 0,
        "cross_count": 0,
        "error": None,
    }
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["action"] = "skip_read_error"
        result["error"] = str(e)
        return result

    # Skip if already enriched
    if is_already_enriched(html):
        result["action"] = "skip_already_enriched"
        return result

    slug = result["slug"]
    title = infer_title_from_html(html, fallback=slug.replace("-", " ").title())
    # Pick related posts (this post should NOT be in its own related list)
    related = index.pick_related(
        new_title=title,
        new_focus_keyword="",  # we don't know the original keyword
        site=site,
        limit=3,
        exclude_slug=slug,
    )
    cross = index.pick_cross_site(site=site, limit=1)

    result["related_count"] = len(related)
    result["cross_count"] = len(cross)

    if not related and not cross:
        result["action"] = "skip_no_candidates"
        return result

    # Build the blocks — use v32 marker so we can identify retro-injected ones later
    related_block = build_related_block(related, site)
    cross_block = build_cross_site_block(cross, site)

    # Swap the v30 marker for a v32-retro marker so we can tell these apart
    if related_block:
        related_block = related_block.replace(
            'data-bvtech-related="v30"',
            'data-bvtech-related="v30" data-bvtech-retro="v32"',
        )
    if cross_block:
        cross_block = cross_block.replace(
            'data-bvtech-cross="v30"',
            'data-bvtech-cross="v30" data-bvtech-retro="v32"',
        )

    new_html = inject_related_blocks(html, related_block, cross_block)
    if new_html == html:
        result["action"] = "skip_no_injection_point"
        return result

    if not commit:
        result["action"] = "dry_run_would_write"
        return result

    # Actually write
    if backup:
        try:
            backup_file(path, backup_dir)
        except Exception as e:
            result["action"] = "skip_backup_failed"
            result["error"] = str(e)
            return result

    try:
        path.write_text(new_html, encoding="utf-8")
        result["action"] = "wrote"
    except Exception as e:
        result["action"] = "skip_write_error"
        result["error"] = str(e)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retroactively inject Related Posts blocks into existing blog files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--site", required=True, choices=["bvtech", "jp"],
                        help="Which site to process (bvtech or jp)")
    parser.add_argument("--site-root", required=True,
                        help="Absolute path to the local site folder (must contain blog/)")
    parser.add_argument("--app-dir", default=str(SCRIPT_DIR),
                        help="Directory containing posts_index.json (defaults to script directory)")
    parser.add_argument("--commit", action="store_true",
                        help="Actually write files. WITHOUT this flag, this is a dry run.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process the first N files (0 = all). Useful for testing.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip the .bvtech_backups/ copy step. Not recommended.")
    args = parser.parse_args()

    site_root = Path(args.site_root).resolve()
    if not site_root.is_dir():
        print(f"ERROR: site root does not exist: {site_root}")
        return 2
    if not (site_root / "blog").is_dir():
        print(f"ERROR: site root does not contain blog/: {site_root}")
        return 2

    app_dir = Path(args.app_dir).resolve()
    index_path = app_dir / "posts_index.json"
    if not index_path.exists():
        print(f"ERROR: posts_index.json not found in {app_dir}")
        print(f"       You need at least a few posts published through Super Posting")
        print(f"       (which populates posts_index.json) before retroactive linking")
        print(f"       has anything to link to.")
        return 2

    index = PostsIndex(str(app_dir))
    if not index.posts:
        print(f"ERROR: posts_index.json is empty. Nothing to link to.")
        return 2

    same_site_count = sum(1 for p in index.posts if p.get("site") == args.site)
    print(f"Retroactive Backlinks — v32")
    print(f"  Site:       {args.site}")
    print(f"  Site root:  {site_root}")
    print(f"  App dir:    {app_dir}")
    print(f"  Index has:  {len(index.posts)} posts total ({same_site_count} on this site)")
    print(f"  Mode:       {'COMMIT (will write)' if args.commit else 'DRY RUN'}")
    print()

    files = find_blog_files(site_root)
    if args.limit > 0:
        files = files[:args.limit]
    print(f"Found {len(files)} blog files to consider:")

    backup_dir = site_root / BACKUP_DIR_NAME
    counts = {
        "wrote": 0,
        "dry_run_would_write": 0,
        "skip_already_enriched": 0,
        "skip_no_candidates": 0,
        "skip_no_injection_point": 0,
        "skip_read_error": 0,
        "skip_write_error": 0,
        "skip_backup_failed": 0,
    }
    for f in files:
        result = process_file(
            path=f,
            site=args.site,
            index=index,
            commit=args.commit,
            backup=not args.no_backup,
            backup_dir=backup_dir,
        )
        action = result["action"]
        counts[action] = counts.get(action, 0) + 1
        icon = {
            "wrote": "✅",
            "dry_run_would_write": "📝",
            "skip_already_enriched": "↷ ",
            "skip_no_candidates": "—",
            "skip_no_injection_point": "⚠️ ",
        }.get(action, "❌")
        print(f"  {icon} {f.name:<50} {action:<28} rel={result['related_count']} cross={result['cross_count']}"
              + (f" ERROR: {result['error']}" if result['error'] else ""))

    print()
    print("Summary:")
    for k, v in counts.items():
        if v > 0:
            print(f"  {k:<28} {v}")

    if not args.commit and (counts.get("dry_run_would_write", 0) > 0):
        print()
        print(f"DRY RUN: {counts['dry_run_would_write']} file(s) would be modified.")
        print(f"Re-run with --commit to actually write them.")
        print(f"Backups will be written to: {backup_dir}")

    if args.commit and counts.get("wrote", 0) > 0:
        print()
        print(f"Wrote {counts['wrote']} file(s).")
        if not args.no_backup:
            print(f"Backups in: {backup_dir}")
        print(f"Review with: git diff")
        print(f"Revert with: git checkout -- .")

    return 0


if __name__ == "__main__":
    sys.exit(main())
