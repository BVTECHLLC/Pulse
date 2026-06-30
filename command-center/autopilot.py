#!/usr/bin/env python3
"""
BVTech AutoPilot v3 — WARMODE: Aggressive Self-Building Daemon
================================================================
WARMODE = aggressive build mode that pumps out improvements nonstop.

WORKERS (each on its own thread):
  - WARMODE Builder — generates/applies/tests code changes at max speed
  - Health Monitor — checks all endpoints, auto-heals failures
  - Error Healer — watches error journal, auto-patches bugs
  - Compliance Scanner — CAN-SPAM/TCPA/DNC
  - Auto Scraper — scrapes new prospects on schedule
  - Auto Email — drip campaigns on autopilot
  - Auto Backup — snapshots before every code change
  - Nightly Build — 2am deep review + queue generation
  - Report Generator — daily summary
"""

import json, os, sys, time, threading, traceback, csv, shutil, subprocess
from datetime import datetime
from pathlib import Path
from collections import deque

try:
    import requests
except ImportError:
    pass


class FileWriteLock:
    """Thread-safe file write lock."""
    def __init__(self):
        self._locks = {}
        self._master = threading.Lock()

    def acquire(self, name, timeout=30):
        with self._master:
            if name not in self._locks:
                self._locks[name] = threading.Lock()
        return self._locks[name].acquire(timeout=timeout)

    def release(self, name):
        with self._master:
            if name in self._locks:
                try: self._locks[name].release()
                except RuntimeError: pass


class WorkerStatus:
    def __init__(self, name):
        self.name = name
        self.running = False
        self.last_run = None
        self.last_result = None
        self.runs = 0
        self.errors = 0
        self.successes = 0

    def to_dict(self):
        return {
            "name": self.name, "running": self.running,
            "last_run": self.last_run, "last_result": self.last_result,
            "runs": self.runs, "errors": self.errors, "successes": self.successes,
        }


