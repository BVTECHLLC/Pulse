#!/usr/bin/env python3
"""
BVTech AutoClaude — Autonomous AI Brain v1.0
=============================================
Self-healing, self-building AI engine embedded in the BVTech app.

CAPABILITIES:
  - Self-Heal: Catches errors, sends them to Claude, applies fixes, auto-restarts
  - Self-Build: Takes feature requests, writes code, applies to files, restarts
  - Auto-Restart: After any code change, gracefully restarts the Flask server
  - Web Access: Can search the web for solutions, docs, API references
  - Error Journal: Tracks all errors and fixes for learning
  - Live Apply: Writes code directly to files with .bak backups
  - Background Monitor: Watches for crashes and auto-fixes them

USAGE:
  from autoclaude import AutoClaude
  brain = AutoClaude()
  
  # Chat
  response = brain.chat("How do I add Dallas as a market?")
  
  # Self-heal an error
  fix = brain.diagnose_and_fix(error_traceback)
  
  # Build a feature
  result = brain.build_feature("Add a dark mode toggle")
  
  # Apply code to a file
  brain.apply_code("dialpad_integration.py", code_string)
"""

import json
import os
import re
import sys
import time
import shutil
import traceback
import subprocess
import signal
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    pass


class AutoClaude:
    """Autonomous AI brain for the BVTech app."""

    ALLOWED_FILES = [
        "bvtech_app.py", "tacticalrmm_integration.py", "dialpad_integration.py",
        "prospect_scraper.py", "email_campaign.py", "sms_campaign.py",
        "power_dialer.py", "generate_prospects.py", "autoclaude.py", "autopilot.py",
    ]

    def __init__(self, app_dir=None):
        self.app_dir = app_dir or self._detect_app_dir()
        self.config = self._load_config()
        self.api_key = self.config.get("anthropic_key", "")
        self.error_journal = self._load_journal()
        self.conversation_history = []
        self._restart_requested = False

    def _detect_app_dir(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _load_config(self):
        cfg_path = os.path.join(self.app_dir, "bvtech_config.json")
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def reload_config(self):
        """Reload config (e.g. after user saves new API key)."""
        self.config = self._load_config()
        self.api_key = self.config.get("anthropic_key", "")

    # ==========================================================
    # ERROR JOURNAL — Tracks all errors and fixes
    # ==========================================================
    def _journal_path(self):
        return os.path.join(self.app_dir, "autoclaude_journal.json")

    def _load_journal(self):
        try:
            p = self._journal_path()
            if os.path.exists(p):
                with open(p, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"errors": [], "fixes": [], "features_built": [], "restarts": 0}

    def _save_journal(self):
        try:
            with open(self._journal_path(), "w") as f:
                json.dump(self.error_journal, f, indent=2, default=str)
        except Exception:
            pass

    def log_error(self, error_msg, source="unknown"):
        self.error_journal["errors"].append({
            "time": datetime.now().isoformat(),
            "error": error_msg[:2000],
            "source": source,
            "fixed": False,
        })
        self._save_journal()

    def log_fix(self, error_msg, fix_description, file_modified):
        self.error_journal["fixes"].append({
            "time": datetime.now().isoformat(),
            "error": error_msg[:500],
            "fix": fix_description[:1000],
            "file": file_modified,
        })
        # Mark error as fixed
        for e in reversed(self.error_journal["errors"]):
            if not e["fixed"] and error_msg[:100] in e["error"]:
                e["fixed"] = True
                break
        self._save_journal()

    def log_feature(self, description, files_modified):
        self.error_journal["features_built"].append({
            "time": datetime.now().isoformat(),
            "description": description[:500],
            "files": files_modified,
        })
        self._save_journal()

    # ==========================================================
    # FILE OPERATIONS — Read, Write, Backup
    # ==========================================================
    def read_file(self, filename):
        """Read a source file."""
        if filename not in self.ALLOWED_FILES and not filename.endswith(('.json', '.csv', '.log')):
            return None, f"Not allowed: {filename}"
        filepath = os.path.join(self.app_dir, filename)
        if not os.path.exists(filepath):
            return None, f"Not found: {filename}"
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read(), None
        except Exception as e:
            return None, str(e)

    def apply_code(self, filename, code, backup=True):
        """Write code to a file. Creates .bak backup first."""
        if filename not in self.ALLOWED_FILES:
            return False, f"Not allowed to modify: {filename}"

        filepath = os.path.join(self.app_dir, filename)

        try:
            # Create backup
            if backup and os.path.exists(filepath):
                bak = filepath + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(filepath, bak)

            # Write new code
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)

            # Verify it's valid Python (syntax check)
            if filename.endswith('.py'):
                try:
                    compile(code, filename, 'exec')
                except SyntaxError as e:
                    # Revert! Bad code
                    if backup and os.path.exists(filepath + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
                        # Find most recent backup
                        baks = sorted(Path(self.app_dir).glob(f"{filename}.bak.*"), reverse=True)
                        if baks:
                            shutil.copy2(str(baks[0]), filepath)
                    return False, f"Syntax error in generated code: {e}. Reverted to backup."

            return True, f"Successfully wrote {filename}"
        except Exception as e:
            return False, str(e)

    def read_all_sources(self, truncate=True):
        """Read all source files for AI context."""
        sources = {}
        for fname in self.ALLOWED_FILES:
            content, err = self.read_file(fname)
            if content:
                if truncate and len(content) > 12000:
                    sources[fname] = content[:6000] + "\n\n# ... [TRUNCATED] ...\n\n" + content[-4000:]
                else:
                    sources[fname] = content
        return sources

    # ==========================================================
    # CLAUDE API — Talk to the brain
    # ==========================================================
    def _call_claude(self, messages, system_prompt, max_tokens=8192):
        """Call the Anthropic API."""
        if not self.api_key:
            self.reload_config()
        if not self.api_key:
            return None, "No Anthropic API key. Set it in Settings → Claude AI."

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": messages,
                },
                timeout=120,
            )

            if resp.status_code == 200:
                result = resp.json()
                text = ""
                for block in result.get("content", []):
                    if block.get("type") == "text":
                        text += block["text"]
                return text, None
            else:
                return None, f"API {resp.status_code}: {resp.text[:300]}"
        except Exception as e:
            return None, str(e)

    def _build_system_prompt(self, mode="general"):
        """Build context-rich system prompt."""
        safe_cfg = {k: ("***" if any(s in k for s in ["key", "secret", "token"]) and v else v)
                    for k, v in self.config.items()}

        base = f"""You are AutoClaude — an autonomous AI brain embedded in the BVTech MSP Marketing Command Center.
You are NOT a chatbot. You are a LIVE SYSTEM that can READ, WRITE, and EXECUTE code on this machine.

Owner: Jordan Polasek, Managing Partner at BVTech LLC (MSP in El Campo, TX)
Services: Managed IT, Cybersecurity, Cloud/M365, VoIP (DialPad)
Markets: Austin, San Antonio, Houston — law firms, medical, dental, CPA, financial

App dir: {self.app_dir}
Config (redacted): {json.dumps(safe_cfg, indent=2)}

CRITICAL RULES FOR CODE OUTPUT:
When you need to fix or create code, you MUST output it in this EXACT format:

===AUTOCLAUDE_FILE_WRITE===
FILENAME: exact_filename.py
MODE: overwrite
CODE_START
(your complete file content here)
CODE_END

You can output multiple file writes in one response. Each one will be automatically applied.
The system will:
1. Create a .bak backup of the original
2. Write your new code
3. Syntax-check it (reverts if bad)
4. Auto-restart the app to load changes

NEVER just show code in markdown blocks. ALWAYS use the ===AUTOCLAUDE_FILE_WRITE=== format.
The difference: markdown blocks are DISPLAY ONLY. AUTOCLAUDE_FILE_WRITE blocks are EXECUTED.
"""

        if mode == "heal":
            base += """
MODE: SELF-HEAL
An error has occurred. Diagnose the root cause and fix it.
Read the traceback carefully. Output the fixed file using ===AUTOCLAUDE_FILE_WRITE=== format.
Fix the ACTUAL bug — don't just add try/except around it. Fix the root cause.
"""
        elif mode == "build":
            base += """
MODE: SELF-BUILD
The user wants a new feature. Write production-ready code.
Output complete files using ===AUTOCLAUDE_FILE_WRITE=== format.
Make sure new code integrates cleanly with the existing codebase.
"""
        elif mode == "general":
            base += """
MODE: GENERAL
Help with whatever the user asks. If they want code changes, use ===AUTOCLAUDE_FILE_WRITE=== format.
If they just want information, answer normally.
"""

        # Add recent error journal context
        recent_errors = self.error_journal.get("errors", [])[-5:]
        if recent_errors:
            base += f"\nRecent errors (last 5): {json.dumps(recent_errors, indent=2, default=str)}"

        recent_fixes = self.error_journal.get("fixes", [])[-5:]
        if recent_fixes:
            base += f"\nRecent fixes applied: {json.dumps(recent_fixes, indent=2, default=str)}"

        return base

    def _parse_file_writes(self, response_text):
        """Parse ===AUTOCLAUDE_FILE_WRITE=== blocks from Claude's response."""
        writes = []
        pattern = r'===AUTOCLAUDE_FILE_WRITE===\s*\nFILENAME:\s*(\S+)\s*\nMODE:\s*(\w+)\s*\nCODE_START\n([\s\S]*?)\nCODE_END'
        matches = re.finditer(pattern, response_text)

        for m in matches:
            filename = m.group(1).strip()
            mode = m.group(2).strip()
            code = m.group(3)
            writes.append({"filename": filename, "mode": mode, "code": code})

        return writes

    def _strip_file_writes(self, response_text):
        """Remove the file write blocks from response text for display."""
        pattern = r'===AUTOCLAUDE_FILE_WRITE===\s*\nFILENAME:\s*\S+\s*\nMODE:\s*\w+\s*\nCODE_START\n[\s\S]*?\nCODE_END'
        return re.sub(pattern, '', response_text).strip()

    # ==========================================================
    # CORE ACTIONS
    # ==========================================================
    def chat(self, message, mode="general", include_sources=False):
        """Send a message to Claude and process any file writes."""
        system = self._build_system_prompt(mode)

        if include_sources or mode in ("heal", "build"):
            sources = self.read_all_sources()
            source_text = "\n\n".join([f"=== {n} ===\n{c}" for n, c in sources.items()])
            system += f"\n\nCurrent source files:\n{source_text}"

        # Build messages
        msgs = []
        for m in self.conversation_history[-12:]:
            msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": message})

        # Call Claude
        response, err = self._call_claude(msgs, system)
        if err:
            return {"response": f"Error: {err}", "files_modified": [], "error": err}

        # Parse file writes
        file_writes = self._parse_file_writes(response)
        display_text = self._strip_file_writes(response) if file_writes else response

        # Apply file writes
        files_modified = []
        apply_results = []
        for fw in file_writes:
            ok, msg = self.apply_code(fw["filename"], fw["code"])
            apply_results.append({"file": fw["filename"], "success": ok, "message": msg})
            if ok:
                files_modified.append(fw["filename"])

        # Update conversation
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": response})

        # Log feature if in build mode
        if mode == "build" and files_modified:
            self.log_feature(message, files_modified)

        result = {
            "response": display_text,
            "files_modified": files_modified,
            "apply_results": apply_results,
            "needs_restart": len(files_modified) > 0,
        }

        return result

    def diagnose_and_fix(self, error_text, auto_apply=True):
        """Auto-diagnose an error and fix it."""
        self.log_error(error_text, "auto_heal")

        result = self.chat(
            f"This error just occurred in the running app. Diagnose and fix it:\n\n{error_text}",
            mode="heal",
            include_sources=True,
        )

        if result.get("files_modified"):
            for f in result["files_modified"]:
                self.log_fix(error_text, result.get("response", "")[:500], f)

        return result

    def build_feature(self, description):
        """Build a new feature from a description."""
        return self.chat(
            f"Build this feature for the BVTech app:\n\n{description}",
            mode="build",
            include_sources=True,
        )

    def web_search(self, query):
        """Search the web for information."""
        try:
            # Use a simple search API or DuckDuckGo
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "BVTech-AutoClaude/1.0"},
                timeout=10,
            )
            if resp.status_code == 200:
                # Extract text snippets
                text = resp.text[:5000]
                return text, None
            return None, f"Search failed: {resp.status_code}"
        except Exception as e:
            return None, str(e)

    # ==========================================================
    # AUTO-RESTART
    # ==========================================================
    def request_restart(self):
        """Signal that the app should restart."""
        self._restart_requested = True

    def should_restart(self):
        return self._restart_requested

    def do_restart(self):
        """Restart the Flask app by re-executing the process."""
        self.error_journal["restarts"] = self.error_journal.get("restarts", 0) + 1
        self._save_journal()

        python = sys.executable
        if getattr(sys, 'frozen', False):
            # Running as EXE
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            # Running as script
            os.execv(python, [python] + sys.argv)

    def get_status(self):
        """Get AI brain status."""
        return {
            "has_api_key": bool(self.api_key),
            "app_dir": self.app_dir,
            "total_errors": len(self.error_journal.get("errors", [])),
            "total_fixes": len(self.error_journal.get("fixes", [])),
            "features_built": len(self.error_journal.get("features_built", [])),
            "restarts": self.error_journal.get("restarts", 0),
            "unfixed_errors": sum(1 for e in self.error_journal.get("errors", []) if not e.get("fixed")),
            "conversation_length": len(self.conversation_history),
            "source_files": [f for f in os.listdir(self.app_dir) if f.endswith('.py')],
        }


# ==========================================================
# ERROR CATCHING MIDDLEWARE
# ==========================================================
class ErrorCatcher:
    """Flask middleware that catches errors and sends them to AutoClaude for healing."""

    def __init__(self, brain):
        self.brain = brain
        self.recent_errors = {}  # Dedup — don't fix the same error twice in 5 min

    def should_auto_fix(self, error_key):
        """Check if we should auto-fix this error (dedup)."""
        now = time.time()
        if error_key in self.recent_errors:
            if now - self.recent_errors[error_key] < 300:  # 5 min cooldown
                return False
        self.recent_errors[error_key] = now
        return True

    def handle_error(self, error_text, source="flask"):
        """Handle an error — log it and optionally auto-fix."""
        error_key = error_text[:200]
        self.brain.log_error(error_text, source)

        if self.brain.api_key and self.should_auto_fix(error_key):
            # Auto-heal in background
            result = self.brain.diagnose_and_fix(error_text, auto_apply=True)
            return result
        return None
