#!/usr/bin/env bash
# Seed the website repo with a COMPLETE site export (e.g. the V107 zip) so the
# git repo matches the full live site BEFORE switching the domain to it.
#
# SAFE BY DESIGN:
#   * Adds/overwrites files; it does NOT delete anything (union copy), so the
#     daily automation's new blog posts are preserved.
#   * Never touches the repo's .git.
#   * Pushing only builds the Cloudflare *preview* (jordanpolasek-site.pages.dev).
#     bvtech.org is unaffected until YOU move the custom domain separately.
#
# Usage:
#   bash automation/seed_website.sh /root/v107.zip            # dry run (no push)
#   bash automation/seed_website.sh /root/v107.zip --push     # commit + push
set -uo pipefail

SRC="${1:-}"
REPO="${BV_WEBSITE_REPO:-/srv/bvtech-website-new}"
PUSH=""; [ "${2:-}" = "--push" ] && PUSH=1
[ -n "$SRC" ] || { echo "usage: seed_website.sh <site.zip|dir> [--push]"; exit 2; }
[ -d "$REPO/.git" ] || { echo "error: $REPO is not a git checkout (set BV_WEBSITE_REPO)"; exit 3; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -f "$SRC" ]; then
  echo "• extracting $SRC ..."
  unzip -oq "$SRC" -d "$TMP/x" || { echo "error: unzip failed"; exit 3; }
  SRCDIR="$TMP/x"
elif [ -d "$SRC" ]; then
  SRCDIR="$SRC"
else
  echo "error: $SRC is not a file or directory"; exit 2
fi

# Find the real site root: the SHALLOWEST index.html (root, or a wrapper folder)
# — not some nested page like sugar-land-it-support/index.html.
IDX="$(find "$SRCDIR" -name index.html -printf '%d\t%p\n' 2>/dev/null | sort -n | head -1 | cut -f2-)"
[ -n "$IDX" ] || { echo "error: no index.html found inside $SRC"; exit 3; }
ROOT="$(dirname "$IDX")"
echo "• site root in source: $ROOT"

count_html(){ find "$1" -path "$1/.git" -prune -o -name '*.html' -print 2>/dev/null | wc -l; }
count_posts(){ ls "$1"/blog/*.html 2>/dev/null | wc -l; }

echo "=== BEFORE (repo) ===  html: $(count_html "$REPO")  posts: $(count_posts "$REPO")"
echo "• copying full site into $REPO (union; .git + new posts preserved) ..."
cp -a "$ROOT"/. "$REPO"/
echo "=== AFTER (working tree) ===  html: $(count_html "$REPO")  posts: $(count_posts "$REPO")"
echo "• sections now present:"
for d in academy cyber-range bvpets trust tools services book guides news; do
  printf "    %-12s %s\n" "$d" "$([ -e "$REPO/$d" ] && echo '✅' || echo '❌')"
done

cd "$REPO"
git add -A
changed="$(git status --short | wc -l)"
echo "=== staged: $changed path(s) changed ==="
git status --short | head -15
[ "$changed" -gt 15 ] && echo "    … and $((changed-15)) more"

if [ -n "$PUSH" ]; then
  git commit -m "Seed complete site (academy, cyber-range, bvpets, trust, tools, services, book)" \
    || { echo "nothing to commit"; exit 0; }
  git push origin main \
    && echo "✅ pushed — verify on https://jordanpolasek-site.pages.dev  (bvtech.org is UNCHANGED)."
else
  echo
  echo "DRY RUN — nothing pushed. If the AFTER counts look right, run:"
  echo "    bash $0 \"$SRC\" --push"
fi
