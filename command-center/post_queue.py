#!/usr/bin/env python3
"""
BVTech — Post Queue + Staggered Scheduler helpers  v32.0
==============================================================

The "All 4 Channels" target in Super Posting publishes to every
channel at once. That's great for quick wins but looks spammy if
you do it 3x a week — every platform sees the same content land
at the same time, and Google's de-dup filter penalizes you.

The staggered publishing model instead:

  Monday     → BVTech.org
  Wednesday  → JordanPolasek.com
  Friday     → LinkedIn
  Saturday   → Google Business Profile

Same master article, different channels, different days, each
rewritten for its channel voice (handled by channel_rewriter.py).
Across a week every channel gets the content, but they're
staggered so it doesn't look coordinated from a platform's view.

This module manages the queue of posts waiting to be published:

  post_queue.json format
  ----------------------
    {
      "queue": [
        {
          "id": "q_1712700000_1",
          "added_at": "2026-04-09T22:00:00",
          "title": "5 Cybersecurity Wins for Houston SMBs",
          "topic": "cybersecurity houston smb",
          "tone": "personal_authority",
          "length": "medium",
          "custom_instructions": "",
          "status": "pending",   // pending | in_progress | done | failed
          "channels_done": [],    // e.g. ["bvtech", "jp"]
          "channels_failed": [],
          "last_attempt": null,
          "last_error": ""
        }
      ]
    }

The TaskRunner tasks in local_automation.py pull from the head
of this queue on their scheduled day and publish to their
specific channel. When all 4 channels are done, the item is
marked "done" and stays in the queue for history.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


QUEUE_FILE_NAME = "post_queue.json"


class PostQueue:
    """Thread-safe read/write wrapper around post_queue.json."""

    def __init__(self, app_dir: str):
        self.app_dir = Path(app_dir)
        self.path = self.app_dir / QUEUE_FILE_NAME
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {"queue": []}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            if "queue" not in self._data or not isinstance(self._data["queue"], list):
                self._data = {"queue": []}
        except Exception:
            self._data = {"queue": []}

    def _save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @property
    def queue(self) -> List[dict]:
        with self._lock:
            return list(self._data.get("queue", []))

    def add(self, title: str, topic: str = "",
            tone: str = "personal_authority",
            length: str = "medium",
            custom_instructions: str = "") -> str:
        """Add a new item to the end of the queue. Returns the item id."""
        with self._lock:
            ts = int(time.time())
            idx = len([q for q in self._data["queue"]
                       if q.get("added_at", "")[:10] == datetime.now().date().isoformat()])
            item_id = f"q_{ts}_{idx + 1}"
            self._data["queue"].append({
                "id": item_id,
                "added_at": datetime.now().isoformat(timespec="seconds"),
                "title": title,
                "topic": topic,
                "tone": tone,
                "length": length,
                "custom_instructions": custom_instructions,
                "status": "pending",
                "channels_done": [],
                "channels_failed": [],
                "last_attempt": None,
                "last_error": "",
            })
            self._save()
            return item_id

    def remove(self, item_id: str) -> bool:
        """Remove an item from the queue by id."""
        with self._lock:
            before = len(self._data["queue"])
            self._data["queue"] = [
                q for q in self._data["queue"] if q.get("id") != item_id
            ]
            changed = len(self._data["queue"]) != before
            if changed:
                self._save()
            return changed

    def next_pending_for_channel(self, channel: str) -> Optional[dict]:
        """Find the oldest pending item that hasn't been published to
        `channel` yet. Returns None if nothing pending."""
        with self._lock:
            for item in self._data["queue"]:
                if item.get("status") in ("done", "failed"):
                    continue
                if channel in item.get("channels_done", []):
                    continue
                return dict(item)
        return None

    def mark_channel_done(self, item_id: str, channel: str,
                           url: str = "") -> bool:
        """Mark a specific channel as completed for an item. If all 4
        channels are now done, mark the item as done overall."""
        with self._lock:
            for item in self._data["queue"]:
                if item.get("id") != item_id:
                    continue
                if channel not in item.get("channels_done", []):
                    item.setdefault("channels_done", []).append(channel)
                    if url:
                        item.setdefault("urls", {})[channel] = url
                item["last_attempt"] = datetime.now().isoformat(timespec="seconds")
                done_set = set(item.get("channels_done", []))
                if done_set >= {"bvtech", "jp", "linkedin", "gbp"}:
                    item["status"] = "done"
                else:
                    item["status"] = "in_progress"
                self._save()
                return True
        return False

    def mark_channel_failed(self, item_id: str, channel: str,
                             error: str) -> bool:
        """Record that a specific channel failed for an item."""
        with self._lock:
            for item in self._data["queue"]:
                if item.get("id") != item_id:
                    continue
                if channel not in item.get("channels_failed", []):
                    item.setdefault("channels_failed", []).append(channel)
                item["last_attempt"] = datetime.now().isoformat(timespec="seconds")
                item["last_error"] = f"{channel}: {error}"[:500]
                # Mark as failed if all 4 channels errored with no successes
                failed_set = set(item.get("channels_failed", []))
                done_set = set(item.get("channels_done", []))
                if (failed_set | done_set) >= {"bvtech", "jp", "linkedin", "gbp"} \
                        and not done_set:
                    item["status"] = "failed"
                self._save()
                return True
        return False

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            q = self._data.get("queue", [])
            return {
                "total": len(q),
                "pending": sum(1 for i in q if i.get("status") == "pending"),
                "in_progress": sum(1 for i in q if i.get("status") == "in_progress"),
                "done": sum(1 for i in q if i.get("status") == "done"),
                "failed": sum(1 for i in q if i.get("status") == "failed"),
            }
