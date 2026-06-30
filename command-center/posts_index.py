#!/usr/bin/env python3
"""
BVTech — Posts Index + Cross-Linking  v30.0
==============================================================

Maintains a local JSON index of every blog post the Super Posting
system has published, so each NEW post can inject "Related Posts"
backlinks to 2-3 previous posts. This builds a link graph forward
without ever mutating old HTML files (which would be dangerous).

WHY FORWARD-ONLY LINKING
------------------------
The original ask was "make all posts backlink to each other so SEO
sees one uniform thing." The *safe* way to do that is to link
forward — each new post links to old ones. Over time the graph
becomes dense:

    post 1 (no links, first one ever)
    post 2 -> post 1
    post 3 -> post 2, post 1
    post 4 -> post 3, post 2   (pick 2-3 most relevant or most recent)
    ...

After 10 posts every post has multiple inbound links from newer
content, which is exactly what Google rewards. And we never rewrote
a single existing file, so nothing breaks.

INDEX FILE LAYOUT
-----------------
Stored as posts_index.json in the app dir:

    {
      "posts": [
        {
          "slug": "how-msps-help-texas-smbs",
          "title": "How MSPs Help Texas SMBs Stay Secure",
          "site": "bvtech",
          "url": "https://bvtech.org/blog/how-msps-help-texas-smbs.html",
          "published_at": "2026-04-09T14:32:11",
          "focus_keyword": "managed it services",
          "summary": "Three ways a managed IT provider..."
        },
        ...
      ]
    }

RELATED-POST SELECTION
----------------------
When a new post is about to publish:
  1. Filter the index to posts on the SAME site (bvtech links to
     bvtech, jp links to jp — cross-site links go in a separate
     "Also published by Jordan" block).
  2. Score each candidate by keyword overlap with the new post's
     focus_keyword + title words.
  3. Pick top 3 by score, tiebreak by recency.
  4. If fewer than 3 candidates exist (early days), take whatever
     is there.

HTML INJECTION
--------------
The "Related Posts" block is HTML that gets inserted into the new
post's <body> just before the author byline (or appended at the
end if the byline marker isn't found). The block has this shape:

    <div class="bvtech-related-posts" data-bvtech-related="v30">
      <h3>Related from BVTech.org</h3>
      <ul>
        <li><a href="/blog/slug-1.html">Title 1</a></li>
        <li><a href="/blog/slug-2.html">Title 2</a></li>
        <li><a href="/blog/slug-3.html">Title 3</a></li>
      </ul>
    </div>

Plus an optional cross-site block:

    <div class="bvtech-cross-site" data-bvtech-cross="v30">
      <p>Also from Jordan Polasek:
         <a href="https://jordanpolasek.com/blog/slug.html">Title</a></p>
    </div>
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


INDEX_FILE_NAME = "posts_index.json"


_STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "in", "on", "and", "is", "how",
    "why", "what", "your", "with", "from", "by", "at", "are", "its", "it",
    "be", "this", "that", "as", "or", "but", "not", "you", "i", "we",
    "they", "so", "do", "has", "have", "had", "was", "were", "will",
    "can", "should", "would", "could", "may", "might", "about", "into",
    "when", "where", "which", "who", "whom", "whose", "if", "then",
}


def _tokenize(text: str) -> set:
    """Lowercase, strip punctuation, drop stopwords, return set of words."""
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


class PostsIndex:
    """Read/write wrapper around posts_index.json."""

    def __init__(self, app_dir: str):
        self.app_dir = Path(app_dir)
        self.path = self.app_dir / INDEX_FILE_NAME
        self._data: Dict = {"posts": []}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {"posts": []}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            if "posts" not in self._data or not isinstance(self._data["posts"], list):
                self._data = {"posts": []}
        except Exception:
            self._data = {"posts": []}

    def save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # best-effort — never block publishing on index persistence

    @property
    def posts(self) -> List[dict]:
        return list(self._data.get("posts", []))

    def add_post(self, slug: str, title: str, site: str, url: str,
                 focus_keyword: str = "", summary: str = "") -> None:
        """Record a newly published post. Dedups on (site, slug)."""
        existing = [
            p for p in self._data["posts"]
            if not (p.get("site") == site and p.get("slug") == slug)
        ]
        existing.append({
            "slug": slug,
            "title": title,
            "site": site,
            "url": url,
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "focus_keyword": focus_keyword,
            "summary": summary[:200] if summary else "",
        })
        self._data["posts"] = existing
        self.save()

    def pick_related(self, new_title: str, new_focus_keyword: str,
                     site: str, limit: int = 3,
                     exclude_slug: str = "") -> List[dict]:
        """Score existing posts on the same site against the new post's
        keywords/title. Return up to `limit` best matches.
        """
        candidates = [
            p for p in self._data["posts"]
            if p.get("site") == site and p.get("slug") != exclude_slug
        ]
        if not candidates:
            return []

        new_tokens = _tokenize(new_title) | _tokenize(new_focus_keyword)
        if not new_tokens:
            # Nothing to score on — just return most recent
            return sorted(candidates,
                          key=lambda p: p.get("published_at", ""),
                          reverse=True)[:limit]

        scored = []
        for c in candidates:
            c_tokens = (_tokenize(c.get("title", "")) |
                        _tokenize(c.get("focus_keyword", "")))
            overlap = len(new_tokens & c_tokens)
            scored.append((overlap, c.get("published_at", ""), c))

        # Sort: highest overlap first, then most recent
        scored.sort(key=lambda t: (-t[0], t[1] > ""), reverse=True)
        # The second sort key is a hack to make recent ones come first
        # when overlap is equal — actually redo properly:
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [c for _, _, c in scored[:limit]]

    def pick_cross_site(self, site: str, limit: int = 1) -> List[dict]:
        """Pick the most recent post from the OTHER site for a cross-site
        reference block."""
        other_site = "jp" if site == "bvtech" else "bvtech"
        candidates = [
            p for p in self._data["posts"]
            if p.get("site") == other_site
        ]
        candidates.sort(key=lambda p: p.get("published_at", ""), reverse=True)
        return candidates[:limit]


# ============================================================
# HTML INJECTION
# ============================================================
_SITE_LABELS = {
    "bvtech": "BVTech.org",
    "jp": "Jordan Polasek",
}


def build_related_block(related: List[dict], site: str) -> str:
    """Build the 'Related Posts' HTML block."""
    if not related:
        return ""
    label = _SITE_LABELS.get(site, "BVTech.org")
    items = "\n".join(
        f'        <li><a href="{_esc(p.get("url", "#"))}">{_esc(p.get("title", "Read more"))}</a></li>'
        for p in related
    )
    return f'''
<div class="bvtech-related-posts" data-bvtech-related="v30" style="margin-top:2rem;padding:1.25rem 1.5rem;background:#f8fafc;border-left:4px solid #6d28d9;border-radius:6px;">
  <h3 style="margin:0 0 0.5rem;font-size:1.05rem;color:#1e293b;">Related from {_esc(label)}</h3>
  <ul style="margin:0.5rem 0 0;padding-left:1.25rem;">
{items}
  </ul>
</div>
'''


def build_cross_site_block(cross: List[dict], this_site: str) -> str:
    """Build the 'Also from the other site' block."""
    if not cross:
        return ""
    other = "jp" if this_site == "bvtech" else "bvtech"
    label = _SITE_LABELS.get(other, "Jordan Polasek")
    p = cross[0]
    return f'''
<div class="bvtech-cross-site" data-bvtech-cross="v30" style="margin-top:1rem;padding:0.75rem 1rem;background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;font-size:0.95rem;">
  <p style="margin:0;"><strong>Also on {_esc(label)}:</strong>
     <a href="{_esc(p.get("url", "#"))}">{_esc(p.get("title", "Read more"))}</a></p>
</div>
'''


def _esc(s: str) -> str:
    if not s:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;"))


def inject_related_blocks(html: str, related_block: str, cross_block: str) -> str:
    """Inject the related + cross blocks into the new post's HTML.

    Strategy:
      1. If there's an author byline (<div class="author-byline">), insert
         the blocks just BEFORE it.
      2. Otherwise, if there's a </body>, insert just before it.
      3. Otherwise, append to the end.
    """
    blob = (related_block or "") + (cross_block or "")
    if not blob.strip():
        return html

    # Prefer inserting before the byline so the article ends cleanly:
    #   [content] [related] [cross] [byline] [end]
    byline_match = re.search(r'<div[^>]*class="author-byline"', html, re.IGNORECASE)
    if byline_match:
        idx = byline_match.start()
        return html[:idx] + blob + html[idx:]

    # Next best: before </body>
    body_match = re.search(r"</body>", html, re.IGNORECASE)
    if body_match:
        idx = body_match.start()
        return html[:idx] + blob + html[idx:]

    # Fallback: append
    return html + blob


def enrich_post_html(html: str, new_title: str, new_focus_keyword: str,
                     new_slug: str, site: str, app_dir: str) -> Tuple[str, dict]:
    """Main entry point called by the publisher.

    Loads the index, picks related posts, builds the blocks, injects them
    into `html`, and returns (enriched_html, info_dict). Does NOT add the
    new post to the index yet — the caller does that after the deploy
    succeeds, so failed deploys don't pollute the graph.
    """
    index = PostsIndex(app_dir)
    related = index.pick_related(new_title, new_focus_keyword, site,
                                  limit=3, exclude_slug=new_slug)
    cross = index.pick_cross_site(site, limit=1)

    related_block = build_related_block(related, site)
    cross_block = build_cross_site_block(cross, site)
    enriched = inject_related_blocks(html, related_block, cross_block)

    return enriched, {
        "related_count": len(related),
        "related_titles": [p.get("title", "") for p in related],
        "cross_count": len(cross),
        "cross_title": cross[0].get("title", "") if cross else "",
    }


def record_post(app_dir: str, slug: str, title: str, site: str, url: str,
                focus_keyword: str = "", summary: str = "") -> None:
    """Record a successfully published post in the index. Called from
    the publisher AFTER the deploy succeeds."""
    index = PostsIndex(app_dir)
    index.add_post(slug=slug, title=title, site=site, url=url,
                   focus_keyword=focus_keyword, summary=summary)
