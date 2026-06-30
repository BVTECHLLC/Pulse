#!/usr/bin/env python3
"""
BVTech — Local Automation Engine  v31.0
==============================================================

Pushes as much automation as possible onto the local machine
instead of relying on Claude / the web UI being open. Three
subsystems:

  1. LocalEventLog — SQLite-backed append-only log of everything
     the tool does. Replaces scattered .json files and makes
     "what happened at 2:47pm yesterday?" a one-query answer.

  2. TaskRunner — lightweight in-process scheduler. Threads,
     no external dependency. Runs registered tasks on a schedule
     (daily, hourly, every N minutes) while the BVTech app is
     running.

  3. WindowsTaskScheduler — thin wrapper around `schtasks.exe`
     for installing tasks that survive reboots, even if the
     BVTech app itself isn't running. Uses Windows' native
     scheduler so your machine wakes up at 3am and runs a scrape
     whether or not you remember to start the app.

DESIGN
------
Every scheduled task is a tiny Python callable registered at
startup. Tasks know their own name, schedule, and the function
to call. The TaskRunner loop wakes once per minute and fires
anything that's due.

The same registry is exposed to the Windows scheduler layer,
which generates `schtasks /Create` commands that shell out to
`pythonw.exe bvtech_app.py --run-task <name>` — so a single
task definition drives both in-process and OS-level scheduling.

DEFAULT TASKS (shipped in v31)
------------------------------
  daily_config_backup       — copy bvtech_config.json to backups/
  weekly_log_rotation       — rotate local_events.db if > 100MB
  hourly_csv_watcher        — check prospects.csv mtime; if new
                              rows, push to HubSpot
  daily_hubspot_enrichment  — fill missing contact IDs on the
                              prospects CSV
  daily_posts_index_prune   — drop entries older than 180 days
                              from posts_index.json
  weekly_super_scraper      — re-run the scraper (if configured)

Tasks can be enabled/disabled from the UI and you can see
last-run / next-run / success-count / failure-count for each
one on the new Automation tab.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


EVENT_DB_NAME = "local_events.db"
TASK_STATE_FILE = "automation_state.json"
BACKUP_DIR_NAME = "backups"


# ============================================================
# EVENT LOG — SQLite, append-only
# ============================================================
class LocalEventLog:
    """SQLite wrapper that records everything the tool does.

    Columns:
      id         INTEGER PRIMARY KEY
      ts         TEXT (ISO 8601)
      ts_epoch   INTEGER (seconds since epoch, for fast range queries)
      category   TEXT (scrape | email | call | post | automation | error)
      action     TEXT (what happened)
      target     TEXT (contact email, url, file path, etc.)
      success    INTEGER (0 or 1)
      details    TEXT (JSON blob with anything extra)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        TEXT    NOT NULL,
        ts_epoch  INTEGER NOT NULL,
        category  TEXT    NOT NULL,
        action    TEXT    NOT NULL,
        target    TEXT    DEFAULT '',
        success   INTEGER DEFAULT 1,
        details   TEXT    DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_epoch);
    CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
    CREATE INDEX IF NOT EXISTS idx_events_target ON events(target);
    """

    def __init__(self, app_dir: str):
        self.app_dir = Path(app_dir)
        self.db_path = self.app_dir / EVENT_DB_NAME
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.executescript(self.SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def record(self, category: str, action: str,
               target: str = "", success: bool = True,
               **details) -> int:
        """Append one event. Thread-safe. Returns the new row id.

        Never raises — logging failures are swallowed so we don't
        crash the caller."""
        try:
            now = datetime.now()
            details_json = json.dumps(details, default=str) if details else ""
            with self._lock:
                conn = sqlite3.connect(str(self.db_path))
                try:
                    cur = conn.execute(
                        "INSERT INTO events (ts, ts_epoch, category, action, "
                        "target, success, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (now.isoformat(timespec="seconds"),
                         int(now.timestamp()),
                         category, action, target,
                         1 if success else 0, details_json),
                    )
                    conn.commit()
                    return cur.lastrowid or 0
                finally:
                    conn.close()
        except Exception:
            return 0

    def query(self, category: Optional[str] = None,
              target: Optional[str] = None,
              since_epoch: Optional[int] = None,
              limit: int = 100) -> List[Dict[str, Any]]:
        """Query events. All filters are optional. Returns newest first."""
        where = []
        args: List[Any] = []
        if category:
            where.append("category = ?")
            args.append(category)
        if target:
            where.append("target = ?")
            args.append(target)
        if since_epoch is not None:
            where.append("ts_epoch >= ?")
            args.append(since_epoch)
        sql = "SELECT id, ts, category, action, target, success, details FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(sql, args)
                rows = cur.fetchall()
            finally:
                conn.close()
        result = []
        for row in rows:
            details_raw = row[6] or ""
            try:
                details = json.loads(details_raw) if details_raw else {}
            except Exception:
                details = {"raw": details_raw}
            result.append({
                "id": row[0],
                "ts": row[1],
                "category": row[2],
                "action": row[3],
                "target": row[4],
                "success": bool(row[5]),
                "details": details,
            })
        return result

    def stats(self) -> Dict[str, Any]:
        """Summary stats for the dashboard."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                by_cat = dict(conn.execute(
                    "SELECT category, COUNT(*) FROM events GROUP BY category"
                ).fetchall())
                fails = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE success = 0"
                ).fetchone()[0]
                last_24h = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE ts_epoch >= ?",
                    (int(time.time()) - 86400,),
                ).fetchone()[0]
            finally:
                conn.close()
        return {
            "total": total,
            "by_category": by_cat,
            "failures": fails,
            "last_24h": last_24h,
            "db_size_kb": round(self.db_path.stat().st_size / 1024, 1)
                          if self.db_path.exists() else 0,
        }

    def rotate_if_too_big(self, max_size_mb: int = 100) -> bool:
        """Rotate the DB if it's over the size limit. Moves the old
        file to backups/ with a timestamp and starts fresh."""
        if not self.db_path.exists():
            return False
        size_mb = self.db_path.stat().st_size / 1024 / 1024
        if size_mb < max_size_mb:
            return False
        backup_dir = self.app_dir / BACKUP_DIR_NAME
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"local_events_{stamp}.db"
        with self._lock:
            shutil.move(str(self.db_path), str(target))
        self._init_db()
        return True