class AutoPilot:
    def __init__(self, brain, app_port=5678):
        self.brain = brain
        self.app_port = app_port
        self.running = False
        self.warmode = False
        self.file_lock = FileWriteLock()

        self.workers = {
            "health": WorkerStatus("Health Monitor"),
            "compliance": WorkerStatus("Compliance Scanner"),
            "build": WorkerStatus("WARMODE Builder"),
            "scraper": WorkerStatus("Auto Scraper"),
            "email": WorkerStatus("Auto Email"),
            "backup": WorkerStatus("Auto Backup"),
            "error_heal": WorkerStatus("Error Healer"),
            "report": WorkerStatus("Report Generator"),
        }
        self._threads = {}

        self.status = {
            "running": False, "warmode": False, "warmode_speed": "normal",
            "health_ok": True, "errors_found": 0, "errors_fixed": 0,
            "improvements_made": 0, "builds_completed": 0,
            "tests_passed": 0, "tests_failed": 0,
            "prospects_scraped": 0, "emails_sent": 0,
            "uptime_start": None, "cycles": 0,
            "current_task": None, "last_build_time": None,
        }

        self.improvement_queue = self._load_json("autopilot_queue.json", [])
        self.build_history = self._load_json("autopilot_build_history.json", [])
        self.log_lines = deque(maxlen=1000)
        self.auto_settings = self._load_settings()

    # ── Logging ──────────────────────────────────────────────
    def _log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        icons = {"info":"ℹ️","success":"✅","error":"❌","warn":"⚠️",
                 "build":"🧬","war":"⚔️","scrape":"🔍","email":"📧",
                 "health":"💚","test":"🧪","backup":"💾"}
        line = f"[{ts}] {icons.get(level,'📌')} {msg}"
        self.log_lines.append(line)
        print(f"  [AutoPilot] {icons.get(level,'📌')} {msg}")

    # ── Persistence helpers ──────────────────────────────────
    def _json_path(self, name):
        return os.path.join(self.brain.app_dir, name)

    def _load_json(self, name, default):
        try:
            p = self._json_path(name)
            if os.path.exists(p):
                with open(p, "r") as f: return json.load(f)
        except: pass
        return default

    def _save_json(self, name, data):
        try:
            with open(self._json_path(name), "w") as f:
                json.dump(data, f, indent=2, default=str)
        except: pass

    def _load_settings(self):
        defaults = {
            "warmode_enabled": False, "warmode_speed": "normal",
            "auto_scrape": False, "scrape_interval_min": 60,
            "auto_email": False, "email_interval_min": 120,
            "auto_health": True, "health_interval_sec": 300,
            "auto_compliance": True, "compliance_interval_min": 60,
            "auto_report": False, "report_hour": 18,
            "auto_backup": True, "backup_interval_min": 30,
            "auto_error_heal": True, "heal_interval_sec": 60,
            "daytime_mode": True, "max_builds_per_hour": 10,
            "test_after_build": True, "nightly_build_hour": 2,
        }
        saved = self._load_json("autopilot_settings.json", {})
        return {**defaults, **saved}

    def save_auto_settings(self):
        self._save_json("autopilot_settings.json", self.auto_settings)

    def update_settings(self, new):
        self.auto_settings.update(new)
        self.save_auto_settings()
        self.warmode = self.auto_settings.get("warmode_enabled", False)
        self.status["warmode"] = self.warmode
        self.status["warmode_speed"] = self.auto_settings.get("warmode_speed", "normal")

    def add_to_queue(self, task):
        self.improvement_queue.append({
            "task": task, "added": datetime.now().isoformat(),
            "status": "pending", "attempts": 0, "priority": "normal",
        })
        self._save_json("autopilot_queue.json", self.improvement_queue)
        self._log(f"Queued: {task[:60]}...", "build")

    # ── Self-Tests ───────────────────────────────────────────
    def run_self_tests(self):
        self._log("Running self-tests...", "test")
        results = []
        passed = failed = 0

        endpoints = [
            ("GET", "/", 200, "Homepage"),
            ("GET", "/api/config", 200, "Config API"),
            ("GET", "/api/ai/status", 200, "AI Status"),
            ("GET", "/api/pilot/status", 200, "Pilot Status"),
        ]
        for method, path, expected, desc in endpoints:
            try:
                r = requests.get(f"http://127.0.0.1:{self.app_port}{path}", timeout=10)
                ok = r.status_code == expected
                results.append({"test": desc, "path": path, "passed": ok, "actual": r.status_code})
                if ok: passed += 1
                else: failed += 1
            except Exception as e:
                results.append({"test": desc, "passed": False, "error": str(e)})
                failed += 1

        for fname in self.brain.ALLOWED_FILES:
            content, _ = self.brain.read_file(fname)
            if content:
                try:
                    compile(content, fname, "exec")
                    results.append({"test": f"Syntax: {fname}", "passed": True})
                    passed += 1
                except SyntaxError as e:
                    results.append({"test": f"Syntax: {fname}", "passed": False, "error": str(e)})
                    failed += 1

        self.status["tests_passed"] = self.status.get("tests_passed", 0) + passed
        self.status["tests_failed"] = self.status.get("tests_failed", 0) + failed
        self._log(f"Tests: {passed}✅ {failed}❌", "success" if failed == 0 else "warn")
        return passed, failed, results

    # ── Backup ───────────────────────────────────────────────
    def create_backup(self, label="auto"):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = os.path.join(self.brain.app_dir, "backups", f"{label}_{ts}")
        os.makedirs(bdir, exist_ok=True)
        ct = 0
        for fname in self.brain.ALLOWED_FILES:
            src = os.path.join(self.brain.app_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(bdir, fname))
                ct += 1
        for cfg in ["bvtech_config.json","autopilot_queue.json","autopilot_settings.json"]:
            src = os.path.join(self.brain.app_dir, cfg)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(bdir, cfg))
        # Cleanup old
        broot = os.path.join(self.brain.app_dir, "backups")
        if os.path.exists(broot):
            dirs = sorted(Path(broot).iterdir(), key=lambda d: d.stat().st_mtime)
            while len(dirs) > 20:
                shutil.rmtree(str(dirs.pop(0)), ignore_errors=True)
        self._log(f"Backup: {bdir} ({ct} files)", "backup")
        return bdir

    def list_backups(self):
        broot = os.path.join(self.brain.app_dir, "backups")
        if not os.path.exists(broot): return []
        dirs = sorted(Path(broot).iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)
        return [{"name": d.name, "path": str(d)} for d in dirs[:20]]

    def restore_backup(self, bdir):
        if not os.path.exists(bdir): return False, "Not found"
        ct = 0
        for f in os.listdir(bdir):
            shutil.copy2(os.path.join(bdir, f), os.path.join(self.brain.app_dir, f))
            ct += 1
        self._log(f"Restored {ct} files from {bdir}", "backup")
        return True, f"Restored {ct} files"

    # ── Health Worker ────────────────────────────────────────
    def _health_worker(self):
        w = self.workers["health"]; w.running = True
        while self.running and self.auto_settings.get("auto_health", True):
            try:
                ok = self.run_health_check()
                w.runs += 1; w.last_run = datetime.now().isoformat()
                w.last_result = "OK" if ok else "FAILED"
                w.successes += 1 if ok else 0
                if not ok: w.errors += 1
            except: w.errors += 1
            time.sleep(self.auto_settings.get("health_interval_sec", 300))
        w.running = False

    def run_health_check(self):
        try:
            ok = True
            for ep in ["/api/config", "/api/ai/status"]:
                r = requests.get(f"http://127.0.0.1:{self.app_port}{ep}", timeout=8)
                if r.status_code != 200: ok = False
            self.status["health_ok"] = ok
            return ok
        except Exception as e:
            self.status["health_ok"] = False
            return False

    # ── Error Healer Worker ──────────────────────────────────
    def _error_heal_worker(self):
        w = self.workers["error_heal"]; w.running = True
        while self.running and self.auto_settings.get("auto_error_heal", True):
            try:
                self.brain.reload_config()
                if self.brain.api_key:
                    self._check_and_fix_errors()
                w.runs += 1; w.last_run = datetime.now().isoformat()
            except: w.errors += 1
            time.sleep(self.auto_settings.get("heal_interval_sec", 60))
        w.running = False

    def _check_and_fix_errors(self):
        unfixed = [e for e in self.brain.error_journal.get("errors", []) if not e.get("fixed")]
        if not unfixed: return
        error = unfixed[-1]
        self._log(f"Healing: {error['error'][:80]}...", "health")
        if self.file_lock.acquire("_heal", timeout=15):
            try:
                result = self.brain.diagnose_and_fix(error["error"])
                if result.get("files_modified"):
                    self.status["errors_fixed"] += 1
                    self.workers["error_heal"].successes += 1
                    self._log(f"Fixed: {result['files_modified']}", "success")
            except: pass
            finally:
                self.file_lock.release("_heal")

    # ── Compliance Worker ────────────────────────────────────
    def _compliance_worker(self):
        w = self.workers["compliance"]; w.running = True
        while self.running and self.auto_settings.get("auto_compliance", True):
            try:
                issues = self.run_compliance_check()
                w.runs += 1; w.last_run = datetime.now().isoformat()
                w.last_result = f"{len(issues)} issues" if issues else "OK"
            except: w.errors += 1
            time.sleep(self.auto_settings.get("compliance_interval_min", 60) * 60)
        w.running = False

    def run_compliance_check(self):
        issues = []
        checks = [
            ("email_campaign.py", [("unsubscribe","CAN-SPAM: unsubscribe"),("physical_address","CAN-SPAM: address")]),
            ("sms_campaign.py", [("stop","TCPA: STOP"),("opt","TCPA: opt-in")]),
            ("power_dialer.py", [("block","DNC: blocked check")]),
        ]
        for fname, fc in checks:
            code, _ = self.brain.read_file(fname)
            if code:
                cl = code.lower()
                for kw, issue in fc:
                    if kw not in cl: issues.append(f"{fname}: {issue}")
        return issues

    # ── Auto Scraper Worker ──────────────────────────────────
    def _scraper_worker(self):
        w = self.workers["scraper"]; w.running = True
        while self.running and self.auto_settings.get("auto_scrape", False):
            try:
                hour = datetime.now().hour
                if 7 <= hour <= 22:
                    self._log("Auto-scrape...", "scrape")
                    self._run_subprocess(["prospect_scraper.py", "--max", "50"])
                    w.runs += 1; w.successes += 1
                    w.last_run = datetime.now().isoformat()
            except: w.errors += 1
            time.sleep(self.auto_settings.get("scrape_interval_min", 60) * 60)
        w.running = False

    # ── Auto Email Worker ────────────────────────────────────
    def _email_worker(self):
        w = self.workers["email"]; w.running = True
        while self.running and self.auto_settings.get("auto_email", False):
            try:
                hour = datetime.now().hour
                if 8 <= hour <= 18:
                    self._log("Auto-email batch...", "email")
                    self._run_subprocess(["email_campaign.py", "--warmup"])
                    w.runs += 1; w.successes += 1
                    w.last_run = datetime.now().isoformat()
            except: w.errors += 1
            time.sleep(self.auto_settings.get("email_interval_min", 120) * 60)
        w.running = False

    # ── Auto Backup Worker ───────────────────────────────────
    def _backup_worker(self):
        w = self.workers["backup"]; w.running = True
        while self.running and self.auto_settings.get("auto_backup", True):
            try:
                self.create_backup("auto")
                w.runs += 1; w.successes += 1; w.last_run = datetime.now().isoformat()
            except: w.errors += 1
            time.sleep(self.auto_settings.get("backup_interval_min", 30) * 60)
        w.running = False

    # ── Report Worker ────────────────────────────────────────
    def _report_worker(self):
        w = self.workers["report"]; w.running = True
        last_date = None
        while self.running and self.auto_settings.get("auto_report", False):
            try:
                now = datetime.now()
                today = now.date().isoformat()
                if now.hour == self.auto_settings.get("report_hour", 18) and last_date != today:
                    report = {
                        "date": today,
                        "builds": self.status.get("builds_completed", 0),
                        "errors_fixed": self.status.get("errors_fixed", 0),
                        "tests_passed": self.status.get("tests_passed", 0),
                        "improvements": self.status.get("improvements_made", 0),
                        "workers": {k: v.to_dict() for k, v in self.workers.items()},
                    }
                    rdir = os.path.join(self.brain.app_dir, "reports")
                    os.makedirs(rdir, exist_ok=True)
                    with open(os.path.join(rdir, f"report_{today}.json"), "w") as f:
                        json.dump(report, f, indent=2, default=str)
                    w.runs += 1; w.successes += 1; last_date = today
                    self._log("Daily report saved", "success")
            except: w.errors += 1
            time.sleep(300)
        w.running = False

    # ══════════════════════════════════════════════════════════
    # ⚔️  WARMODE — THE AGGRESSIVE SELF-BUILDER
    # ══════════════════════════════════════════════════════════
    def _build_worker(self):
        w = self.workers["build"]; w.running = True
        builds_this_hour = 0
        hour_start = time.time()

        while self.running and self.auto_settings.get("warmode_enabled", False):
            try:
                self.brain.reload_config()
                if not self.brain.api_key:
                    time.sleep(60); continue

                # Rate limit
                speed = self.auto_settings.get("warmode_speed", "normal")
                max_h = self.auto_settings.get("max_builds_per_hour", 10)
                if speed == "aggressive": max_h = min(max_h * 2, 30)
                elif speed == "ludicrous": max_h = min(max_h * 4, 60)

                if time.time() - hour_start >= 3600:
                    builds_this_hour = 0; hour_start = time.time()
                if builds_this_hour >= max_h:
                    self._log(f"Rate limit ({max_h}/hr). Cooling...", "war")
                    time.sleep(120); continue

                # Daytime check
                if self.auto_settings.get("daytime_mode", True):
                    if not (8 <= datetime.now().hour <= 22):
                        time.sleep(600); continue

                # Get or generate task
                task = self._get_next_task()
                if not task:
                    self._generate_ideas()
                    task = self._get_next_task()
                if not task:
                    time.sleep(300); continue

                # ⚔️ BUILD
                self.status["current_task"] = task["task"][:80]
                self._log(f"⚔️ BUILD: {task['task'][:70]}...", "war")

                if self.auto_settings.get("auto_backup", True):
                    self.create_backup(f"pre_build")

                task["attempts"] = task.get("attempts", 0) + 1
                task["last_attempt"] = datetime.now().isoformat()

                if not self.file_lock.acquire("_build", timeout=30):
                    time.sleep(30); continue
                try:
                    result = self.brain.build_feature(task["task"])
                finally:
                    self.file_lock.release("_build")

                if result.get("files_modified"):
                    task["files_modified"] = result["files_modified"]
                    self._log(f"Built: {result['files_modified']}", "build")

                    # Test
                    if self.auto_settings.get("test_after_build", True):
                        time.sleep(2)
                        p, f_count, tres = self.run_self_tests()
                        if f_count > 0:
                            self._log(f"Tests FAILED ({f_count}). Patching...", "error")
                            fails = [t for t in tres if not t.get("passed")]
                            if self.file_lock.acquire("_patch", timeout=30):
                                try:
                                    self.brain.chat(
                                        f"Build '{task['task']}' broke tests:\n{json.dumps(fails,indent=2)}\nFix it.",
                                        mode="heal", include_sources=True)
                                finally:
                                    self.file_lock.release("_patch")

                    task["status"] = "completed"
                    task["completed"] = datetime.now().isoformat()
                    self.status["builds_completed"] = self.status.get("builds_completed", 0) + 1
                    self.status["improvements_made"] += 1
                    w.successes += 1; builds_this_hour += 1

                    self.build_history.append({
                        "task": task["task"], "time": datetime.now().isoformat(),
                        "files": result.get("files_modified", []),
                    })
                    self.build_history = self.build_history[-200:]
                    self._save_json("autopilot_build_history.json", self.build_history)
                else:
                    if task["attempts"] >= 3: task["status"] = "failed"

                self.status["current_task"] = None
                self.status["last_build_time"] = datetime.now().isoformat()
                w.runs += 1; w.last_run = datetime.now().isoformat()
                self._save_json("autopilot_queue.json", self.improvement_queue)

                # Speed cooldown
                cooldowns = {"ludicrous": 10, "aggressive": 30, "normal": 60}
                time.sleep(cooldowns.get(speed, 60))

            except Exception as e:
                w.errors += 1
                self._log(f"WARMODE error: {e}", "error")
                self.status["current_task"] = None
                time.sleep(60)

        w.running = False

    def _get_next_task(self):
        for t in self.improvement_queue:
            if t.get("status") == "pending" and t.get("attempts", 0) < 3:
                return t
        return None

    def _generate_ideas(self):
        self.brain.reload_config()
        if not self.brain.api_key: return
        try:
            done = [t["task"] for t in self.improvement_queue if t.get("status") == "completed"][-10:]
            prompt = (
                "Analyze the BVTech app. Generate exactly 5 high-impact improvements.\n"
                "DONE ALREADY:\n" + ("\n".join(f"- {t}" for t in done) or "(none)") +
                "\n\nFocus: error handling, UI polish, security, caching, useful MSP features.\n"
                "Format: one task per line, starting with verb (Add/Fix/Improve/etc). Under 100 chars.\n"
                "Be SPECIFIC — name files and functions."
            )
            result = self.brain.chat(prompt, mode="general", include_sources=True)
            if result.get("response"):
                existing = {t["task"].lower() for t in self.improvement_queue}
                added = 0
                for line in result["response"].split("\n"):
                    line = line.strip().lstrip("0123456789.-•) ")
                    if (20 < len(line) < 200 and
                        any(line.lower().startswith(v) for v in
                            ["add","fix","improve","handle","update","create","implement",
                             "make","ensure","refactor","optimize","validate","cache",
                             "enhance","secure","extract","replace"])):
                        if line.lower() not in existing:
                            self.add_to_queue(line)
                            added += 1
                        if added >= 5: break
                self._log(f"Generated {added} ideas", "war")
        except Exception as e:
            self._log(f"Idea gen error: {e}", "error")

    # ── Nightly Build ────────────────────────────────────────
    def run_nightly_build(self):
        self._log("🌙 NIGHTLY BUILD...", "war")
        self.brain.reload_config()
        if not self.brain.api_key: return
        self.create_backup("pre_nightly")
        self._generate_ideas()
        for i in range(3):
            task = self._get_next_task()
            if not task: break
            self._log(f"Nightly {i+1}/3: {task['task'][:60]}...", "war")
            if self.file_lock.acquire("_nightly", timeout=30):
                try:
                    result = self.brain.build_feature(task["task"])
                    if result.get("files_modified"):
                        task["status"] = "completed"
                        task["completed"] = datetime.now().isoformat()
                        self.status["improvements_made"] += 1
                finally:
                    self.file_lock.release("_nightly")
            self._save_json("autopilot_queue.json", self.improvement_queue)
            time.sleep(5)
        self.run_self_tests()
        self._log("🌙 Nightly done", "war")

    # ── Subprocess runner ────────────────────────────────────
    def _run_subprocess(self, args, timeout=300):
        python_exe = sys.executable
        if getattr(sys, "frozen", False):
            import shutil as sh
            python_exe = sh.which("python") or sh.which("python3") or "python"
        cmd = [python_exe, os.path.join(self.brain.app_dir, args[0])] + args[1:]
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=timeout, cwd=self.brain.app_dir).stdout
        except: return None

    # ══════════════════════════════════════════════════════════
    # START / STOP
    # ══════════════════════════════════════════════════════════
    def start(self):
        if self.running: return
        self.running = True
        self.warmode = self.auto_settings.get("warmode_enabled", False)
        self.status["running"] = True
        self.status["warmode"] = self.warmode
        self.status["uptime_start"] = datetime.now().isoformat()
        self._log("🚀 AutoPilot v3 LAUNCHING...", "success")

        workers = {
            "health": self._health_worker,
            "error_heal": self._error_heal_worker,
            "compliance": self._compliance_worker,
            "scraper": self._scraper_worker,
            "email": self._email_worker,
            "backup": self._backup_worker,
            "report": self._report_worker,
            "build": self._build_worker,
        }
        for name, func in workers.items():
            t = threading.Thread(target=func, daemon=True, name=f"BV-{name}")
            t.start()
            self._threads[name] = t

        # Nightly scheduler
        def nightly_loop():
            last = None
            while self.running:
                try:
                    now = datetime.now()
                    today = now.date().isoformat()
                    if now.hour == self.auto_settings.get("nightly_build_hour", 2) and last != today:
                        self.run_nightly_build(); last = today
                except: pass
                time.sleep(300)
        t = threading.Thread(target=nightly_loop, daemon=True, name="BV-nightly")
        t.start()
        self._threads["nightly"] = t
        self._log(f"{len(self._threads)} workers running!", "success")

    def stop(self):
        self.running = False; self.warmode = False
        self.status["running"] = False; self.status["warmode"] = False

    def toggle_warmode(self, enabled=True, speed="normal"):
        self.auto_settings["warmode_enabled"] = enabled
        self.auto_settings["warmode_speed"] = speed
        self.save_auto_settings()
        self.warmode = enabled
        self.status["warmode"] = enabled
        self.status["warmode_speed"] = speed
        if enabled and not self.workers["build"].running:
            t = threading.Thread(target=self._build_worker, daemon=True, name="BV-build")
            t.start(); self._threads["build"] = t
            self._log(f"⚔️ WARMODE ENGAGED — {speed.upper()}", "war")
        elif not enabled:
            self._log("WARMODE disengaged", "war")

    # ── Status ───────────────────────────────────────────────
    def get_status(self):
        return {
            **self.status,
            "queue_size": len(self.improvement_queue),
            "queue_pending": sum(1 for t in self.improvement_queue if t.get("status") == "pending"),
            "queue_completed": sum(1 for t in self.improvement_queue if t.get("status") == "completed"),
            "queue_failed": sum(1 for t in self.improvement_queue if t.get("status") == "failed"),
            "workers": {k: v.to_dict() for k, v in self.workers.items()},
            "recent_log": list(self.log_lines)[-30:],
            "auto_settings": self.auto_settings,
            "recent_builds": self.build_history[-5:],
        }

    def get_queue(self):
        return self.improvement_queue