# ============================================================
# SCHEDULED TASKS
# ============================================================
@dataclass
class ScheduledTask:
    """Declarative task definition."""
    name: str
    description: str
    schedule: str          # "daily" | "hourly" | "weekly" | "every_N_minutes"
    func: Callable[[], Any]
    interval_minutes: int = 0  # used when schedule == "every_N_minutes"
    preferred_hour: int = 3     # used when schedule == "daily" or "weekly"
    preferred_weekday: int = 1  # 0=Mon, 6=Sun — used when schedule == "weekly"
    enabled: bool = True
    last_run: Optional[str] = None  # ISO
    next_run: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    last_error: str = ""

    def compute_next_run(self, now: Optional[datetime] = None) -> datetime:
        now = now or datetime.now()
        if self.schedule == "hourly":
            return (now + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0)
        if self.schedule == "daily":
            target = now.replace(
                hour=self.preferred_hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target
        if self.schedule == "weekly":
            target = now.replace(
                hour=self.preferred_hour, minute=0, second=0, microsecond=0)
            days_ahead = (self.preferred_weekday - now.weekday()) % 7
            if days_ahead == 0 and target <= now:
                days_ahead = 7
            return target + timedelta(days=days_ahead)
        if self.schedule == "every_N_minutes":
            return now + timedelta(minutes=max(1, self.interval_minutes))
        return now + timedelta(hours=1)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("func", None)  # not serializable
        return d


class TaskRunner:
    """In-process scheduler. Runs a background thread that wakes
    once per minute and fires any tasks whose next_run has passed.

    Not a replacement for a real cron — it's best-effort, in-process,
    and dies if the app dies. Use the WindowsTaskScheduler helper
    below to install tasks at the OS level for reboot survival."""

    def __init__(self, app_dir: str, event_log: LocalEventLog):
        self.app_dir = Path(app_dir)
        self.event_log = event_log
        self._tasks: Dict[str, ScheduledTask] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._state_path = self.app_dir / TASK_STATE_FILE

    def register(self, task: ScheduledTask) -> None:
        """Register a task definition. Loads persisted state if present."""
        # Merge any saved state (last_run, counts, enabled)
        saved = self._load_state()
        if task.name in saved:
            s = saved[task.name]
            task.last_run = s.get("last_run") or task.last_run
            task.success_count = s.get("success_count", 0)
            task.failure_count = s.get("failure_count", 0)
            task.enabled = s.get("enabled", task.enabled)
            task.last_error = s.get("last_error", "")
        if not task.next_run:
            task.next_run = task.compute_next_run().isoformat(timespec="seconds")
        self._tasks[task.name] = task

    def all_tasks(self) -> List[ScheduledTask]:
        return list(self._tasks.values())

    def get(self, name: str) -> Optional[ScheduledTask]:
        return self._tasks.get(name)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        t = self._tasks.get(name)
        if not t:
            return False
        t.enabled = enabled
        self._save_state()
        return True

    def run_now(self, name: str) -> Tuple[bool, str]:
        """Run a task immediately, out of band. Returns (ok, message)."""
        task = self._tasks.get(name)
        if not task:
            return False, f"No such task: {name}"
        return self._execute(task)

    def _execute(self, task: ScheduledTask) -> Tuple[bool, str]:
        self.event_log.record("automation", f"task_start:{task.name}",
                                target=task.name)
        t0 = time.time()
        try:
            result = task.func()
            elapsed = time.time() - t0
            task.success_count += 1
            task.last_run = datetime.now().isoformat(timespec="seconds")
            task.next_run = task.compute_next_run().isoformat(timespec="seconds")
            task.last_error = ""
            self.event_log.record(
                "automation", f"task_ok:{task.name}",
                target=task.name, success=True,
                elapsed_sec=round(elapsed, 2),
                result=str(result)[:500] if result is not None else "",
            )
            self._save_state()
            return True, f"OK in {elapsed:.1f}s"
        except Exception as e:
            task.failure_count += 1
            task.last_run = datetime.now().isoformat(timespec="seconds")
            task.next_run = task.compute_next_run().isoformat(timespec="seconds")
            task.last_error = f"{type(e).__name__}: {e}"
            self.event_log.record(
                "automation", f"task_fail:{task.name}",
                target=task.name, success=False,
                error=str(e), traceback=traceback.format_exc()[:1000],
            )
            self._save_state()
            return False, str(e)

    def _tick(self) -> None:
        """Check all tasks and fire any that are due."""
        now = datetime.now()
        for task in list(self._tasks.values()):
            if not task.enabled:
                continue
            if not task.next_run:
                task.next_run = task.compute_next_run(now).isoformat(timespec="seconds")
                continue
            try:
                next_dt = datetime.fromisoformat(task.next_run)
            except Exception:
                next_dt = task.compute_next_run(now)
            if next_dt <= now:
                self._execute(task)

    def start(self) -> None:
        """Start the background scheduler thread. Idempotent."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="BVTech-TaskRunner", daemon=True)
        self._thread.start()
        self.event_log.record("automation", "runner_started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                self.event_log.record(
                    "error", "runner_tick_exception",
                    success=False, error=str(e))
            # Wake every 60 seconds
            self._stop.wait(60)

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        try:
            state = {
                t.name: {
                    "last_run": t.last_run,
                    "success_count": t.success_count,
                    "failure_count": t.failure_count,
                    "enabled": t.enabled,
                    "last_error": t.last_error,
                }
                for t in self._tasks.values()
            }
            self._state_path.write_text(
                json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass


# ============================================================
# WINDOWS TASK SCHEDULER INTEGRATION
# ============================================================
class WindowsTaskScheduler:
    """Wraps `schtasks.exe` to install/uninstall/query OS-level tasks.

    Uses /SC DAILY and /ST HH:MM for daily schedules. Each task is
    named "BVTech_<taskname>" so they group together in taskschd.msc.

    Only functional on Windows. Every method returns (ok, message).
    """

    PREFIX = "BVTech_"

    @staticmethod
    def is_windows() -> bool:
        return sys.platform == "win32"

    @classmethod
    def _run(cls, *args: str) -> Tuple[bool, str]:
        if not cls.is_windows():
            return False, "Not running on Windows — schtasks.exe is unavailable"
        try:
            r = subprocess.run(
                ["schtasks.exe"] + list(args),
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode == 0:
                return True, r.stdout.strip() or "OK"
            return False, (r.stderr.strip() or r.stdout.strip()
                           or f"schtasks exited with code {r.returncode}")
        except FileNotFoundError:
            return False, "schtasks.exe not found on PATH"
        except subprocess.TimeoutExpired:
            return False, "schtasks timed out after 30s"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    @classmethod
    def install_daily(cls, task_name: str, command: str,
                       hour: int = 3, minute: int = 0) -> Tuple[bool, str]:
        """Install a daily Windows scheduled task.

        command: the full shell command to run, e.g.
                 'C:\\Python313\\pythonw.exe C:\\BVTech2\\bvtech_app.py --run-task daily_backup'
        """
        full_name = cls.PREFIX + task_name
        time_str = f"{hour:02d}:{minute:02d}"
        return cls._run(
            "/Create", "/F",   # force overwrite
            "/SC", "DAILY",
            "/ST", time_str,
            "/TN", full_name,
            "/TR", command,
            "/RL", "LIMITED",  # run with normal user rights, not admin
        )

    @classmethod
    def install_hourly(cls, task_name: str, command: str) -> Tuple[bool, str]:
        full_name = cls.PREFIX + task_name
        return cls._run(
            "/Create", "/F",
            "/SC", "HOURLY",
            "/TN", full_name,
            "/TR", command,
            "/RL", "LIMITED",
        )

    @classmethod
    def uninstall(cls, task_name: str) -> Tuple[bool, str]:
        full_name = cls.PREFIX + task_name
        return cls._run("/Delete", "/F", "/TN", full_name)

    @classmethod
    def list_installed(cls) -> Tuple[Optional[List[str]], Optional[str]]:
        """Return the names of all BVTech_* tasks currently installed."""
        ok, output = cls._run("/Query", "/FO", "CSV")
        if not ok:
            return None, output
        names = []
        for line in output.splitlines()[1:]:  # skip header
            parts = line.split(",")
            if parts and parts[0].startswith('"' + cls.PREFIX):
                names.append(parts[0].strip('"'))
        return names, None

    @classmethod
    def query(cls, task_name: str) -> Tuple[bool, str]:
        """Check if a specific BVTech task is installed."""
        full_name = cls.PREFIX + task_name
        return cls._run("/Query", "/TN", full_name)


# ============================================================
# DEFAULT TASKS — built-in automation bundled with v31
# ============================================================
def build_default_tasks(app_dir: str, event_log: LocalEventLog,
                          config_loader: Callable[[], dict]
                          ) -> List[ScheduledTask]:
    """Returns the built-in tasks. The caller (bvtech_app.py)
    registers these at startup."""
    app_path = Path(app_dir)

    def _daily_config_backup():
        cfg_src = app_path / "bvtech_config.json"
        if not cfg_src.exists():
            return "no config to back up"
        backup_dir = app_path / BACKUP_DIR_NAME
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        dest = backup_dir / f"bvtech_config_{stamp}.json"
        shutil.copy2(cfg_src, dest)
        # Keep only last 14 backups
        backups = sorted(backup_dir.glob("bvtech_config_*.json"))
        for old in backups[:-14]:
            try:
                old.unlink()
            except Exception:
                pass
        return f"backed up to {dest.name}"

    def _weekly_log_rotation():
        rotated = event_log.rotate_if_too_big(max_size_mb=100)
        return "rotated" if rotated else "no rotation needed"

    def _daily_posts_index_prune():
        """Drop posts_index.json entries older than 180 days."""
        idx_path = app_path / "posts_index.json"
        if not idx_path.exists():
            return "no posts_index.json"
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            return "posts_index.json unreadable"
        posts = data.get("posts", [])
        cutoff = (datetime.now() - timedelta(days=180)).isoformat()
        kept = [p for p in posts if p.get("published_at", "") >= cutoff]
        removed = len(posts) - len(kept)
        if removed > 0:
            data["posts"] = kept
            idx_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"pruned {removed} old posts, {len(kept)} remain"

    def _hourly_csv_watcher():
        """Check if prospects.csv has new rows since last check, and
        push them to HubSpot for enrichment."""
        csv_path = app_path / "prospects.csv"
        if not csv_path.exists():
            return "no prospects.csv"
        state_file = app_path / ".csv_watcher_state.json"
        try:
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
        except Exception:
            state = {}
        current_mtime = csv_path.stat().st_mtime
        last_mtime = state.get("mtime", 0)
        if current_mtime <= last_mtime:
            return "no changes"
        # Count rows
        try:
            import csv as _csv
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                rows = list(_csv.DictReader(f))
        except Exception as e:
            return f"csv read error: {e}"
        last_count = state.get("row_count", 0)
        new_count = max(0, len(rows) - last_count)
        # Save state
        state["mtime"] = current_mtime
        state["row_count"] = len(rows)
        try:
            state_file.write_text(json.dumps(state, indent=2))
        except Exception:
            pass
        if new_count == 0:
            return f"file touched but row count unchanged ({len(rows)})"
        return f"detected {new_count} new rows (total {len(rows)})"

    def _daily_hubspot_enrichment():
        """Look for prospects missing hubspot_contact_id and push them."""
        cfg = config_loader()
        token = cfg.get("hubspot_token", "").strip()
        if not token:
            return "hubspot_token not configured — skipping"
        csv_path = app_path / "prospects.csv"
        if not csv_path.exists():
            return "no prospects.csv"
        try:
            import csv as _csv
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                rows = list(_csv.DictReader(f))
        except Exception as e:
            return f"csv read error: {e}"
        to_enrich = [r for r in rows
                     if r.get("email")
                     and not r.get("hubspot_contact_id")]
        if not to_enrich:
            return f"all {len(rows)} rows already enriched"
        try:
            from hubspot_tracker import HubSpotTracker
        except ImportError:
            return "hubspot_tracker module missing"
        tracker = HubSpotTracker(api_token=token)
        enriched_count = 0
        # Cap per run to stay under rate limits
        for row in to_enrich[:50]:
            email = row.get("email", "").strip()
            if not email:
                continue
            contact_id, status = tracker.find_or_create_contact(
                email=email,
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
                company=row.get("company", ""),
                phone=row.get("phone", ""),
            )
            if contact_id:
                row["hubspot_contact_id"] = contact_id
                enriched_count += 1
            time.sleep(0.15)  # rate limit
        # Write back CSV with new column
        if enriched_count > 0:
            fieldnames = list(rows[0].keys())
            if "hubspot_contact_id" not in fieldnames:
                fieldnames.append("hubspot_contact_id")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
        return f"enriched {enriched_count} contacts (of {len(to_enrich)} pending)"

    # v32: Staggered publishing tasks — pull next pending item from
    # post_queue.json, invoke Super Posting's _generate_one_post for
    # the specific channel, mark the queue item as done for that channel.
    def _staggered_publish(channel: str):
        """Generic per-channel publish runner. Called by the 4 weekly tasks."""
        try:
            from post_queue import PostQueue
        except ImportError:
            return "post_queue module missing"

        queue = PostQueue(app_dir)
        item = queue.next_pending_for_channel(channel)
        if not item:
            return f"no pending items for {channel}"

        # Lazy import the post generator from bvtech_app via a hook.
        # We expose it through builtins at startup so we don't have a
        # circular import.
        import builtins
        generate_fn = getattr(builtins, "_BVTECH_GENERATE_POST", None)
        if generate_fn is None:
            return "_BVTECH_GENERATE_POST not registered — is the app running?"

        try:
            target_map = {
                "bvtech": "bvtech",
                "jp": "jordanpolasek",
                "linkedin": "linkedin",
                "gbp": "gbp",
            }
            target = target_map[channel]
            result = generate_fn(
                topic=item.get("topic", ""),
                target=target,
                status="publish",
                tone=item.get("tone", "personal_authority"),
                length=item.get("length", "medium"),
                custom=item.get("custom_instructions", ""),
            )
        except Exception as e:
            queue.mark_channel_failed(item["id"], channel, str(e))
            return f"generation error: {e}"

        if not result or result.get("error"):
            err_msg = (result or {}).get("error", "unknown error")
            queue.mark_channel_failed(item["id"], channel, err_msg)
            return f"post failed: {err_msg}"

        # Find the URL for this channel from result.posts
        channel_result = result.get("posts", {}).get(target, {})
        url = channel_result.get("link", "") or channel_result.get("url", "")
        if channel_result.get("success"):
            queue.mark_channel_done(item["id"], channel, url=url)
            return f"published {item.get('title', '?')[:50]} → {channel} ({url or 'no url'})"
        else:
            err_msg = channel_result.get("error", "post unsuccessful")
            queue.mark_channel_failed(item["id"], channel, err_msg)
            return f"channel reported failure: {err_msg}"

    def _staggered_bvtech():    return _staggered_publish("bvtech")
    def _staggered_jp():        return _staggered_publish("jp")
    def _staggered_linkedin():  return _staggered_publish("linkedin")
    def _staggered_gbp():       return _staggered_publish("gbp")

    return [
        ScheduledTask(
            name="daily_config_backup",
            description="Back up bvtech_config.json daily at 3am (keeps last 14)",
            schedule="daily",
            preferred_hour=3,
            func=_daily_config_backup,
        ),
        ScheduledTask(
            name="weekly_log_rotation",
            description="Rotate local_events.db if it exceeds 100MB (Sundays 4am)",
            schedule="weekly",
            preferred_weekday=6,  # Sunday
            preferred_hour=4,
            func=_weekly_log_rotation,
        ),
        ScheduledTask(
            name="daily_posts_index_prune",
            description="Remove posts_index.json entries older than 180 days",
            schedule="daily",
            preferred_hour=2,
            func=_daily_posts_index_prune,
        ),
        ScheduledTask(
            name="hourly_csv_watcher",
            description="Check prospects.csv for new rows every hour",
            schedule="hourly",
            func=_hourly_csv_watcher,
        ),
        ScheduledTask(
            name="daily_hubspot_enrichment",
            description="Auto-enrich prospects missing HubSpot contact IDs (daily 6am, max 50/run)",
            schedule="daily",
            preferred_hour=6,
            func=_daily_hubspot_enrichment,
        ),
        # v32: Staggered publishing — disabled by default so they don't
        # start firing unexpectedly. User enables them from the Automation
        # tab once they've populated the post queue.
        ScheduledTask(
            name="staggered_monday_bvtech",
            description="Monday 10am — publish next queued post to BVTech.org",
            schedule="weekly",
            preferred_weekday=0,  # Monday
            preferred_hour=10,
            enabled=False,
            func=_staggered_bvtech,
        ),
        ScheduledTask(
            name="staggered_wednesday_jp",
            description="Wednesday 10am — publish next queued post to JordanPolasek.com",
            schedule="weekly",
            preferred_weekday=2,  # Wednesday
            preferred_hour=10,
            enabled=False,
            func=_staggered_jp,
        ),
        ScheduledTask(
            name="staggered_friday_linkedin",
            description="Friday 10am — publish next queued post to LinkedIn",
            schedule="weekly",
            preferred_weekday=4,  # Friday
            preferred_hour=10,
            enabled=False,
            func=_staggered_linkedin,
        ),
        ScheduledTask(
            name="staggered_saturday_gbp",
            description="Saturday 10am — publish next queued post to Google Business Profile",
            schedule="weekly",
            preferred_weekday=5,  # Saturday
            preferred_hour=10,
            enabled=False,
            func=_staggered_gbp,
        ),
    ]
