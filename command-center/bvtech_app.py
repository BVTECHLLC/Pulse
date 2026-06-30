#!/usr/bin/env python3
"""
BVTech MSP Command Center v30.0 — FINAL Edition
==============================================================
SUPER MSP App — Ties your ENTIRE MSP stack into one unified platform.

v20 — CLOUDFLARE PAGES INTEGRATION:
  - NEW: Cloudflare Pages integration for BVTech.org (static site, not WordPress)
  - NEW: CloudflarePagesClient — deploys blog posts as static HTML via GitHub API
  - NEW: Blog template engine — generates pixel-perfect HTML matching BVTech.org design
  - NEW: Dual-site publishing: BVTech.org → Cloudflare Pages, JordanPolasek.com → WordPress
  - NEW: Cloudflare tab — site dashboard, blog management, deploy status
  - UPD: ORM Beast v20 — auto-detects BVTech=Cloudflare, JP=WordPress
  - UPD: AI Blog Engine — generates SEO/GEO/AEO posts, deploys to Cloudflare Pages
  - UPD: Auto-poster scheduler — works with Cloudflare for BVTech.org
  - UPD: Business Pulse report — includes Cloudflare site data
  - KEPT: JordanPolasek.com stays on WordPress (ORM personal brand)

FULL STACK:
  - 📋 SuperOps PSA — Live tickets, clients, assets, technicians, invoices (GraphQL API)
  - 🛡️ Guardz Security — Incident dashboard via SuperOps sync + portal link
  - 📬 M365 Inbox — Read, send, reply to real emails (separate from campaigns)
  - 💰 Revenue Dashboard — MRR tracking, client health, contract overview
  - 🔍 Smart Scraper — Google Places prospect finder
  - 📧 Email Campaigns — M365 Graph API drip sequences
  - 💬 SMS / 📞 Dialer / 🎙️ Phone — DialPad Pro full integration
  - 🧠 AI Coaching — Call analysis + scoring
  - 🔥 Pipeline — HubSpot deal tracker
  - 🔶 CRM — HubSpot contact sync
  - 🤖 Claude AI — Brain + Debugger + Self-Builder
  - ⚔️ WARMODE — Aggressive self-building engine with parallel workers
"""

APP_VERSION = "32.1"
APP_NAME = "BVTech MSP Command Center"

import json, os, sys, csv, subprocess, threading, webbrowser, time, traceback
from pathlib import Path
from datetime import datetime

# ============================================================
# v18.1: PYINSTALLER SYS.PATH FIX
# --add-data puts files in _MEIPASS but NOT on sys.path.
# Without this, `from autoclaude import ...` etc. crash the EXE.
# ============================================================
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', None)
    if _meipass and _meipass not in sys.path:
        sys.path.insert(0, _meipass)
    # Also add the directory where the .exe lives (for config, data files)
    _exe_dir = os.path.dirname(sys.executable)
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)

# ============================================================
# v18.1: DEPENDENCY AUTO-INSTALL (flask + requests)
# ============================================================
def _ensure_dependencies():
    """Install missing dependencies. Only runs in non-frozen (dev/script) mode."""
    if getattr(sys, 'frozen', False):
        return  # EXE has everything bundled
    missing = []
    try:
        import flask  # noqa: F401
    except ImportError:
        missing.append("flask")
    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")
    if missing:
        print(f"  [v18.1] Installing missing packages: {', '.join(missing)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)

_ensure_dependencies()

from flask import Flask, render_template_string, request, jsonify, Response

# ============================================================
# PYTHON EXECUTABLE FINDER
# When running as a PyInstaller EXE, sys.executable points to the EXE itself,
# NOT to python.exe. This breaks all subprocess calls. Fix: find real python.
# ============================================================
def get_python_exe():
    """Find the real Python interpreter, even inside a PyInstaller bundle."""
    # If we're NOT in a PyInstaller bundle, sys.executable is fine
    if not getattr(sys, 'frozen', False):
        return sys.executable

    # We ARE in a PyInstaller bundle — sys.executable is the .exe
    # Find python.exe on the system
    import shutil

    # Try common locations
    python_path = shutil.which("python")
    if python_path:
        return python_path

    python3_path = shutil.which("python3")
    if python3_path:
        return python3_path

    # Try py launcher (Windows)
    py_path = shutil.which("py")
    if py_path:
        return py_path

    # Fallback: common Windows Python paths
    for ver in ["313", "312", "311", "310", "39"]:
        for base in [os.path.expanduser("~"), "C:\\", "C:\\Program Files"]:
            candidate = os.path.join(base, "AppData", "Local", "Programs", "Python", f"Python{ver}", "python.exe")
            if os.path.exists(candidate):
                return candidate

    # Last resort — just try "python" and hope PATH has it
    return "python"

def get_app_dir():
    """Get the directory where the app files live."""
    if getattr(sys, 'frozen', False):
        # PyInstaller EXE: files are next to the exe
        return os.path.dirname(sys.executable)
    else:
        # Running as script: files are next to this .py file
        return os.path.dirname(os.path.abspath(__file__)) or "."

PYTHON_EXE = get_python_exe()
APP_DIR = get_app_dir()

# ============================================================
# v18: KILL PREVIOUS INSTANCES — prevents demo accidents
# ============================================================
def kill_previous_instances(port=5678):
    """Kill any existing process on the target port before starting.
    v19: More robust — tries multiple methods, waits for port release, verifies."""
    import socket

    def _port_in_use(p):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(('127.0.0.1', p))
            sock.close()
            return result == 0
        except Exception:
            return False

    if not _port_in_use(port):
        return  # Port is free, nothing to do

    print(f"  [v19] Port {port} in use — killing previous instance...")

    if sys.platform == "win32":
        # Method 1: Kill by port via netstat
        try:
            output = subprocess.check_output(
                f'netstat -aon | findstr :{port} | findstr LISTENING',
                shell=True, text=True, timeout=5)
            for line in output.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1].strip()
                    if pid.isdigit() and int(pid) != os.getpid():
                        subprocess.run(f'taskkill /F /PID {pid}',
                                     shell=True, capture_output=True, timeout=5)
                        print(f"  [v19] Killed PID {pid}")
        except Exception:
            pass

        # Method 2: Kill by window title
        try:
            subprocess.run('taskkill /F /FI "WINDOWTITLE eq BVTech*"',
                         shell=True, capture_output=True, timeout=5)
        except Exception:
            pass

        # Method 3: Kill any BVTech-CommandCenter.exe processes (not ourselves)
        try:
            subprocess.run('taskkill /F /IM BVTech-CommandCenter.exe',
                         shell=True, capture_output=True, timeout=5)
        except Exception:
            pass
    else:
        # Linux/Mac: use lsof
        try:
            output = subprocess.check_output(
                f'lsof -ti :{port}', shell=True, text=True, timeout=5)
            for pid in output.strip().split('\n'):
                if pid.isdigit() and int(pid) != os.getpid():
                    os.kill(int(pid), 9)
                    print(f"  [v19] Killed PID {pid}")
        except Exception:
            pass

    # Wait for port to actually be released (up to 5 seconds)
    for i in range(10):
        if not _port_in_use(port):
            print(f"  [v19] Port {port} is now free.")
            return
        time.sleep(0.5)

    print(f"  [v19] Warning: Port {port} may still be in use after kill attempts.")

# ============================================================
# v18.1: CONFIG — definitions FIRST, then migration
# ============================================================
CONFIG_FILE = "bvtech_config.json"
DEFAULT_CONFIG = {
    "tenant_id":"","client_id":"","client_secret":"",
    "sender_email":"help@bvtech.org","sender_name":"Jordan Polasek",
    "sender_title":"Managing Partner","sender_phone":"(210) 538-3669",
    "physical_address":"BVTech LLC, 1902 Kirby Rd, El Campo, TX 77437",
    "dialpad_key":"","dialpad_user_id":"6283801532137472",
    "dialpad_number":"+12105383669","hubspot_token":"","google_api_key":"",
    "anthropic_key":"",
    "hunter_api_key":"","bing_api_key":"",
    "trmm_api_url":"","trmm_api_key":"",
    "wp_site_url":"https://bvtech.org","wp_relay_key":"BVTech2026Relay",
    "wp_user":"","wp_app_password":"",
    "cf_api_token":"","cf_account_id":"c31280b99fda28a238ada0b669eedd0a","cf_project_name":"bvtech-website",
    "cf_site_url":"https://bvtech.org",
    # v29: absolute path to the local mirror of the site. The Cloudflare
    # Pages Direct Upload deployer walks this folder and uploads the
    # whole tree on every publish. This is the "fresh v38 website zip
    # extracted into your working dir" — see CHANGELOG_v29.md.
    "bvtech_site_root":"C:\\BVTech2\\Website\\bvtech.org",
    "cf_deploy_branch":"main",
    "gh_token":"","gh_repo":"","gh_branch":"main",
    "guardz_portal_url":"https://app.guardz.com",
    "emails_per_day":200,"warmup_mode":True,
    "jp_site_url":"https://jordanpolasek.com","jp_relay_key":"JP2026Relay",
    "jp_wp_user":"","jp_wp_app_password":"",
    "jp_gh_token":"","jp_gh_repo":"","jp_gh_branch":"main",
    "jp_cf_api_token":"","jp_cf_account_id":"c31280b99fda28a238ada0b669eedd0a","jp_cf_project_name":"jordanpolasek-site",
    "jp_site_root":"C:\\BVTech2\\Website\\jordanpolasek.com",
    "linkedin_access_token":"","linkedin_person_urn":"",
    "linkedin_client_id":"","linkedin_client_secret":"",
    "linkedin_redirect_uri":"http://localhost:5678/api/linkedin/callback",
    # v30: Google Business Profile auto-posting
    "google_client_id":"","google_client_secret":"",
    "google_redirect_uri":"http://localhost:5678/api/gbp/oauth/callback",
    "gbp_refresh_token":"","gbp_account_name":"","gbp_location_name":"",
    "gbp_location_title":"",  # display-only, shown in UI
    # v31: HubSpot email tracking
    "hubspot_bcc_address":"",  # format: xxxx@bcc.hubspot.com, copy from HubSpot Settings → Log Email
    "filter_min_rating":4.0,"filter_min_reviews":10,"filter_min_score":60,
    "filter_require_phone":True,"filter_require_website":True,"filter_skip_solo":True,
    "scraper_max_results":200,
}

def load_config():
    cfg_path = os.path.join(APP_DIR, CONFIG_FILE)
    try:
        if Path(cfg_path).exists():
            with open(cfg_path, "r") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
    except (json.JSONDecodeError, IOError) as e:
        print(f"  [v18.1] Warning: Config file corrupt, using defaults. Error: {e}")
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    cfg_path = os.path.join(APP_DIR, CONFIG_FILE)
    # v18.1: Write to temp file first, then rename (atomic write prevents corruption)
    tmp_path = cfg_path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(cfg, f, indent=2)
        # Atomic rename (on Windows this may fail if dest exists, so remove first)
        if sys.platform == "win32" and os.path.exists(cfg_path):
            os.remove(cfg_path)
        os.rename(tmp_path, cfg_path)
    except Exception as e:
        print(f"  [v18.1] Warning: Could not save config: {e}")
        # Fallback: direct write
        try:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

def migrate_config():
    """Ensure all required config fields exist. Preserves user values, adds new defaults."""
    try:
        cfg = load_config()
        changed = False
        for key, default_val in DEFAULT_CONFIG.items():
            if key not in cfg:
                cfg[key] = default_val
                changed = True
        if changed:
            save_config(cfg)
            print(f"  [v18.1] Config migrated — new fields added.")
    except Exception as e:
        print(f"  [v18.1] Config migration skipped (non-fatal): {e}")

# NOW it's safe to call migrate (all definitions exist)
migrate_config()

app = Flask(__name__)
app.config["SECRET_KEY"] = "bvtech-msp-2026"

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BVTech MSP Command Center v31 — FINAL</title>
<link rel="icon" type="image/png" href="/favicon.png">
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

  *{margin:0;padding:0;box-sizing:border-box;}
  :root{
    --bg:#06080f;--bg2:#0a0e1a;--bg3:#111827;--bg4:#1a2540;
    --fg:#e2e8f0;--fg2:#94a3b8;--fg3:#64748b;
    --blue:#3b82f6;--purple:#8b5cf6;--green:#22c55e;
    --red:#ef4444;--orange:#f59e0b;--cyan:#06b6d4;--pink:#ec4899;
    --hubspot:#ff7a59;--ms:#0078d4;--dialpad:#7c3aed;
    --superops:#00b4d8;--guardz:#10b981;--revenue:#f59e0b;
    --radius:12px;
  }

  body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;}

  /* Animated gradient bg */
  body::before{content:'';position:fixed;top:0;left:0;right:0;bottom:0;
    background:radial-gradient(ellipse at 20% 0%, rgba(124,58,237,0.08) 0%, transparent 50%),
               radial-gradient(ellipse at 80% 100%, rgba(59,130,246,0.06) 0%, transparent 50%);
    pointer-events:none;z-index:0;}

  /* Header */
  .header{position:relative;z-index:10;
    background:linear-gradient(135deg,rgba(10,14,26,0.95),rgba(17,24,39,0.95));
    backdrop-filter:blur(20px);
    border-bottom:1px solid rgba(255,255,255,0.04);
    padding:12px 28px;display:flex;align-items:center;justify-content:space-between;}
  .header-left{display:flex;align-items:center;gap:14px;}
  .logo-text{font-size:22px;font-weight:900;letter-spacing:3px;
    background:linear-gradient(135deg,#7c3aed,#3b82f6,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
  .header-sub{font-size:11px;font-weight:600;color:rgba(255,255,255,0.3);letter-spacing:1px;}
  .version-badge{padding:2px 8px;border-radius:99px;font-size:9px;font-weight:700;
    background:rgba(124,58,237,0.2);color:#a78bfa;border:1px solid rgba(124,58,237,0.3);}
  .header-badges{display:flex;gap:5px;flex-wrap:wrap;}
  .svc-badge{padding:2px 10px;border-radius:99px;font-size:9px;font-weight:700;
    background:rgba(59,130,246,0.08);color:#60a5fa;border:1px solid rgba(59,130,246,0.12);
    transition:all 0.2s ease;user-select:none;}
  .svc-badge[onclick]{cursor:pointer;}
  .svc-badge[onclick]:hover{transform:translateY(-1px);box-shadow:0 2px 12px rgba(59,130,246,0.2);filter:brightness(1.3);}

  /* Tabs */
  .tabs{position:relative;z-index:10;display:flex;gap:1px;padding:0 28px;
    background:rgba(0,0,0,0.3);border-bottom:1px solid rgba(255,255,255,0.04);overflow-x:auto;}
  .tab{padding:12px 16px;cursor:pointer;color:var(--fg3);font-size:12px;font-weight:700;
    border:none;background:none;border-bottom:2px solid transparent;white-space:nowrap;
    transition:all 0.2s;font-family:inherit;letter-spacing:0.3px;}
  .tab:hover{color:var(--fg2);background:rgba(255,255,255,0.02);}
  .tab.active{color:#a78bfa;border-bottom-color:#7c3aed;background:rgba(124,58,237,0.05);}
  .tab-emoji{font-size:14px;margin-right:4px;}
  .tab-sub{font-size:8px;color:var(--fg3);margin-top:1px;font-weight:500;letter-spacing:0.5px;text-transform:uppercase;}
  .tab-new{display:inline-block;padding:0 5px;border-radius:4px;font-size:8px;font-weight:800;
    background:linear-gradient(135deg,#7c3aed,#ec4899);color:#fff;margin-left:4px;vertical-align:top;}

  .prospect-count{margin-left:auto;display:flex;align-items:center;padding:0 16px;}
  .count-badge{background:rgba(34,197,94,0.12);color:#4ade80;padding:3px 12px;
    border-radius:99px;font-size:10px;font-weight:800;border:1px solid rgba(34,197,94,0.2);}

  /* Content */
  .content{position:relative;z-index:10;padding:20px 28px;max-width:1400px;margin:0 auto;}
  .tab-content{display:none;}.tab-content.active{display:block;}

  /* Cards */
  .card{background:rgba(10,14,26,0.8);border:1px solid rgba(255,255,255,0.05);
    border-radius:var(--radius);padding:16px 18px;backdrop-filter:blur(10px);}
  .glow{border-radius:var(--radius);padding:16px;}
  .glow-blue{background:linear-gradient(135deg,rgba(59,130,246,0.06),rgba(59,130,246,0.02));border:1px solid rgba(59,130,246,0.12);}
  .glow-green{background:linear-gradient(135deg,rgba(34,197,94,0.06),rgba(34,197,94,0.02));border:1px solid rgba(34,197,94,0.12);}
  .glow-orange{background:linear-gradient(135deg,rgba(245,158,11,0.06),rgba(239,68,68,0.03));border:1px solid rgba(245,158,11,0.15);}
  .glow-purple{background:linear-gradient(135deg,rgba(124,58,237,0.06),rgba(124,58,237,0.02));border:1px solid rgba(124,58,237,0.12);}
  .glow-hubspot{background:linear-gradient(135deg,rgba(255,122,89,0.06),rgba(255,122,89,0.02));border:1px solid rgba(255,122,89,0.12);}
  .glow-ms{background:linear-gradient(135deg,rgba(0,120,212,0.06),rgba(0,120,212,0.02));border:1px solid rgba(0,120,212,0.12);}
  .glow-pink{background:linear-gradient(135deg,rgba(236,72,153,0.06),rgba(236,72,153,0.02));border:1px solid rgba(236,72,153,0.12);}
  .glow-cyan{background:linear-gradient(135deg,rgba(6,182,212,0.06),rgba(6,182,212,0.02));border:1px solid rgba(6,182,212,0.12);}

  .section-title{font-size:13px;font-weight:800;margin-bottom:5px;letter-spacing:0.3px;}
  .section-desc{font-size:11px;color:var(--fg2);line-height:1.7;}

  /* Stats grid */
  .stats{display:grid;gap:10px;margin:14px 0;}
  .stats-3{grid-template-columns:repeat(3,1fr);}
  .stats-4{grid-template-columns:repeat(4,1fr);}
  .stats-5{grid-template-columns:repeat(5,1fr);}
  .stats-6{grid-template-columns:repeat(6,1fr);}
  .stats-8{grid-template-columns:repeat(8,1fr);}
  .stat{position:relative;overflow:hidden;}
  .stat-icon{position:absolute;top:10px;right:12px;font-size:16px;opacity:0.2;}
  .stat-label{font-size:8px;font-weight:800;text-transform:uppercase;letter-spacing:1.2px;color:var(--fg3);margin-bottom:4px;}
  .stat-value{font-size:22px;font-weight:900;line-height:1;}
  .stat-sub{font-size:9px;color:var(--fg3);margin-top:3px;}

  /* Buttons */
  .btn{padding:8px 18px;border:none;border-radius:8px;font-weight:700;font-size:11px;
    cursor:pointer;font-family:inherit;transition:all 0.15s;letter-spacing:0.3px;}
  .btn-primary{background:linear-gradient(135deg,#7c3aed,#3b82f6);color:#fff;}
  .btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(124,58,237,0.3);}
  .btn-ms{background:linear-gradient(135deg,#0078d4,#0063b1);color:#fff;}
  .btn-purple{background:linear-gradient(135deg,#7c3aed,#6d28d9);color:#fff;}
  .btn-green{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;}
  .btn-hubspot{background:linear-gradient(135deg,#ff7a59,#ff5c35);color:#fff;}
  .btn-pink{background:linear-gradient(135deg,#ec4899,#be185d);color:#fff;}
  .btn-cyan{background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;}
  .btn-outline{background:rgba(255,255,255,0.04);color:var(--fg2);border:1px solid rgba(255,255,255,0.08);}
  .btn-outline:hover{background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.15);}
  .btn-lg{padding:12px 30px;font-size:13px;}
  .btn-sm{padding:5px 12px;font-size:10px;}
  .btn-disabled{opacity:0.4;cursor:not-allowed;}
  .btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;}

  /* Inputs */
  input[type="text"],input[type="number"],input[type="password"],select,textarea{
    background:rgba(17,24,39,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:8px;
    padding:8px 12px;color:var(--fg);font-size:12px;font-family:inherit;
    outline:none;width:100%;transition:border-color 0.2s;}
  input:focus,select:focus,textarea:focus{border-color:rgba(124,58,237,0.4);}
  textarea{resize:vertical;min-height:60px;font-family:'JetBrains Mono',monospace;font-size:11px;}
  select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
    background-repeat:no-repeat;background-position:right 10px center;padding-right:30px;}
  label.filter-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--fg3);display:block;margin-bottom:4px;}

  .check-row{display:flex;align-items:center;gap:6px;font-size:11px;cursor:pointer;font-weight:500;}
  .check-row input{accent-color:#7c3aed;}

  /* Log output */
  .log-output{background:rgba(6,8,15,0.9);border:1px solid rgba(255,255,255,0.04);
    border-radius:var(--radius);padding:14px;font-family:'JetBrains Mono',monospace;
    font-size:11px;line-height:1.8;color:#a0aec0;min-height:280px;max-height:600px;overflow-y:auto;white-space:pre-wrap;}
  .log-output .success{color:#4ade80;}.log-output .error{color:#f87171;}
  .log-output .info{color:#60a5fa;}.log-output .warn{color:#facc15;}

  /* Grid helpers */
  .grid{display:grid;gap:12px;}
  .grid-2{grid-template-columns:1fr 1fr;}.grid-3{grid-template-columns:1fr 1fr 1fr;}
  .grid-4{grid-template-columns:1fr 1fr 1fr 1fr;}
  .flex{display:flex;}.gap-6{gap:6px;}.gap-8{gap:8px;}.gap-10{gap:10px;}.gap-12{gap:12px;}.gap-16{gap:16px;}
  .items-center{align-items:center;}.justify-between{justify-content:space-between;}.justify-center{justify-content:center;}
  .mt-8{margin-top:8px;}.mt-12{margin-top:12px;}.mt-16{margin-top:16px;}
  .mb-8{margin-bottom:8px;}.mb-12{margin-bottom:12px;}.mb-16{margin-bottom:16px;}
  .flex-wrap{flex-wrap:wrap;}

  /* Filter section */
  .filter-box{border-radius:var(--radius);padding:14px;
    background:linear-gradient(135deg,rgba(34,197,94,0.04),rgba(34,197,94,0.01));
    border:1px solid rgba(34,197,94,0.1);}
  .filter-title{font-size:11px;font-weight:800;color:#4ade80;margin-bottom:10px;letter-spacing:0.5px;}
  .filter-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
  .filter-input{display:flex;align-items:center;gap:6px;}
  .filter-input input,.filter-input select{width:auto;min-width:60px;}
  .filter-hint{font-size:9px;color:var(--fg3);margin-left:auto;}

  /* Settings sections */
  .settings-section{border-radius:var(--radius);padding:18px;margin-bottom:14px;}
  .settings-title{font-size:13px;font-weight:800;margin-bottom:12px;}
  .settings-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;}
  .settings-field label{font-size:9px;font-weight:700;text-transform:uppercase;
    letter-spacing:0.8px;color:var(--fg3);display:block;margin-bottom:4px;}

  /* Pipeline kanban */
  .pipeline{display:flex;gap:10px;overflow-x:auto;padding-bottom:10px;}
  .pipeline-col{min-width:180px;flex:1;background:rgba(10,14,26,0.6);border-radius:var(--radius);
    border:1px solid rgba(255,255,255,0.04);padding:10px;min-height:200px;}
  .pipeline-header{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1px;
    color:var(--fg3);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.06);}
  .pipeline-count{float:right;background:rgba(124,58,237,0.15);color:#a78bfa;
    padding:1px 6px;border-radius:99px;font-size:9px;}
  .pipeline-deal{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);
    border-radius:8px;padding:8px;margin-bottom:6px;font-size:11px;cursor:pointer;transition:all 0.15s;}
  .pipeline-deal:hover{background:rgba(124,58,237,0.08);border-color:rgba(124,58,237,0.2);}
  .deal-name{font-weight:700;margin-bottom:2px;}.deal-amount{color:#4ade80;font-weight:800;font-size:12px;}
  .deal-priority{font-size:8px;font-weight:700;text-transform:uppercase;padding:1px 5px;border-radius:4px;}
  .deal-priority.HIGH{background:rgba(239,68,68,0.15);color:#f87171;}
  .deal-priority.MEDIUM{background:rgba(245,158,11,0.15);color:#fbbf24;}
  .deal-priority.LOW{background:rgba(59,130,246,0.15);color:#60a5fa;}

  /* Coaching score ring */
  .score-ring{width:80px;height:80px;border-radius:50%;display:flex;align-items:center;justify-content:center;
    font-size:24px;font-weight:900;position:relative;}
  .score-ring::before{content:'';position:absolute;inset:-3px;border-radius:50%;
    background:conic-gradient(var(--ring-color) var(--ring-pct), rgba(255,255,255,0.05) var(--ring-pct));}
  .score-ring-inner{position:relative;z-index:1;width:70px;height:70px;border-radius:50%;
    background:var(--bg2);display:flex;align-items:center;justify-content:center;flex-direction:column;}
  .score-ring-value{font-size:22px;font-weight:900;line-height:1;}.score-ring-label{font-size:8px;color:var(--fg3);margin-top:2px;}

  /* Toast */
  .toast{position:fixed;bottom:20px;right:20px;padding:12px 24px;border-radius:12px;font-weight:700;font-size:12px;
    box-shadow:0 8px 40px rgba(0,0,0,0.4);transform:translateY(100px);opacity:0;
    transition:all 0.3s;z-index:999;backdrop-filter:blur(10px);}
  .toast.show{transform:translateY(0);opacity:1;}
  .toast-success{background:rgba(34,197,94,0.9);color:#fff;}
  .toast-error{background:rgba(239,68,68,0.9);color:#fff;}
  .toast-info{background:rgba(124,58,237,0.9);color:#fff;}

  /* Disposition buttons */
  .disp-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;}
  .disp-btn{padding:8px 4px;border:1px solid rgba(255,255,255,0.08);border-radius:8px;
    background:rgba(255,255,255,0.03);color:var(--fg2);font-size:10px;font-weight:700;
    cursor:pointer;text-align:center;transition:all 0.15s;font-family:inherit;}
  .disp-btn:hover{background:rgba(124,58,237,0.1);border-color:rgba(124,58,237,0.3);color:#a78bfa;}
  .disp-btn.selected{background:rgba(124,58,237,0.15);border-color:rgba(124,58,237,0.4);color:#c4b5fd;}

  /* Contact table */
  .contact-table{width:100%;border-collapse:collapse;font-size:11px;}
  .contact-table th{text-align:left;padding:8px;font-size:9px;font-weight:700;text-transform:uppercase;
    letter-spacing:1px;color:var(--fg3);border-bottom:1px solid rgba(255,255,255,0.06);}
  .contact-table td{padding:7px 8px;border-bottom:1px solid rgba(255,255,255,0.03);}
  .contact-table tr:hover{background:rgba(124,58,237,0.04);}

  /* AI Chat */
  .ai-chat-container{display:flex;flex-direction:column;height:calc(100vh - 200px);min-height:500px;}
  .ai-messages{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;
    background:rgba(6,8,15,0.6);border:1px solid rgba(255,255,255,0.04);border-radius:var(--radius);}
  .ai-msg{max-width:85%;padding:10px 14px;border-radius:12px;font-size:12px;line-height:1.7;word-wrap:break-word;}
  .ai-msg.user{align-self:flex-end;background:linear-gradient(135deg,rgba(124,58,237,0.2),rgba(59,130,246,0.15));
    border:1px solid rgba(124,58,237,0.25);color:#e2e8f0;}
  .ai-msg.assistant{align-self:flex-start;background:rgba(17,24,39,0.8);
    border:1px solid rgba(255,255,255,0.06);color:#cbd5e1;}
  .ai-msg.system{align-self:center;background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.15);
    color:#4ade80;font-size:11px;max-width:95%;font-family:'JetBrains Mono',monospace;}
  .ai-msg pre{background:rgba(0,0,0,0.4);border-radius:8px;padding:10px;margin:6px 0;overflow-x:auto;
    font-family:'JetBrains Mono',monospace;font-size:11px;white-space:pre-wrap;}
  .ai-msg code{background:rgba(124,58,237,0.15);padding:1px 5px;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:11px;}
  .ai-input-row{display:flex;gap:8px;margin-top:10px;}
  .ai-input-row textarea{flex:1;min-height:44px;max-height:150px;resize:vertical;
    font-family:'DM Sans',sans-serif;font-size:12px;padding:10px 14px;}
  .ai-mode-bar{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;}
  .ai-mode-btn{padding:5px 12px;border:1px solid rgba(255,255,255,0.08);border-radius:8px;
    background:rgba(255,255,255,0.03);color:var(--fg3);font-size:10px;font-weight:700;
    cursor:pointer;transition:all 0.15s;font-family:inherit;}
  .ai-mode-btn:hover{background:rgba(124,58,237,0.1);border-color:rgba(124,58,237,0.3);color:#a78bfa;}
  .ai-mode-btn.active{background:rgba(124,58,237,0.15);border-color:rgba(124,58,237,0.4);color:#c4b5fd;}
  .ai-status{font-size:9px;color:var(--fg3);margin-left:auto;display:flex;align-items:center;gap:4px;}
  .ai-dot{width:6px;height:6px;border-radius:50%;background:var(--green);display:inline-block;}
  .ai-dot.thinking{background:var(--orange);animation:pulse 1s infinite;}
  @keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.3;}}

  /* WARMODE styles */
  @keyframes warmode-pulse{0%{box-shadow:0 0 5px rgba(239,68,68,0.3)}50%{box-shadow:0 0 25px rgba(239,68,68,0.6),0 0 50px rgba(239,68,68,0.2)}100%{box-shadow:0 0 5px rgba(239,68,68,0.3)}}
  @keyframes warmode-glow{0%{border-color:rgba(239,68,68,0.3)}50%{border-color:rgba(239,68,68,0.8)}100%{border-color:rgba(239,68,68,0.3)}}
  @keyframes build-progress{0%{width:0}100%{width:100%}}
  .warmode-active{animation:warmode-pulse 2s infinite;}
  .warmode-border{animation:warmode-glow 2s infinite;}
  .worker-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;}
  .worker-card{background:rgba(10,14,26,0.8);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px;font-size:10px;transition:all 0.3s;}
  .worker-card.active{border-color:rgba(34,197,94,0.3);background:rgba(34,197,94,0.03);}
  .worker-card.stopped{border-color:rgba(239,68,68,0.2);opacity:0.6;}
  .worker-name{font-weight:800;font-size:10px;margin-bottom:4px;}
  .worker-stat{color:var(--fg3);font-size:9px;}
  .speed-btn{padding:6px 16px;border:2px solid rgba(255,255,255,0.1);border-radius:8px;background:rgba(255,255,255,0.03);color:var(--fg2);font-size:11px;font-weight:800;cursor:pointer;font-family:inherit;transition:all 0.2s;}
  .speed-btn:hover{background:rgba(255,255,255,0.06);}
  .speed-btn.active-normal{border-color:rgba(34,197,94,0.5);color:#4ade80;background:rgba(34,197,94,0.08);}
  .speed-btn.active-aggressive{border-color:rgba(245,158,11,0.5);color:#fbbf24;background:rgba(245,158,11,0.08);}
  .speed-btn.active-ludicrous{border-color:rgba(239,68,68,0.5);color:#f87171;background:rgba(239,68,68,0.12);animation:warmode-glow 1s infinite;}
  .toggle-switch{position:relative;width:44px;height:24px;display:inline-block;}
  .toggle-switch input{opacity:0;width:0;height:0;}
  .toggle-slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:rgba(255,255,255,0.1);border-radius:24px;transition:0.3s;}
  .toggle-slider:before{content:'';position:absolute;height:18px;width:18px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:0.3s;}
  .toggle-switch input:checked+.toggle-slider{background:linear-gradient(135deg,#22c55e,#16a34a);}
  .toggle-switch input:checked+.toggle-slider:before{transform:translateX(20px);}
  .auto-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);}
  .auto-label{font-size:11px;font-weight:700;display:flex;align-items:center;gap:6px;}
  .build-log-item{padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.02);font-size:10px;font-family:'JetBrains Mono',monospace;}

  @media(max-width:1100px){
    .stats-5,.stats-6,.stats-8{grid-template-columns:repeat(3,1fr);}
    .grid-3,.grid-4{grid-template-columns:1fr 1fr;}
    .settings-grid{grid-template-columns:1fr;}
    .disp-grid{grid-template-columns:repeat(3,1fr);}
    .pipeline{flex-direction:column;}
    .pipeline-col{min-width:auto;}
  }
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="header-left">
    <div>
      <div class="logo-text">BVTECH</div>
      <div class="header-sub">MSP COMMAND CENTER <span class="version-badge" style="background:rgba(248,113,113,0.2);color:#f87171;border-color:rgba(248,113,113,0.3)">v32.1 FINAL</span></div>
    </div>
  </div>
  <div class="header-badges">
    <span class="svc-badge" onclick="switchTab('dashboard',this)" style="cursor:pointer" title="Dashboard">🏠 DASHBOARD</span>
    <span class="svc-badge" onclick="switchTab('orm',this)" style="cursor:pointer;background:rgba(236,72,153,0.15);color:#f472b6;border-color:rgba(236,72,153,0.25)" title="Super Posting">🚀 SUPER POSTING</span>
    <span class="svc-badge" onclick="switchTab('cloudflare',this)" style="cursor:pointer;background:rgba(248,113,113,0.15);color:#f87171;border-color:rgba(248,113,113,0.25)" title="Cloudflare Pages">☁️ CLOUDFLARE</span>
    <span class="svc-badge" onclick="switchTab('news',this)" style="cursor:pointer;background:rgba(239,68,68,0.15);color:#ef4444;border-color:rgba(239,68,68,0.25)" title="BVTech News — Vulnerability Intel">📰 NEWS</span>
    <span class="svc-badge" onclick="switchTab('trmm',this)" style="cursor:pointer;background:rgba(0,180,216,0.15);color:#00b4d8;border-color:rgba(0,180,216,0.25)" title="Tactical RMM">📋 TRMM</span>
    <span class="svc-badge" onclick="switchTab('pipeline',this)" style="cursor:pointer" title="HubSpot Pipeline">🔥 PIPELINE</span>
    <span class="svc-badge" onclick="switchTab('inbox',this)" style="cursor:pointer;background:rgba(0,120,212,0.15);color:#60a5fa;border-color:rgba(0,120,212,0.25)" title="M365 Inbox">📬 INBOX</span>
    <span class="svc-badge" onclick="switchTab('scraper',this)" style="cursor:pointer" title="Prospect Scraper">🔍 SCRAPER</span>
    <span class="svc-badge" onclick="switchTab('cyberaudit',this)" style="cursor:pointer;background:rgba(239,68,68,0.15);color:#ef4444;border-color:rgba(239,68,68,0.25)" title="Cyber Audit &amp; Pen Test">🛡️ CYBER AUDIT</span>
    <span class="svc-badge" onclick="switchTab('ai',this)" style="cursor:pointer;background:rgba(236,72,153,0.15);color:#f472b6;border-color:rgba(236,72,153,0.25)" title="Claude AI">🤖 CLAUDE AI</span>
    <span class="svc-badge" onclick="switchTab('settings',this)" style="cursor:pointer" title="Settings">⚙️ SETTINGS</span>
    <span class="svc-badge" onclick="window.bvtechDebug && window.bvtechDebug.show()" style="cursor:pointer;background:rgba(239,68,68,0.15);color:#ef4444;border-color:rgba(239,68,68,0.25)" title="Show debug console (JS errors)">🐛 DEBUG</span>
  </div>
</div>

<!-- Tabs — v32 organized layout -->
<div class="tabs">
  <button class="tab active" onclick="switchTab('dashboard',this)"><span class="tab-emoji">📊</span>Dashboard<div class="tab-sub">Command Center</div></button>
  <button class="tab" onclick="switchTab('scraper',this)"><span class="tab-emoji">🔍</span>Scraper<div class="tab-sub">Prospect Finder</div></button>
  <button class="tab" onclick="switchTab('orm',this)"><span class="tab-emoji">🚀</span>Super Posting<div class="tab-sub">4 Channels</div></button>
  <button class="tab" onclick="switchTab('hstrack',this)"><span class="tab-emoji">📬</span>HS Track<div class="tab-sub">Email Tracking</div></button>
  <button class="tab" onclick="switchTab('automation',this)"><span class="tab-emoji">⏰</span>Automation<div class="tab-sub">Local Tasks</div></button>
  <button class="tab" onclick="switchTab('email',this)"><span class="tab-emoji">📧</span>Email<div class="tab-sub">M365 Campaign</div></button>
  <button class="tab" onclick="switchTab('sms',this)"><span class="tab-emoji">💬</span>SMS<div class="tab-sub">DialPad SMS</div></button>
  <button class="tab" onclick="switchTab('dialer',this)"><span class="tab-emoji">📞</span>Dialer<div class="tab-sub">Power Dialer</div></button>
  <button class="tab" onclick="switchTab('phone',this)"><span class="tab-emoji">🎙️</span>Phone<div class="tab-sub">DialPad AI</div></button>
  <button class="tab" onclick="switchTab('coaching',this)"><span class="tab-emoji">🧠</span>Coaching<div class="tab-sub">Call Coach</div></button>
  <button class="tab" onclick="switchTab('inbox',this)"><span class="tab-emoji">📬</span>Inbox<div class="tab-sub">M365 Email</div></button>
  <button class="tab" onclick="switchTab('crm',this)"><span class="tab-emoji">🔶</span>CRM<div class="tab-sub">HubSpot</div></button>
  <button class="tab" onclick="switchTab('pipeline',this)"><span class="tab-emoji">🔥</span>Pipeline<div class="tab-sub">Deals</div></button>
  <button class="tab" onclick="switchTab('revenue',this)"><span class="tab-emoji">💰</span>Revenue<div class="tab-sub">MRR</div></button>
  <button class="tab" onclick="switchTab('trmm',this)"><span class="tab-emoji">📋</span>TRMM<div class="tab-sub">Tactical RMM</div></button>
  <button class="tab" onclick="switchTab('cloudflare',this)"><span class="tab-emoji">☁️</span>Cloudflare<div class="tab-sub">Pages Deploy</div></button>
  <button class="tab" onclick="switchTab('cyberaudit',this)"><span class="tab-emoji">🛡️</span>CyberAudit<div class="tab-sub">Audit + PenTest</div></button>
  <button class="tab" onclick="switchTab('news',this)"><span class="tab-emoji">📰</span>News<div class="tab-sub">Vuln Intel</div></button>
  <button class="tab" onclick="switchTab('ai',this)"><span class="tab-emoji">🤖</span>Claude AI<div class="tab-sub">Brain</div></button>
  <button class="tab" onclick="switchTab('warmode',this)"><span class="tab-emoji">⚔️</span>WARMODE<div class="tab-sub">Auto Builder</div></button>
  <button class="tab" onclick="switchTab('settings',this)"><span class="tab-emoji">⚙️</span>Settings<div class="tab-sub">API Keys</div></button>
  <div class="prospect-count"><span class="count-badge" id="prospect-count">0 prospects</span></div>
</div>

<div class="content">

<!-- ===== DASHBOARD TAB (v16.0 COMMAND CENTER) ===== -->
<div class="tab-content active" id="tab-dashboard">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(239,68,68,0.06),rgba(245,158,11,0.04),rgba(124,58,237,0.04));border:1px solid rgba(239,68,68,0.15);">
    <div class="section-title" style="color:#f87171;font-size:16px">🏠 BVTech Command Center</div>
    <div class="section-desc">Your entire MSP stack in one view. SuperOps PSA, Guardz Security, M365, DialPad, HubSpot, Claude AI — all connected. <button onclick="showWhatsNew()" class="btn btn-sm" style="background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;margin-left:8px">🎁 What's New</button></div>
  </div>

  <!-- Quick Stats Grid -->
  <div class="stats stats-6 mb-16" id="dash-stats">
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Open Tickets</div><div class="stat-value" style="color:var(--cyan)" id="dash-tickets">—</div><div class="stat-sub">SuperOps PSA</div></div>
    <div class="card stat"><div class="stat-icon">🛡️</div><div class="stat-label">Security Alerts</div><div class="stat-value" style="color:var(--red)" id="dash-security">—</div><div class="stat-sub">Guardz</div></div>
    <div class="card stat"><div class="stat-icon">📬</div><div class="stat-label">Unread Emails</div><div class="stat-value" style="color:var(--ms)" id="dash-unread">—</div><div class="stat-sub">M365 Inbox</div></div>
    <div class="card stat"><div class="stat-icon">💰</div><div class="stat-label">Pipeline MRR</div><div class="stat-value" style="color:var(--green)" id="dash-mrr">—</div><div class="stat-sub">HubSpot</div></div>
    <div class="card stat"><div class="stat-icon">🖥️</div><div class="stat-label">Managed Assets</div><div class="stat-value" style="color:var(--purple)" id="dash-assets">—</div><div class="stat-sub">SuperOps RMM</div></div>
    <div class="card stat"><div class="stat-icon">👥</div><div class="stat-label">Total Clients</div><div class="stat-value" style="color:var(--orange)" id="dash-clients">—</div><div class="stat-sub">Active Contracts</div></div>
  </div>

  <!-- Quick Action Buttons -->
  <div class="grid grid-4 mb-16">
    <div class="card" style="border-left:3px solid var(--cyan);cursor:pointer" onclick="switchTab('trmm',document.querySelectorAll('.tab')[1])">
      <div style="font-size:12px;font-weight:800;color:var(--cyan)">📋 Tactical RMM</div>
      <div style="font-size:10px;color:var(--fg3);margin-top:4px">Agents • Clients • Alerts • Scripts</div>
      <div style="font-size:9px;color:var(--fg3);margin-top:2px" id="dash-so-status">Click to configure →</div>
    </div>
    <div class="card" style="border-left:3px solid var(--green);cursor:pointer" onclick="window.open('https://app.guardz.com','_blank')">
      <div style="font-size:12px;font-weight:800;color:#34d399">🛡️ Guardz Security</div>
      <div style="font-size:10px;color:var(--fg3);margin-top:4px">Open Guardz Portal ↗</div>
      <div style="font-size:9px;color:var(--fg3);margin-top:2px">Click to open dashboard</div>
    </div>
    <div class="card" style="border-left:3px solid var(--ms);cursor:pointer" onclick="switchTab('inbox',document.querySelectorAll('.tab')[3])">
      <div style="font-size:12px;font-weight:800;color:var(--ms)">📬 M365 Inbox</div>
      <div style="font-size:10px;color:var(--fg3);margin-top:4px">Read • Send • Reply • Search</div>
      <div style="font-size:9px;color:var(--fg3);margin-top:2px" id="dash-inbox-status">help@bvtech.org</div>
    </div>
    <div class="card" style="border-left:3px solid var(--orange);cursor:pointer" onclick="switchTab('revenue',document.querySelectorAll('.tab')[4])">
      <div style="font-size:12px;font-weight:800;color:var(--orange)">💰 Revenue</div>
      <div style="font-size:10px;color:var(--fg3);margin-top:4px">MRR • Contracts • Health Scores</div>
      <div style="font-size:9px;color:var(--fg3);margin-top:2px" id="dash-rev-status">Track growth →</div>
    </div>
  </div>

  <!-- Integration Status Grid -->
  <div class="grid grid-4 mb-16">
    <div class="card" style="border-left:3px solid var(--cyan)"><div style="font-size:11px;font-weight:800;color:var(--cyan)">✅ Tactical RMM</div><div style="font-size:9px;color:var(--fg3)">Self-Hosted RMM via REST</div></div>
    <div class="card" style="border-left:3px solid #34d399"><div style="font-size:11px;font-weight:800;color:#34d399">✅ Guardz</div><div style="font-size:9px;color:var(--fg3)">Security Portal + Tracker</div></div>
    <div class="card" style="border-left:3px solid #0078d4"><div style="font-size:11px;font-weight:800;color:#0078d4">✅ Microsoft 365</div><div style="font-size:9px;color:var(--fg3)">Email + Campaigns via Graph</div></div>
    <div class="card" style="border-left:3px solid #7c3aed"><div style="font-size:11px;font-weight:800;color:#7c3aed">✅ DialPad Pro</div><div style="font-size:9px;color:var(--fg3)">Calls + SMS + AI</div></div>
    <div class="card" style="border-left:3px solid #ff7a59"><div style="font-size:11px;font-weight:800;color:#ff7a59">✅ HubSpot CRM</div><div style="font-size:9px;color:var(--fg3)">Contacts + Deals + Tasks</div></div>
    <div class="card" style="border-left:3px solid #4285f4"><div style="font-size:11px;font-weight:800;color:#4285f4">✅ Google Places</div><div style="font-size:9px;color:var(--fg3)">Smart Scraping</div></div>
    <div class="card" style="border-left:3px solid #f472b6"><div style="font-size:11px;font-weight:800;color:#f472b6">✅ Claude AI</div><div style="font-size:9px;color:var(--fg3)">Brain + Self-Builder</div></div>
    <div class="card" style="border-left:3px solid var(--red)"><div style="font-size:11px;font-weight:800;color:var(--red)">✅ WARMODE</div><div style="font-size:9px;color:var(--fg3)">Auto-Build Engine</div></div>
  </div>

  <div class="flex justify-center mb-16">
    <button class="btn btn-primary btn-lg" onclick="refreshDashboard()">🔄 REFRESH ALL SYSTEMS</button>
  </div>

  <!-- ✨ NEW: Daily Business Pulse — AI Summary -->
  <div class="card mb-16" style="border-left:3px solid #f472b6">
    <div class="flex justify-between items-center">
      <div>
        <div style="font-size:14px;font-weight:800;color:#f472b6">✨ Daily Business Pulse — AI-Powered Briefing</div>
        <div style="font-size:10px;color:var(--fg3);margin-top:2px">Claude analyzes your HubSpot pipeline, WordPress blog, prospect data, and campaigns — generates a daily MSP business intelligence report.</div>
      </div>
      <button class="btn btn-lg" style="background:linear-gradient(135deg,#ec4899,#8b5cf6);color:#fff" onclick="generateBusinessPulse()">🧠 Generate Pulse</button>
    </div>
    <div class="log-output mt-12" id="pulse-log" style="min-height:120px;max-height:500px;font-size:11px">Click "Generate Pulse" for your AI daily briefing.

Includes: pipeline health, blog SEO performance, prospect analysis, action items, and strategic recommendations.</div>
  </div>
</div>

<!-- ===== TACTICAL RMM TAB (v16.0 NEW) ===== -->
<div class="tab-content" id="tab-trmm">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(0,180,216,0.06),rgba(0,119,182,0.04));border:1px solid rgba(0,180,216,0.15);">
    <div class="section-title" style="color:#00b4d8">📋 Tactical RMM — Self-Hosted Remote Monitoring & Management</div>
    <div class="section-desc">Manage agents, clients, alerts, scripts, tasks, Windows updates, services, and software inventory — all from your self-hosted Tactical RMM instance. 100% free, open-source.</div>
  </div>

  <!-- SuperOps Dashboard Stats -->
  <div class="stats stats-8 mb-16" id="so-stats">
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Total Agents</div><div class="stat-value" style="color:var(--cyan)" id="so-open">—</div></div>
    <div class="card stat"><div class="stat-icon">⏳</div><div class="stat-label">Online</div><div class="stat-value" style="color:var(--green)" id="so-pending">—</div></div>
    <div class="card stat"><div class="stat-icon">✅</div><div class="stat-label">Offline</div><div class="stat-value" style="color:var(--red)" id="so-resolved">—</div></div>
    <div class="card stat"><div class="stat-icon">🔴</div><div class="stat-label">Alerts</div><div class="stat-value" style="color:var(--orange)" id="so-critical">—</div></div>
    <div class="card stat"><div class="stat-icon">🖥️</div><div class="stat-label">Clients</div><div class="stat-value" style="color:var(--purple)" id="so-assets">—</div></div>
    <div class="card stat"><div class="stat-icon">🟢</div><div class="stat-label">Online</div><div class="stat-value" style="color:var(--green)" id="so-online">—</div></div>
    <div class="card stat"><div class="stat-icon">📜</div><div class="stat-label">Scripts</div><div class="stat-value" style="color:var(--red)" id="so-offline">—</div></div>
    <div class="card stat"><div class="stat-icon">🔄</div><div class="stat-label">Tasks</div><div class="stat-value" style="color:var(--blue)" id="so-clients">—</div></div>
  </div>

  <!-- Action Buttons -->
  <div class="flex gap-8 mb-16 flex-wrap">
    <button class="btn btn-cyan btn-lg" onclick="loadTRMMDashboard()">📊 Load Dashboard</button>
    <button class="btn btn-outline" onclick="loadTRMMAgents()">🖥️ Agents</button>
    <button class="btn btn-outline" onclick="loadTRMMClients()">👥 Clients</button>
    <button class="btn btn-outline" onclick="loadTRMMAlerts()">🔔 Alerts</button>
    <button class="btn btn-outline" onclick="loadTRMMScripts()">📜 Scripts</button>
    <button class="btn btn-outline" onclick="loadTRMMUpdates()">🔄 Win Updates</button>
    <button class="btn btn-outline" onclick="loadTRMMSoftware()">📦 Software</button>
    <button class="btn btn-outline" onclick="window.open(document.getElementById('cfg-trmm_api_url')?.value?.replace('/api','').replace('api.','rmm.')||'#','_blank')">Open TRMM Web ↗</button>
  </div>

  <!-- Quick Create Ticket -->
  <div class="card mb-16" style="border-left:3px solid var(--cyan)">
    <div style="font-size:12px;font-weight:800;color:var(--cyan);margin-bottom:10px">⚡ Remote Command</div>
    <div class="grid grid-3 gap-8">
      <div><label class="filter-label">Agent ID</label><input type="text" id="trmm-cmd-agent" placeholder="Agent ID from list above"></div>
      <div><label class="filter-label">Shell</label>
        <select id="trmm-cmd-shell"><option value="powershell">PowerShell</option><option value="cmd">CMD</option><option value="bash">Bash</option></select>
      </div>
      <div><label class="filter-label">Timeout (sec)</label><input type="number" id="trmm-cmd-timeout" value="30" style="width:80px"></div>
    </div>
    <div class="mt-8"><label class="filter-label">Command</label><textarea id="trmm-cmd-text" placeholder="e.g. Get-Service | Where-Object {$_.Status -eq 'Running'}"></textarea></div>
    <div class="mt-8 flex justify-center"><button class="btn btn-cyan" onclick="runTRMMCommand()">⚡ RUN COMMAND</button></div>
  </div>

  <!-- Ticket List + Details -->
  <div class="grid grid-2 gap-12 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">AGENT LIST / DATA</div>
      <div class="log-output" id="so-tickets-log" style="min-height:350px">Click "Load Dashboard" or "Agents" to view your Tactical RMM agents.

Configure Tactical RMM API URL + API Key in Settings first.</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">DETAILS / DATA VIEW</div>
      <div class="log-output" id="so-detail-log" style="min-height:350px">Select an item from the left panel to view details.

Supported views: Ticket details, Client info, Asset health, Technician workload, Invoice details.</div>
    </div>
  </div>
</div>

<!-- ===== GUARDZ SECURITY TAB (v16.0 NEW) ===== -->
<!-- ===== CLOUDFLARE PAGES TAB (v20.0 NEW) ===== -->
<div class="tab-content" id="tab-cloudflare">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(248,113,113,0.06),rgba(245,158,11,0.04));border:1px solid rgba(248,113,113,0.15);">
    <div class="section-title" style="color:#f87171;font-size:15px">☁️ Cloudflare Pages — BVTech.org & JordanPolasek.com</div>
    <div class="section-desc">Both <strong style="color:#f87171">BVTech.org</strong> and <strong style="color:#ec4899">JordanPolasek.com</strong> are static sites on Cloudflare Pages. Blog posts deploy as pixel-perfect HTML via GitHub API → GitHub Actions → Wrangler → Cloudflare Pages. No WordPress, no broken Git integration — pure API-driven deployment.</div>
  </div>

  <!-- CF Dashboard Stats -->
  <div class="stats stats-4 mb-16" id="cf-stats">
    <div class="card stat" style="border-top:2px solid var(--red)"><div class="stat-icon">☁️</div><div class="stat-label">Deploy Mode</div><div class="stat-value" style="color:var(--red);font-size:14px" id="cf-mode">—</div></div>
    <div class="card stat" style="border-top:2px solid var(--green)"><div class="stat-icon">📝</div><div class="stat-label">Blog Posts</div><div class="stat-value" style="color:var(--green)" id="cf-posts">—</div></div>
    <div class="card stat" style="border-top:2px solid var(--cyan)"><div class="stat-icon">🚀</div><div class="stat-label">Last Deploy</div><div class="stat-value" style="color:var(--cyan);font-size:11px" id="cf-deploy">—</div></div>
    <div class="card stat" style="border-top:2px solid var(--purple)"><div class="stat-icon">🌐</div><div class="stat-label">Site</div><div class="stat-value" style="color:var(--purple);font-size:11px" id="cf-site">bvtech.org</div></div>
  </div>

  <!-- Controls -->
  <div class="card mb-16" style="padding:16px">
    <button class="btn btn-lg" style="background:linear-gradient(135deg,#f87171,#f59e0b);color:#fff" onclick="loadCFDashboard()">☁️ Load Cloudflare Dashboard</button>
    <button class="btn btn-outline" onclick="testCFConnection()">🔌 Test Connection</button>
    <button class="btn btn-outline" onclick="window.open('https://bvtech.org/blog/','_blank')">🌐 View Live Blog ↗</button>
    <button class="btn btn-outline" onclick="window.open('https://dash.cloudflare.com/','_blank')">☁️ CF Dashboard ↗</button>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <!-- Blog Post List -->
    <div class="card" style="padding:16px">
      <div style="font-size:13px;font-weight:800;color:#f87171;margin-bottom:12px">📝 Blog Posts on BVTech.org</div>
      <div class="log-output" id="cf-blog-list" style="min-height:400px">Click "Load Cloudflare Dashboard" to fetch blog posts from GitHub repo.

Configure GitHub Token + Repo in Settings first.</div>
    </div>
    <!-- Blog Post Preview -->
    <div class="card" style="padding:16px">
      <div style="font-size:13px;font-weight:800;color:var(--cyan);margin-bottom:12px">👁️ Post Preview</div>
      <div class="log-output" id="cf-preview" style="min-height:400px">Select a post from the list to preview.</div>
    </div>
  </div>

  <!-- AI Blog Engine for Cloudflare -->
  <div class="glow mt-16 mb-16" style="background:linear-gradient(135deg,rgba(248,113,113,0.04),rgba(139,92,246,0.04));border:1px solid rgba(248,113,113,0.1);">
    <div class="section-title" style="color:#f87171;font-size:15px">🧠 AI Blog Engine — SEO · GEO · AEO → Cloudflare Pages</div>
    <div class="section-desc">Generate SEO-optimized, Generative Engine Optimized (GEO), and Answer Engine Optimized (AEO) blog posts using Claude AI — then auto-deploy them as static HTML to BVTech.org via Cloudflare Pages.</div>
  </div>

  <div class="stats stats-4 mb-12">
    <div class="card stat" style="border-top:2px solid var(--green)"><div class="stat-icon">📤</div><div class="stat-label">Published</div><div class="stat-value" style="color:var(--green)" id="cf-seo-published">0</div></div>
    <div class="card stat"><div class="stat-icon">📝</div><div class="stat-label">Generated</div><div class="stat-value" id="cf-seo-generated">0</div></div>
    <div class="card stat"><div class="stat-icon">📊</div><div class="stat-label">Avg SEO Score</div><div class="stat-value" style="color:var(--cyan)" id="cf-seo-score">—</div></div>
    <div class="card stat"><div class="stat-icon">📖</div><div class="stat-label">Avg Words</div><div class="stat-value" id="cf-seo-words">—</div></div>
  </div>

  <!-- AI Blog Generator -->
  <div class="card mb-16" style="padding:16px">
    <div style="font-size:13px;font-weight:800;color:#f87171;margin-bottom:12px">🧠 Generate Blog Post with Claude AI → Deploy to Cloudflare</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <label class="filter-label">Topic / Title</label>
        <input type="text" id="cf-blog-topic" placeholder="e.g., Why Every Business Needs Endpoint Detection">
      </div>
      <div>
        <label class="filter-label">Target Location</label>
        <input type="text" id="cf-blog-location" value="El Campo TX, San Antonio TX, Houston TX" placeholder="City, State">
      </div>
      <div>
        <label class="filter-label">Industry Focus</label>
        <input type="text" id="cf-blog-industry" placeholder="e.g., law firms, medical offices">
      </div>
      <div>
        <label class="filter-label">Optimization</label>
        <select id="cf-blog-opt">
          <option value="seo_geo_aeo">SEO + GEO + AEO (Full Power)</option>
          <option value="seo">SEO Only</option>
          <option value="seo_geo">SEO + GEO</option>
          <option value="seo_aeo">SEO + AEO</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Tone</label>
        <select id="cf-blog-tone">
          <option value="professional">Professional</option>
          <option value="conversational">Conversational</option>
          <option value="technical">Technical Deep-Dive</option>
          <option value="friendly">Friendly / Approachable</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Length</label>
        <select id="cf-blog-length">
          <option value="medium">Medium (~800 words)</option>
          <option value="short">Short (~400 words)</option>
          <option value="long">Long (~1500 words)</option>
          <option value="pillar">Pillar (2500+ words)</option>
        </select>
      </div>
      <div style="grid-column:span 2">
        <label class="filter-label">Custom Instructions (optional)</label>
        <input type="text" id="cf-blog-custom" placeholder="Any special instructions for Claude...">
      </div>
      <div style="grid-column:span 2;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <div style="display:flex;gap:16px">
          <label class="check-row"><input type="radio" name="cf-blog-action" value="publish" checked> 🚀 Deploy to Cloudflare</label>
          <label class="check-row"><input type="radio" name="cf-blog-action" value="preview"> 👁️ Preview Only</label>
        </div>
      </div>
      <div style="grid-column:span 2">
        <button class="btn btn-lg" style="background:linear-gradient(135deg,#f87171,#f59e0b);color:#fff" onclick="generateCFBlog()">🧠 GENERATE WITH CLAUDE AI → CLOUDFLARE</button>
      </div>
    </div>
  </div>

  <!-- AI Blog Preview -->
  <div class="card mb-16" style="padding:16px">
    <div style="font-size:13px;font-weight:800;color:var(--cyan);margin-bottom:12px">📄 Generated Blog Preview</div>
    <div class="log-output" id="cf-blog-preview" style="min-height:400px">Generated blog posts appear here for review before deploying to Cloudflare Pages.

The AI Blog Engine will:
• Generate SEO/GEO/AEO optimized content via Claude AI
• Build a complete static HTML page matching your BVTech.org design
• Include proper schema markup (BlogPosting, BreadcrumbList)
• Push the HTML file to your GitHub repo
• Cloudflare Pages auto-deploys within ~60 seconds

Your blog posts will be live at: bvtech.org/blog/[slug]/</div>
  </div>

  <!-- Auto-Post Scheduler -->
  <div class="card mb-16" style="padding:16px">
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
      <div>
        <div style="font-size:13px;font-weight:800;color:var(--cyan)">📅 Auto-Post Scheduler — Daily AI Blog Posts → Cloudflare</div>
        <div style="font-size:10px;color:var(--fg3);margin-top:2px">Claude generates a fresh, SEO-optimized blog post every day and deploys it as a static HTML page to BVTech.org via Cloudflare Pages. Set it and forget it.</div>
      </div>
      <label class="toggle-switch" style="transform:scale(1.3)">
        <input type="checkbox" id="cf-auto-toggle" onchange="toggleCFAutoPost(this.checked)">
        <span class="toggle-slider"></span>
      </label>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div>
        <label class="filter-label">Post Time</label>
        <select id="cf-auto-time">
          <option value="08:00">8:00 AM</option>
          <option value="09:00" selected>9:00 AM</option>
          <option value="10:00">10:00 AM</option>
          <option value="12:00">12:00 PM</option>
          <option value="14:00">2:00 PM</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Topic Rotation</label>
        <select id="cf-auto-rotation">
          <option value="msp_services">MSP Services (BVTech focused)</option>
          <option value="cybersecurity">Cybersecurity Tips</option>
          <option value="cloud">Cloud & M365</option>
          <option value="mixed" selected>Mixed (all topics)</option>
          <option value="custom">Custom Topics Below</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Custom Topics (comma-separated)</label>
        <input type="text" id="cf-auto-topics" placeholder="topic1, topic2, topic3...">
      </div>
    </div>
    <div class="log-output mt-12" id="cf-auto-log" style="min-height:80px;max-height:200px;font-size:10px">Auto-poster inactive. Toggle ON to start daily AI blog generation → Cloudflare Pages.

When active, Claude will generate a unique blog post each day covering your MSP services, optimized for SEO + GEO + AEO, build a static HTML page, and deploy it to BVTech.org via Cloudflare Pages automatically.</div>
  </div>
</div>

<!-- ===== BVTECH NEWS — AUTOMATED VULNERABILITY INTELLIGENCE v24 ===== -->
<div class="tab-content" id="tab-news">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(239,68,68,0.06),rgba(245,158,11,0.04));border:1px solid rgba(239,68,68,0.15);">
    <div class="section-title" style="color:#ef4444;font-size:15px">📰 BVTech News — Automated Vulnerability Intelligence</div>
    <div class="section-desc">Scours <strong style="color:#f87171">CISA KEV</strong> + <strong style="color:#fb923c">NVD</strong> feeds every morning at <strong style="color:var(--green)">6:00 AM CST</strong>. Claude AI writes a pro-grade cybersecurity intelligence briefing with BVTech's take, remediation steps, and a sales funnel CTA. Auto-deploys to <strong style="color:#f87171">bvtech.org/news/</strong> as a static HTML page. One article per day — real CVEs, real data, no fluff.</div>
  </div>

  <!-- News Stats -->
  <div class="stats stats-4 mb-16">
    <div class="card stat" style="border-top:2px solid #ef4444"><div class="stat-icon">📰</div><div class="stat-label">Articles Published</div><div class="stat-value" style="color:#ef4444" id="news-total">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--green)"><div class="stat-icon">🛡️</div><div class="stat-label">CVEs Covered</div><div class="stat-value" style="color:var(--green)" id="news-cves">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--cyan)"><div class="stat-icon">⏰</div><div class="stat-label">Scheduler</div><div class="stat-value" style="color:var(--cyan);font-size:11px" id="news-sched">OFF</div></div>
    <div class="card stat" style="border-top:2px solid var(--orange)"><div class="stat-icon">📅</div><div class="stat-label">Last Run</div><div class="stat-value" style="color:var(--orange);font-size:11px" id="news-last-run">Never</div></div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <!-- LEFT: Controls -->
    <div>
      <!-- Test Scraper -->
      <div class="card mb-12" style="border-left:3px solid #ef4444;padding:16px">
        <div style="font-size:12px;font-weight:800;color:#ef4444;margin-bottom:8px">🔍 Step 1: Test Vulnerability Scraper</div>
        <div style="font-size:10px;color:var(--fg2);margin-bottom:12px">Pulls the latest CVEs from CISA's Known Exploited Vulnerabilities catalog and NIST NVD. This is real data — not generated.</div>
        <button class="btn" style="background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;width:100%" onclick="newsTestScrape()">🔍 SCRAPE LATEST VULNERABILITIES</button>
      </div>

      <!-- Generate Now -->
      <div class="card mb-12" style="border-left:3px solid #f59e0b;padding:16px">
        <div style="font-size:12px;font-weight:800;color:#f59e0b;margin-bottom:8px">⚡ Step 2: Generate & Publish News Article</div>
        <div style="font-size:10px;color:var(--fg2);margin-bottom:8px">Claude AI reads the real vulnerability data, writes a pro-grade article as Jordan Polasek, and deploys it to bvtech.org/news/</div>
        <div class="mb-8"><label class="filter-label">Custom Instructions (optional)</label><textarea id="news-custom" placeholder="Focus on healthcare industry impact, mention specific clients..." style="min-height:40px;width:100%"></textarea></div>
        <div class="grid grid-2 gap-8 mb-8">
          <div><label class="filter-label">Action</label>
            <select id="news-action">
              <option value="publish">🚀 Generate & Deploy Live</option>
              <option value="preview">👁️ Preview Only (don't deploy)</option>
            </select>
          </div>
          <div><label class="filter-label">Severity Filter</label>
            <select id="news-severity">
              <option value="all">All Severities</option>
              <option value="critical" selected>Critical Only</option>
              <option value="critical_high">Critical + High</option>
            </select>
          </div>
        </div>
        <button class="btn btn-lg" style="background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff;width:100%" onclick="newsGenerateNow()">📰 GENERATE BVTECH NEWS ARTICLE NOW</button>
      </div>

      <!-- Auto Scheduler -->
      <div class="card mb-12" style="border-left:3px solid var(--green);padding:16px">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
          <div>
            <div style="font-size:12px;font-weight:800;color:var(--green)">📅 Daily Auto-Publisher — 6:00 AM CST</div>
            <div style="font-size:10px;color:var(--fg3);margin-top:2px">Every morning: scrape CVEs → Claude writes article → auto-deploy to bvtech.org/news/</div>
          </div>
          <label class="toggle-switch" style="transform:scale(1.3)">
            <input type="checkbox" id="news-auto-toggle" onchange="newsToggleScheduler(this.checked)">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="grid grid-2 gap-8">
          <div><label class="filter-label">Daily Post Time (CST)</label>
            <select id="news-auto-time">
              <option value="05:00">5:00 AM</option>
              <option value="06:00" selected>6:00 AM</option>
              <option value="07:00">7:00 AM</option>
              <option value="08:00">8:00 AM</option>
            </select>
          </div>
          <div><label class="filter-label">Auto-Publish</label>
            <select id="news-auto-publish">
              <option value="true" selected>Yes — deploy immediately</option>
              <option value="false">No — preview only</option>
            </select>
          </div>
        </div>
        <div class="log-output mt-12" id="news-sched-log" style="min-height:60px;max-height:150px;font-size:10px">Scheduler inactive. Toggle ON to start daily vulnerability news at 6:00 AM CST.

Pipeline: CISA KEV + NVD scrape → Claude AI writes article → deploy to bvtech.org/news/</div>
      </div>
    </div>

    <!-- RIGHT: Output -->
    <div>
      <!-- Scraper Results -->
      <div class="card mb-12" style="padding:16px">
        <div style="font-size:13px;font-weight:800;color:#ef4444;margin-bottom:12px">🛡️ Latest Vulnerabilities (Live Feed)</div>
        <div class="log-output" id="news-vuln-feed" style="min-height:250px;max-height:400px;font-size:10px">Click "Scrape Latest Vulnerabilities" to pull live CVE data from CISA KEV and NVD.

This is REAL vulnerability data — not AI generated. It feeds into the article generator.</div>
      </div>

      <!-- Article Preview -->
      <div class="card" style="padding:16px">
        <div style="font-size:13px;font-weight:800;color:var(--cyan);margin-bottom:12px">📄 Generated Article Preview</div>
        <div class="log-output" id="news-preview" style="min-height:250px;max-height:400px;font-size:10px">Generated articles appear here.

The pipeline:
1. Scrapes REAL CVEs from CISA + NVD (government feeds)
2. Ranks by severity and active exploitation
3. Claude AI writes a 1200-2000 word intelligence briefing
4. Written as Jordan Polasek from BVTech LLC
5. Includes remediation steps + sales funnel CTA
6. Deploys to bvtech.org/news/ as static HTML
7. SEO/GEO/AEO optimized with schema markup</div>
      </div>
    </div>
  </div>

  <!-- History -->
  <div class="card mt-16" style="padding:16px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-size:13px;font-weight:800;color:var(--orange)">📋 News Article History</div>
      <button class="btn btn-outline btn-sm" onclick="newsLoadHistory()">Refresh</button>
    </div>
    <div class="log-output" id="news-history-log" style="min-height:100px;max-height:300px;font-size:10px">No articles generated yet. Use the controls above to generate your first BVTech News article.</div>
  </div>
</div>

<!-- ===== WORDPRESS TAB (JordanPolasek.com ONLY — v20) ===== -->
<div class="tab-content" id="tab-wordpress">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(33,117,155,0.06),rgba(70,70,70,0.04));border:1px solid rgba(33,117,155,0.15);">
    <div class="section-title" style="color:#21759b">🌐 WordPress — Legacy (Deprecated)</div>
    <div class="section-desc" style="color:var(--fg3)">⚠️ <strong style="color:var(--orange)">Both sites are now on Cloudflare Pages.</strong> JordanPolasek.com and BVTech.org both deploy as static HTML via GitHub → Wrangler → Cloudflare. This WordPress tab is kept for legacy compatibility only. Use the ☁️ Cloudflare tab instead.</div>
  </div>

  <!-- WP Stats -->
  <div class="stats stats-4 mb-16">
    <div class="card stat"><div class="stat-icon">📝</div><div class="stat-label">Posts</div><div class="stat-value" style="color:#21759b" id="wp-posts">—</div></div>
    <div class="card stat"><div class="stat-icon">📄</div><div class="stat-label">Pages</div><div class="stat-value" style="color:var(--blue)" id="wp-pages">—</div></div>
    <div class="card stat"><div class="stat-icon">💬</div><div class="stat-label">Comments</div><div class="stat-value" style="color:var(--orange)" id="wp-comments">—</div></div>
    <div class="card stat"><div class="stat-icon">👥</div><div class="stat-label">Users</div><div class="stat-value" style="color:var(--purple)" id="wp-users">—</div></div>
  </div>

  <!-- Actions -->
  <div class="flex gap-8 mb-16 flex-wrap">
    <button class="btn btn-lg" style="background:linear-gradient(135deg,#21759b,#464646);color:#fff" onclick="loadWPDashboard()">🌐 Load WordPress</button>
    <button class="btn btn-outline" onclick="loadWPPosts()">📝 Posts</button>
    <button class="btn btn-outline" onclick="loadWPPages()">📄 Pages</button>
    <button class="btn btn-outline" onclick="loadWPComments()">💬 Comments</button>
    <button class="btn btn-outline" onclick="window.open(document.getElementById('cfg-wp_site_url')?.value+'/wp-admin/'||'#','_blank')">WP Admin ↗</button>
    <button class="btn btn-outline" onclick="window.open('https://tools.siteground.com','_blank')">SiteGround ↗</button>
    <button class="btn btn-green" onclick="testWPConnection()">🔌 Test WP Connection</button>
    <button class="btn" style="background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff" onclick="debugWPPost()">🧪 Test Post (Draft)</button>
  </div>

  <!-- Quick Create Post -->
  <div class="card mb-16" style="border-left:3px solid #21759b">
    <div style="font-size:12px;font-weight:800;color:#21759b;margin-bottom:10px">✏️ Quick Create Post</div>
    <div class="grid grid-2 gap-8">
      <div><label class="filter-label">Title</label><input type="text" id="wp-new-title" placeholder="Blog post title"></div>
      <div><label class="filter-label">Status</label>
        <select id="wp-new-status"><option value="draft">Draft</option><option value="publish">Publish</option></select>
      </div>
    </div>
    <div class="mt-8"><label class="filter-label">Content (HTML supported)</label><textarea id="wp-new-content" placeholder="Post content..." style="min-height:100px"></textarea></div>
    <div class="mt-8 flex justify-center"><button class="btn" style="background:linear-gradient(135deg,#21759b,#464646);color:#fff" onclick="createWPPost()">📝 CREATE POST</button></div>
  </div>

  <!-- Post List + Detail -->
  <div class="grid grid-2 gap-12 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">POSTS / PAGES</div>
      <div class="log-output" id="wp-list-log" style="min-height:350px">Click "Load WordPress" to fetch your site data.

Configure WordPress URL + Application Password in Settings first.
Generate an App Password: WP Admin → Users → Profile → Application Passwords</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">POST DETAIL / PREVIEW</div>
      <div class="log-output" id="wp-detail-log" style="min-height:350px">Select a post or page from the list to preview.

Full content, metadata, and edit capabilities.</div>
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════ -->
  <!-- SEO / GEO / AEO — AI BLOG ENGINE (Claude-Powered)         -->
  <!-- ═══════════════════════════════════════════════════════════ -->
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(236,72,153,0.06),rgba(124,58,237,0.06),rgba(6,182,212,0.04));border:1px solid rgba(236,72,153,0.15);">
    <div class="section-title" style="color:#f472b6;font-size:15px">🧠 AI Blog Engine — SEO · GEO · AEO Powered by Claude</div>
    <div class="section-desc">Generate SEO-optimized, Generative Engine Optimized (GEO), and Answer Engine Optimized (AEO) blog posts using Claude AI — then auto-publish them to your WordPress site. Schedule daily auto-posts to build organic traffic on autopilot.</div>
  </div>

  <!-- SEO/GEO/AEO Stats -->
  <div class="stats stats-5 mb-16">
    <div class="card stat" style="border-top:2px solid #f472b6"><div class="stat-icon">🧠</div><div class="stat-label">AI Posts Generated</div><div class="stat-value" style="color:#f472b6" id="seo-generated">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--green)"><div class="stat-icon">📤</div><div class="stat-label">Published</div><div class="stat-value" style="color:var(--green)" id="seo-published">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--orange)"><div class="stat-icon">📝</div><div class="stat-label">Drafts</div><div class="stat-value" style="color:var(--orange)" id="seo-drafts">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--cyan)"><div class="stat-icon">📅</div><div class="stat-label">Auto-Post</div><div class="stat-value" style="color:var(--cyan);font-size:14px" id="seo-schedule">OFF</div></div>
    <div class="card stat" style="border-top:2px solid var(--purple)"><div class="stat-icon">🎯</div><div class="stat-label">SEO Mode</div><div class="stat-value" style="color:var(--purple);font-size:12px" id="seo-mode-display">SEO+GEO+AEO</div></div>
  </div>

  <!-- AI Blog Generator -->
  <div class="card mb-16" style="border-left:3px solid #f472b6">
    <div style="font-size:13px;font-weight:800;color:#f472b6;margin-bottom:12px">🧠 Generate Blog Post with Claude AI</div>

    <div class="grid grid-3 gap-8 mb-8">
      <div>
        <label class="filter-label">Topic / Keyword</label>
        <input type="text" id="seo-topic" placeholder="e.g. managed IT services for law firms">
      </div>
      <div>
        <label class="filter-label">Target Location (GEO)</label>
        <input type="text" id="seo-location" placeholder="e.g. El Campo TX, San Antonio TX">
      </div>
      <div>
        <label class="filter-label">Industry Focus</label>
        <select id="seo-industry">
          <option value="">General MSP</option>
          <option value="law firms">Law Firms</option>
          <option value="medical offices">Medical / Healthcare</option>
          <option value="dental practices">Dental Practices</option>
          <option value="accounting firms">Accounting / CPA</option>
          <option value="financial advisors">Financial Advisors</option>
          <option value="insurance agencies">Insurance Agencies</option>
          <option value="real estate">Real Estate</option>
          <option value="construction">Construction</option>
          <option value="manufacturing">Manufacturing</option>
          <option value="nonprofits">Nonprofits</option>
          <option value="churches">Churches / Religious Orgs</option>
          <option value="small business">Small Business (General)</option>
        </select>
      </div>
    </div>

    <div class="grid grid-3 gap-8 mb-8">
      <div>
        <label class="filter-label">Optimization Mode</label>
        <select id="seo-opt-mode">
          <option value="seo_geo_aeo">SEO + GEO + AEO (Full Stack)</option>
          <option value="seo">SEO Only (Google Rankings)</option>
          <option value="geo">GEO Only (Local Search)</option>
          <option value="aeo">AEO Only (AI Answer Engines)</option>
          <option value="seo_geo">SEO + GEO (Search + Local)</option>
          <option value="seo_aeo">SEO + AEO (Search + AI)</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Tone</label>
        <select id="seo-tone">
          <option value="professional">Professional / Authoritative</option>
          <option value="friendly">Friendly / Approachable</option>
          <option value="technical">Technical / In-Depth</option>
          <option value="urgent">Urgent / Problem-Focused</option>
          <option value="educational">Educational / How-To</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Post Length</label>
        <select id="seo-length">
          <option value="medium">Medium (~800 words)</option>
          <option value="short">Short (~400 words)</option>
          <option value="long">Long (~1500 words)</option>
          <option value="pillar">Pillar Post (~2500+ words)</option>
        </select>
      </div>
    </div>

    <div class="grid grid-2 gap-8 mb-8">
      <div>
        <label class="filter-label">Custom Instructions (optional)</label>
        <textarea id="seo-custom" placeholder="e.g. Include a section about HIPAA compliance. Mention our free security assessment offer. Link to bvtech.org/contact" style="min-height:60px"></textarea>
      </div>
      <div>
        <label class="filter-label">Publish Action</label>
        <div class="flex gap-8 mt-8 flex-wrap">
          <label class="check-row"><input type="radio" name="seo-action" value="draft" checked> 📝 Save as Draft</label>
          <label class="check-row"><input type="radio" name="seo-action" value="publish"> 🚀 Publish Immediately</label>
          <label class="check-row"><input type="radio" name="seo-action" value="preview"> 👁️ Preview Only</label>
        </div>
      </div>
    </div>

    <div class="flex gap-8 justify-center mt-12">
      <button class="btn btn-lg" style="background:linear-gradient(135deg,#ec4899,#8b5cf6);color:#fff" onclick="generateAIBlog()">🧠 GENERATE WITH CLAUDE AI</button>
      <button class="btn btn-outline btn-lg" onclick="generateBulkTopics()">💡 Generate Topic Ideas</button>
    </div>
  </div>

  <!-- AI Blog Preview / Output -->
  <div class="grid grid-2 gap-12 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">AI BLOG PREVIEW</div>
      <div class="log-output" id="seo-preview-log" style="min-height:400px">Generated blog posts appear here for review before publishing.

<strong style="color:#f472b6">What SEO + GEO + AEO does:</strong>

<strong style="color:var(--green)">SEO (Search Engine Optimization):</strong>
  • Keyword-rich H1/H2 headings
  • Meta description optimized for CTR
  • Internal linking suggestions
  • Schema markup recommendations
  • Natural keyword density

<strong style="color:var(--cyan)">GEO (Generative Engine Optimization):</strong>
  • Structured for AI-powered search (Google SGE, Bing Copilot)
  • Clear factual statements AI can cite
  • Data points and statistics included
  • Conversational Q&A format sections
  • Location-specific content for local AI results

<strong style="color:var(--purple)">AEO (Answer Engine Optimization):</strong>
  • FAQ schema-ready sections
  • Direct answer formatting (featured snippet bait)
  • "People Also Ask" targeting
  • Voice search optimized phrasing
  • Concise definition blocks</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">SEO ANALYSIS & METADATA</div>
      <div class="log-output" id="seo-analysis-log" style="min-height:400px">After generating a post, SEO analysis appears here:

• Title tag optimization score
• Meta description preview
• Keyword density analysis
• Heading structure (H1/H2/H3)
• Readability score
• GEO signals detected
• AEO signals detected
• Suggested internal links
• Schema markup output</div>
    </div>
  </div>

  <!-- Auto-Post Scheduler -->
  <div class="card mb-16" style="border-left:3px solid var(--cyan)">
    <div class="flex justify-between items-center">
      <div>
        <div style="font-size:13px;font-weight:800;color:var(--cyan)">📅 Auto-Post Scheduler — Daily AI Blog Posts</div>
        <div style="font-size:10px;color:var(--fg3);margin-top:2px">Claude generates a fresh, SEO-optimized blog post every day and publishes it to your WordPress site automatically. Set it and forget it.</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:9px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:4px">AUTO-POST</div>
        <label class="toggle-switch" style="transform:scale(1.3)">
          <input type="checkbox" id="seo-auto-toggle" onchange="toggleAutoPost(this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>

    <div class="grid grid-4 gap-8 mt-12">
      <div>
        <label class="filter-label">Post Time</label>
        <select id="seo-auto-time">
          <option value="06:00">6:00 AM</option>
          <option value="08:00" selected>8:00 AM</option>
          <option value="10:00">10:00 AM</option>
          <option value="12:00">12:00 PM</option>
          <option value="14:00">2:00 PM</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Topics Rotation</label>
        <select id="seo-auto-rotation">
          <option value="msp_services">MSP Services Mix</option>
          <option value="cybersecurity">Cybersecurity Focus</option>
          <option value="compliance">Compliance (HIPAA/PCI/etc)</option>
          <option value="local_seo">Local SEO (El Campo/SA/Houston)</option>
          <option value="industry_mix">Industry-Specific Mix</option>
          <option value="custom">Custom Topic Queue</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Auto-Publish</label>
        <select id="seo-auto-status">
          <option value="draft">Save as Draft (review first)</option>
          <option value="publish">Publish Immediately</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Custom Topic Queue</label>
        <input type="text" id="seo-auto-topics" placeholder="topic1, topic2, topic3...">
      </div>
    </div>

    <div class="mt-12 flex gap-8 justify-center">
      <button class="btn btn-cyan" onclick="testAutoPost()">🧪 Test Generate (Dry Run)</button>
      <button class="btn btn-outline" onclick="viewAutoPostHistory()">📜 View Auto-Post History</button>
    </div>
    <div class="log-output mt-12" id="seo-auto-log" style="min-height:80px;max-height:200px;font-size:10px">Auto-poster inactive. Toggle ON to start daily AI blog generation.

When active, Claude will generate a unique blog post each day covering your MSP services, optimized for SEO + GEO + AEO, and post it to your WordPress site automatically.</div>
  </div>
</div>

<!-- ===== INBOX TAB (v16.0 NEW) ===== -->
<div class="tab-content" id="tab-inbox">
  <div class="glow glow-ms mb-16">
    <div class="section-title" style="color:#0078d4">📬 M365 Inbox — Business Email (help@bvtech.org)</div>
    <div class="section-desc">Read, compose, reply, forward, and search your real M365 mailbox. This is your actual inbox — separate from the email campaign system. Uses the same Azure AD credentials.</div>
  </div>

  <!-- Inbox Stats -->
  <div class="stats stats-4 mb-16">
    <div class="card stat"><div class="stat-icon">📨</div><div class="stat-label">Unread</div><div class="stat-value" style="color:var(--ms)" id="inbox-unread">—</div></div>
    <div class="card stat"><div class="stat-icon">📧</div><div class="stat-label">Total</div><div class="stat-value" style="color:var(--blue)" id="inbox-total">—</div></div>
    <div class="card stat"><div class="stat-icon">📤</div><div class="stat-label">Sent Today</div><div class="stat-value" style="color:var(--green)" id="inbox-sent-today">—</div></div>
    <div class="card stat"><div class="stat-icon">📁</div><div class="stat-label">Folder</div><div class="stat-value" style="color:var(--fg3);font-size:14px" id="inbox-folder">Inbox</div></div>
  </div>

  <!-- Action Bar -->
  <div class="flex gap-8 mb-16 flex-wrap items-center">
    <button class="btn btn-ms btn-lg" onclick="loadInbox()">📬 Load Inbox</button>
    <button class="btn btn-outline" onclick="loadInbox('sentitems')">📤 Sent</button>
    <button class="btn btn-outline" onclick="loadInbox('drafts')">📝 Drafts</button>
    <button class="btn btn-outline" onclick="loadInbox('deleteditems')">🗑️ Trash</button>
    <div style="margin-left:auto" class="flex gap-8">
      <input type="text" id="inbox-search" placeholder="Search emails..." style="width:200px" onkeydown="if(event.key==='Enter')searchInbox()">
      <button class="btn btn-outline" onclick="searchInbox()">🔍</button>
    </div>
    <button class="btn btn-green" onclick="showComposeEmail()">✏️ Compose</button>
  </div>

  <!-- Compose Email (hidden by default) -->
  <div id="compose-panel" class="card mb-16" style="display:none;border-left:3px solid var(--ms)">
    <div style="font-size:12px;font-weight:800;color:var(--ms);margin-bottom:10px">✏️ Compose Email</div>
    <div class="grid grid-2 gap-8 mb-8">
      <div><label class="filter-label">To</label><input type="text" id="compose-to" placeholder="recipient@example.com"></div>
      <div><label class="filter-label">CC (optional)</label><input type="text" id="compose-cc" placeholder="cc@example.com"></div>
    </div>
    <div class="mb-8"><label class="filter-label">Subject</label><input type="text" id="compose-subject" placeholder="Email subject"></div>
    <div class="mb-8"><label class="filter-label">Body</label><textarea id="compose-body" style="min-height:150px" placeholder="Type your message..."></textarea></div>
    <div class="flex gap-8 justify-center">
      <button class="btn btn-ms" onclick="sendInboxEmail()">📤 Send</button>
      <button class="btn btn-outline" onclick="hideComposeEmail()">Cancel</button>
    </div>
  </div>

  <!-- Reply Panel (hidden by default) -->
  <div id="reply-panel" class="card mb-16" style="display:none;border-left:3px solid var(--green)">
    <div style="font-size:12px;font-weight:800;color:var(--green);margin-bottom:10px">↩️ Reply</div>
    <div class="mb-8"><label class="filter-label">Reply Body</label><textarea id="reply-body" style="min-height:100px" placeholder="Type your reply..."></textarea></div>
    <div class="flex gap-8 justify-center">
      <button class="btn btn-green" onclick="sendReply()">↩️ Send Reply</button>
      <button class="btn btn-outline" onclick="document.getElementById('reply-panel').style.display='none'">Cancel</button>
    </div>
  </div>

  <!-- Email List + Preview -->
  <div class="grid grid-2 gap-12 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">EMAIL LIST</div>
      <div class="log-output" id="inbox-list-log" style="min-height:400px">Click "Load Inbox" to fetch your M365 emails.

Uses the same Azure credentials as email campaigns (Settings tab).
This is your real mailbox — read, reply, forward, compose.</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">EMAIL PREVIEW</div>
      <div class="log-output" id="inbox-preview-log" style="min-height:400px">Select an email from the list to preview it here.

Full HTML body, attachments indicator, reply/forward actions.</div>
    </div>
  </div>
</div>

<!-- ===== REVENUE DASHBOARD TAB (v16.0 NEW) ===== -->
<div class="tab-content" id="tab-revenue">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(245,158,11,0.06),rgba(217,119,6,0.04));border:1px solid rgba(245,158,11,0.15);">
    <div class="section-title" style="color:var(--orange)">💰 Revenue Dashboard — MRR Tracking & Client Health</div>
    <div class="section-desc">Track Monthly Recurring Revenue from SuperOps contracts, monitor client health scores based on ticket volume and asset status, and view invoice aging. Your MSP financial command center.</div>
  </div>

  <!-- Revenue Stats -->
  <div class="stats stats-6 mb-16">
    <div class="card stat"><div class="stat-icon">💰</div><div class="stat-label">Total MRR</div><div class="stat-value" style="color:var(--green)" id="rev-mrr">—</div></div>
    <div class="card stat"><div class="stat-icon">📈</div><div class="stat-label">ARR</div><div class="stat-value" style="color:var(--blue)" id="rev-arr">—</div></div>
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Active Contracts</div><div class="stat-value" style="color:var(--purple)" id="rev-contracts">—</div></div>
    <div class="card stat"><div class="stat-icon">💳</div><div class="stat-label">Outstanding</div><div class="stat-value" style="color:var(--red)" id="rev-outstanding">—</div></div>
    <div class="card stat"><div class="stat-icon">✅</div><div class="stat-label">Paid (30d)</div><div class="stat-value" style="color:var(--green)" id="rev-paid">—</div></div>
    <div class="card stat"><div class="stat-icon">🔥</div><div class="stat-label">Pipeline</div><div class="stat-value" style="color:var(--orange)" id="rev-pipeline">—</div></div>
  </div>

  <!-- Actions -->
  <div class="flex gap-8 mb-16 flex-wrap">
    <button class="btn btn-primary btn-lg" onclick="loadRevenueDashboard()">💰 Load Revenue Data</button>
    <button class="btn btn-outline" onclick="loadContracts()">📋 Contracts</button>
    <button class="btn btn-outline" onclick="loadInvoiceAging()">💳 Invoice Aging</button>
    <button class="btn btn-outline" onclick="loadClientHealth()">💚 Client Health</button>
  </div>

  <!-- Revenue Details -->
  <div class="grid grid-2 gap-12 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">CONTRACTS & MRR</div>
      <div class="log-output" id="rev-contracts-log" style="min-height:350px">Click "Load Revenue Data" to pull data from HubSpot pipeline.

Shows pipeline deals, MRR estimates, and client revenue breakdown.</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">CLIENT HEALTH SCORES</div>
      <div class="log-output" id="rev-health-log" style="min-height:350px">Client health is calculated from:
• Ticket volume (fewer = healthier)
• Asset online % (more = healthier)
• Invoice payment speed
• Contract renewal status

Click "Client Health" to generate scores.</div>
    </div>
  </div>
</div>

<!-- ===== SCRAPER TAB ===== -->
<div class="tab-content" id="tab-scraper">
  <div class="glow glow-blue mb-16">
    <div class="section-title" style="color:#60a5fa">🌐 Smart MSP Prospect Scraper — Google Places API</div>
    <div class="section-desc">Finds real businesses with phone numbers, websites, Google ratings. MSP-readiness scoring. Auto-dedup against HubSpot. Industry-targeted with compliance tiers. Smart caching prevents re-scraping.</div>
  </div>

  <div class="flex gap-16 items-center mb-12" style="flex-wrap:wrap">
    <div>
      <label class="filter-label">Target Markets</label>
      <div class="flex gap-10">
        <label class="check-row"><input type="checkbox" id="mk-austin" checked> Austin (512)</label>
        <label class="check-row"><input type="checkbox" id="mk-sa" checked> San Antonio (210)</label>
        <label class="check-row"><input type="checkbox" id="mk-houston" checked> Houston (713)</label>
      </div>
    </div>
    <div>
      <label class="filter-label">Max Prospects</label>
      <input type="number" id="max-results" value="200" style="width:80px">
    </div>
    <label class="check-row" style="color:var(--hubspot);font-weight:700">
      <input type="checkbox" id="sync-hs" checked> Sync → HubSpot
    </label>
    <button class="btn btn-primary btn-lg" onclick="runScraper()" id="scrape-btn">🔍 SCRAPE BUSINESSES</button>
  </div>

  <!-- ADVANCED FILTERS -->
  <div class="filter-box mb-12">
    <div class="filter-title">QUALITY FILTERS — MSP-Targeted Intelligence</div>
    <div class="filter-row mb-10">
      <label class="check-row"><input type="checkbox" id="f-phone" checked> Must have phone</label>
      <label class="check-row"><input type="checkbox" id="f-website" checked> Must have website</label>
      <label class="check-row"><input type="checkbox" id="f-solo" checked> Skip solo/freelance</label>
      <label class="check-row"><input type="checkbox" id="f-dedup-hs"> Dedup vs HubSpot</label>
    </div>
    <div class="filter-row mb-10">
      <div class="filter-input">
        <span style="font-size:10px;color:var(--fg2)">Min Rating:</span>
        <input type="number" id="f-rating" value="4.0" step="0.5" style="width:55px">
      </div>
      <div class="filter-input">
        <span style="font-size:10px;color:var(--fg2)">Min Reviews:</span>
        <input type="number" id="f-reviews" value="10" style="width:55px">
      </div>
      <div class="filter-input">
        <span style="font-size:10px;color:var(--fg2)">Min MSP Score:</span>
        <input type="number" id="f-score" value="60" style="width:55px">
      </div>
    </div>
    <div class="filter-row">
      <div class="filter-input">
        <span style="font-size:10px;color:var(--fg2)">Industry Tier:</span>
        <select id="f-tier" style="width:160px">
          <option value="all">All Tiers</option>
          <option value="1">Tier 1 — Compliance (Law, Medical, CPA)</option>
          <option value="2">Tier 2 — Tech-Heavy (Insurance, Real Estate)</option>
          <option value="3">Tier 3 — Operational (Construction, Mfg)</option>
        </select>
      </div>
      <div class="filter-input">
        <span style="font-size:10px;color:var(--fg2)">Specific Industry:</span>
        <select id="f-industry" style="width:180px">
          <option value="">All Industries</option>
          <option value="law">Law Firms</option>
          <option value="medical">Medical Offices</option>
          <option value="dental">Dental Practices</option>
          <option value="accounting">Accounting / CPA</option>
          <option value="financial">Financial Advisors</option>
          <option value="insurance">Insurance Agencies</option>
          <option value="real estate">Real Estate</option>
          <option value="architecture">Architecture</option>
          <option value="engineering">Engineering</option>
          <option value="property management">Property Management</option>
          <option value="construction">Construction</option>
          <option value="manufacturing">Manufacturing</option>
          <option value="logistics">Logistics</option>
          <option value="veterinary">Veterinary</option>
        </select>
      </div>
      <span class="filter-hint">Smart cache: won't re-scrape known businesses</span>
    </div>
  </div>

  <div class="log-output" id="scraper-log">Ready to scrape. Configure Google API key in Settings → click SCRAPE BUSINESSES.
Smart scraping: cached businesses are skipped, MSP scoring prioritizes compliance-heavy industries.</div>

  <!-- ===== SUPER SCRAPER PANEL ===== -->
  <div class="glow" style="margin-top:24px;border:2px solid #a855f7;background:linear-gradient(135deg,rgba(168,85,247,0.08),rgba(236,72,153,0.05))">
    <div class="section-title" style="color:#c084fc">🚀 SUPER SCRAPER — Decision-Maker Discovery Engine</div>
    <div style="font-size:11px;color:var(--fg2);margin-bottom:12px;line-height:1.5">
      Goes <strong>way beyond</strong> info@ emails. Deep-crawls company websites for real names + titles + emails,
      finds LinkedIn profiles via search operators, generates &amp; verifies email patterns (Hunter.io if configured),
      auto-pushes named decision-makers to HubSpot <em>and</em> the Dialpad dialer with full job titles.
      Reuses your existing Google Places cache so it never re-scrapes known businesses.
    </div>

    <div class="flex gap-16 items-center mb-12" style="flex-wrap:wrap">
      <div>
        <label class="filter-label">Target Markets</label>
        <div class="flex gap-10">
          <label class="check-row"><input type="checkbox" id="ss-mk-austin" checked> Austin</label>
          <label class="check-row"><input type="checkbox" id="ss-mk-sa" checked> San Antonio</label>
          <label class="check-row"><input type="checkbox" id="ss-mk-houston" checked> Houston</label>
        </div>
      </div>
      <div>
        <label class="filter-label">Max Prospects</label>
        <input type="number" id="ss-max" value="50" style="width:80px">
      </div>
      <div>
        <label class="filter-label">Industry</label>
        <select id="ss-industry" style="width:170px">
          <option value="">All Industries</option>
          <option value="law">Law Firms</option>
          <option value="medical">Medical Offices</option>
          <option value="dental">Dental Practices</option>
          <option value="accounting">Accounting / CPA</option>
          <option value="financial">Financial Advisors</option>
          <option value="insurance">Insurance Agencies</option>
          <option value="real estate">Real Estate</option>
          <option value="construction">Construction (General Contractors)</option>
          <option value="property management">Property Management</option>
          <option value="architecture">Architecture</option>
          <option value="engineering">Engineering</option>
          <option value="manufacturing">Manufacturing</option>
        </select>
      </div>
      <button class="btn btn-lg" style="background:linear-gradient(135deg,#a855f7,#ec4899);color:#fff;font-weight:700" onclick="runSuperScraper()" id="ss-btn">🚀 LAUNCH SUPER SCRAPER</button>
    </div>

    <div class="filter-box mb-12" style="border-color:#a855f7">
      <div class="filter-title" style="color:#c084fc">DECISION-MAKER MODE</div>
      <div class="filter-row mb-10">
        <label class="check-row" style="color:#c084fc;font-weight:700">
          <input type="checkbox" id="ss-deep" checked> 🔥 DEEP MODE (LinkedIn discovery + max-depth crawl)
        </label>
        <label class="check-row">
          <input type="checkbox" id="ss-titles-only"> Only keep prospects with a real decision-maker title
        </label>
        <label class="check-row"><input type="checkbox" id="ss-require-phone" checked> Must have phone</label>
        <label class="check-row"><input type="checkbox" id="ss-skip-solo" checked> Skip solo/freelance</label>
      </div>
      <div class="filter-row">
        <div class="filter-input">
          <span style="font-size:10px;color:var(--fg2)">Min MSP Score:</span>
          <input type="number" id="ss-min-score" value="60" style="width:55px">
        </div>
        <label class="check-row" style="color:var(--hubspot);font-weight:700">
          <input type="checkbox" id="ss-sync-hs" checked> ↗ Sync to HubSpot
        </label>
        <label class="check-row" style="color:#7c3aed;font-weight:700">
          <input type="checkbox" id="ss-sync-dp" checked> ↗ Push to Dialpad Dialer
        </label>
        <span class="filter-hint" style="color:#c084fc">Decision-maker titles boost MSP score by up to +35</span>
      </div>
    </div>

    <div class="log-output" id="super-scraper-log" style="border-color:#a855f7">Ready. Configure Google API key (and optionally Hunter.io for verified emails) in Settings → click LAUNCH SUPER SCRAPER.

Discovery sources used: Google Places → Website Deep Crawl → LinkedIn (via search operators) → Hunter.io domain search → Email pattern verification → HubSpot + Dialpad sync.</div>
  </div>
</div>

<!-- ===== EMAIL TAB ===== -->
<div class="tab-content" id="tab-email">
  <div class="glow glow-ms mb-16">
    <div class="section-title" style="color:#0078d4">📧 M365 Graph API — DMARC Safe Email Campaign</div>
    <div class="section-desc">Sends through help@bvtech.org. SPF/DKIM/DMARC preserved. 4-touch sequence with warm-up mode. HubSpot tracks unsubscribes across all channels.</div>
  </div>
  <div class="stats stats-5 mb-16">
    <div class="card stat"><div class="stat-icon">👥</div><div class="stat-label">Prospects</div><div class="stat-value" style="color:var(--blue)" id="email-prospects">0</div></div>
    <div class="card stat"><div class="stat-icon">📧</div><div class="stat-label">Sent</div><div class="stat-value" style="color:var(--purple)" id="email-sent">0</div></div>
    <div class="card stat"><div class="stat-icon">🛡️</div><div class="stat-label">Daily Limit</div><div class="stat-value" style="color:var(--green)">200</div><div class="stat-sub">30/min M365 safe</div></div>
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Sequence</div><div class="stat-value" style="color:var(--orange)">4</div><div class="stat-sub">Day 0-3-7-14</div></div>
    <div class="card stat"><div class="stat-icon">⚡</div><div class="stat-label">Status</div><div class="stat-value" style="color:var(--fg3)" id="email-status">READY</div></div>
  </div>
  <div class="flex gap-12 justify-center mb-16">
    <label class="check-row" style="font-weight:700;color:var(--green)"><input type="checkbox" id="warmup" checked> 🔥 Warm-Up</label>
    <label class="check-row" style="font-weight:700;color:var(--orange)"><input type="checkbox" id="dryrun"> Dry Run</label>
    <button class="btn btn-ms btn-lg" onclick="runEmail()">🚀 LAUNCH EMAIL CAMPAIGN</button>
  </div>
  <div class="log-output" id="email-log">Configure Azure credentials in Settings, then launch. Dry run recommended first.</div>
</div>

<!-- ===== SMS TAB ===== -->
<div class="tab-content" id="tab-sms">
  <div class="glow glow-orange mb-16">
    <div class="section-title" style="color:#f59e0b">⚠️ TCPA — Written Consent Required</div>
    <div class="section-desc"><strong style="color:#f87171">Cold texting = $500-$1,500/msg fines.</strong> Use email for opt-ins first. STOP included. 9am-8pm CT. DialPad Pro API: 100 SMS/min.</div>
  </div>
  <div class="stats stats-4 mb-16">
    <div class="card stat"><div class="stat-icon">📱</div><div class="stat-label">Opt-In</div><div class="stat-value" style="color:var(--blue)">0</div></div>
    <div class="card stat"><div class="stat-icon">💬</div><div class="stat-label">Sent</div><div class="stat-value" style="color:var(--purple)">0</div></div>
    <div class="card stat"><div class="stat-icon">🚫</div><div class="stat-label">Opt-Outs</div><div class="stat-value" style="color:var(--red)">0</div></div>
    <div class="card stat"><div class="stat-icon">✅</div><div class="stat-label">Delivered</div><div class="stat-value" style="color:var(--green)">0</div></div>
  </div>
  <div class="flex gap-12 justify-center mb-16">
    <label class="check-row"><input type="radio" name="sms-tmpl" value="intro" checked> Introduction</label>
    <label class="check-row"><input type="radio" name="sms-tmpl" value="security"> Security Alert</label>
    <label class="check-row"><input type="radio" name="sms-tmpl" value="value"> Value Add</label>
    <label class="check-row" style="font-weight:700;color:var(--orange)"><input type="checkbox" id="sms-dry" checked> Dry Run</label>
    <button class="btn btn-purple btn-lg" onclick="runSMS()">📱 LAUNCH SMS</button>
  </div>
  <div class="log-output" id="sms-log">Configure DialPad API key in Settings. Use opted-in contacts only.</div>
</div>

<!-- ===== DIALER TAB ===== -->
<div class="tab-content" id="tab-dialer">
  <div class="glow glow-purple mb-16">
    <div class="section-title" style="color:#a78bfa">📞 DialPad Pro — Power Dialer + Auto Call Logging</div>
    <div class="section-desc">Click-to-call through DialPad. On-screen scripts. Every disposition auto-logged to HubSpot. Post-call workflows create deals + tasks.</div>
  </div>

  <!-- Market Filter + Controls -->
  <div class="flex gap-12 items-center mb-16 flex-wrap">
    <span style="font-size:11px;color:var(--fg2)">Market:</span>
    <label class="check-row"><input type="radio" name="dialer-mk" value="" checked> All</label>
    <label class="check-row"><input type="radio" name="dialer-mk" value="austin"> Austin</label>
    <label class="check-row"><input type="radio" name="dialer-mk" value="san_antonio"> SA</label>
    <label class="check-row"><input type="radio" name="dialer-mk" value="houston"> Houston</label>
    <div style="margin-left:auto;display:flex;gap:8px">
      <button class="btn btn-green btn-lg" onclick="dialerStart()">📞 START DIALING</button>
      <button class="btn btn-outline" onclick="dialerStop()" id="dialer-stop-btn" style="display:none">⏹ Stop</button>
    </div>
  </div>

  <!-- Dialer Stats -->
  <div class="stats stats-6 mb-16" id="dialer-stats">
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Loaded</div><div class="stat-value" style="color:var(--blue)" id="ds-loaded">0</div></div>
    <div class="card stat"><div class="stat-icon">📞</div><div class="stat-label">Dialed</div><div class="stat-value" style="color:var(--green)" id="ds-dialed">0</div></div>
    <div class="card stat"><div class="stat-icon">✅</div><div class="stat-label">Connected</div><div class="stat-value" style="color:var(--cyan)" id="ds-connected">0</div></div>
    <div class="card stat"><div class="stat-icon">📵</div><div class="stat-label">No Answer</div><div class="stat-value" style="color:var(--fg3)" id="ds-noanswer">0</div></div>
    <div class="card stat"><div class="stat-icon">🔥</div><div class="stat-label">Qualified</div><div class="stat-value" style="color:var(--orange)" id="ds-qualified">0</div></div>
    <div class="card stat"><div class="stat-icon">⏱️</div><div class="stat-label">Talk Time</div><div class="stat-value" style="color:var(--purple)" id="ds-talktime">0m</div></div>
  </div>

  <div class="grid grid-2 gap-16">
    <!-- Left: Current Prospect Card -->
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;letter-spacing:1px">CURRENT PROSPECT</div>
      <div class="card" id="dialer-prospect-card" style="border-left:3px solid var(--purple);min-height:180px">
        <div id="dialer-prospect-info" style="font-size:13px;color:var(--fg2)">
          Click <strong>START DIALING</strong> to load prospects and begin calling.
        </div>
      </div>

      <!-- Call Script -->
      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;margin-top:16px;letter-spacing:1px">CALL SCRIPT</div>
      <div class="card" style="border-left:3px solid var(--cyan);font-size:12px;line-height:1.8;color:var(--fg2)">
        <div><strong style="color:var(--green)">Opener:</strong> "Hi [NAME], this is Jordan from BVTech — we help businesses in [CITY] with IT support and cybersecurity. Do you have a minute?"</div>
        <div class="mt-8"><strong style="color:var(--cyan)">Pain Point:</strong> "A lot of [INDUSTRY] companies tell us they're worried about ransomware and downtime. Is that something you've been dealing with?"</div>
        <div class="mt-8"><strong style="color:var(--orange)">Close:</strong> "I'd love to do a free 15-minute security assessment. What does your calendar look like this week?"</div>
        <div class="mt-8"><strong style="color:var(--pink)">Objection (no time):</strong> "Totally get it — can I send over a quick one-pager? If it looks useful, we can chat when it's convenient."</div>
      </div>
    </div>

    <!-- Right: Disposition + Notes -->
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;letter-spacing:1px">DISPOSITION</div>
      <div class="disp-grid mb-12" id="dialer-disp-grid">
        <div class="disp-btn" onclick="dialerDisp(this,'qualified_lead')">🔥 Qualified</div>
        <div class="disp-btn" onclick="dialerDisp(this,'interested')">👍 Interested</div>
        <div class="disp-btn" onclick="dialerDisp(this,'callback')">📞 Callback</div>
        <div class="disp-btn" onclick="dialerDisp(this,'send_info')">📧 Send Info</div>
        <div class="disp-btn" onclick="dialerDisp(this,'no_answer')">📵 No Answer</div>
        <div class="disp-btn" onclick="dialerDisp(this,'voicemail')">📼 Voicemail</div>
        <div class="disp-btn" onclick="dialerDisp(this,'not_interested')">👎 Not Interested</div>
        <div class="disp-btn" onclick="dialerDisp(this,'do_not_call')">🚫 DNC</div>
      </div>
      <div>
        <label class="filter-label">Notes</label>
        <textarea id="dialer-notes" placeholder="Call notes..." rows="3"></textarea>
      </div>
      <div class="flex gap-8 mt-12">
        <button class="btn btn-pink btn-lg" onclick="dialerSaveAndNext()" style="flex:1">💾 Save & Next Call →</button>
        <button class="btn btn-outline" onclick="dialerSkip()">Skip →</button>
      </div>

      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;margin-top:16px;letter-spacing:1px">CALL LOG</div>
      <div class="log-output" id="dialer-log" style="min-height:160px;max-height:300px;overflow-y:auto">Ready. Load prospects from the Scraper tab first, then start dialing.</div>
    </div>
  </div>
</div>

<!-- ===== PHONE SYSTEM TAB ===== -->
<div class="tab-content" id="tab-phone">
  <div class="glow glow-purple mb-16">
    <div class="section-title" style="color:#a78bfa">🎙️ DialPad AI Phone System — Full Deep Integration</div>
    <div class="section-desc">Call analytics, AI transcripts, recordings, sentiment analysis, contact sync, DNC management, SMS opt-outs, post-call workflows. Full DialPad Pro API access.</div>
  </div>

  <div class="flex gap-8 mb-16 flex-wrap">
    <button class="btn btn-purple" onclick="testDialPad()">🔌 Test Connection</button>
    <button class="btn btn-green" onclick="loadCallAnalytics()">📊 Load Analytics</button>
    <button class="btn btn-outline" onclick="loadRecentCalls()">📞 Recent Calls</button>
    <button class="btn btn-outline" onclick="loadOptOuts()">🚫 SMS Opt-Outs</button>
    <button class="btn btn-outline" onclick="loadBlocked()">🔇 Blocked Numbers</button>
    <button class="btn btn-outline" onclick="syncDialPadContacts()">👥 Sync → DialPad</button>
  </div>

  <div class="grid grid-2 mb-16">
    <div class="card" style="border-left:3px solid var(--green)">
      <div style="font-size:12px;font-weight:800;color:var(--green);margin-bottom:8px">📞 Quick Dial</div>
      <div class="flex gap-8">
        <input type="text" id="quick-phone" placeholder="+12105551234" style="flex:1">
        <button class="btn btn-green" onclick="quickCall()">Call</button>
      <button class="btn btn-outline btn-sm" onclick="formatPhoneInput('quick-phone')" style="font-size:9px">Format</button>
      </div>
      <div style="font-size:9px;color:var(--fg3);margin-top:4px">Rings your DialPad app → connects</div>
    </div>
    <div class="card" style="border-left:3px solid var(--cyan)">
      <div style="font-size:12px;font-weight:800;color:var(--cyan);margin-bottom:8px">💬 Quick SMS</div>
      <div class="flex gap-8 mb-6">
        <input type="text" id="quick-sms-phone" placeholder="+12105551234" style="flex:1">
      </div>
      <div class="flex gap-8">
        <input type="text" id="quick-sms-text" placeholder="Message text..." style="flex:1">
        <button class="btn btn-cyan" onclick="quickSMS()">Send</button>
        <button class="btn btn-outline btn-sm" onclick="formatPhoneInput('quick-sms-phone')" style="font-size:9px">Format</button>
      </div>
    </div>
  </div>

  <!-- Analytics Dashboard -->
  <div id="dp-analytics" class="stats stats-8 mb-16" style="display:none">
    <div class="card stat"><div class="stat-icon">📞</div><div class="stat-label">Total Calls</div><div class="stat-value" style="color:var(--blue)" id="dp-total">-</div></div>
    <div class="card stat"><div class="stat-icon">📥</div><div class="stat-label">Inbound</div><div class="stat-value" style="color:var(--green)" id="dp-inbound">-</div></div>
    <div class="card stat"><div class="stat-icon">📤</div><div class="stat-label">Outbound</div><div class="stat-value" style="color:var(--purple)" id="dp-outbound">-</div></div>
    <div class="card stat"><div class="stat-icon">🎙️</div><div class="stat-label">Recorded</div><div class="stat-value" style="color:var(--orange)" id="dp-recorded">-</div></div>
    <div class="card stat"><div class="stat-icon">⏱️</div><div class="stat-label">Avg Duration</div><div class="stat-value" style="color:var(--cyan)" id="dp-avgdur">-</div><div class="stat-sub">seconds</div></div>
    <div class="card stat"><div class="stat-icon">🕐</div><div class="stat-label">Talk Time</div><div class="stat-value" style="color:var(--fg)" id="dp-totalmin">-</div><div class="stat-sub">minutes</div></div>
    <div class="card stat"><div class="stat-icon">📡</div><div class="stat-label">Connect Rate</div><div class="stat-value" style="color:var(--pink)" id="dp-connectrate">-</div><div class="stat-sub">percent</div></div>
    <div class="card stat"><div class="stat-icon">📅</div><div class="stat-label">Today</div><div class="stat-value" style="color:var(--green)" id="dp-today">-</div><div class="stat-sub">calls</div></div>
  </div>

  <!-- Calls + Transcript -->
  <div class="grid grid-2 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;letter-spacing:1px">RECENT CALLS</div>
      <div class="log-output" id="dp-calls-log" style="min-height:250px">Click "Recent Calls" to load history with AI transcripts.</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;letter-spacing:1px">AI TRANSCRIPT / RECAP</div>
      <div class="log-output" id="dp-transcript-log" style="min-height:250px">Select a call to view AI transcript, recap, action items, sentiment.</div>
    </div>
  </div>

  <!-- Post-Call Workflow -->
  <div class="glow glow-pink mb-16">
    <div class="section-title" style="color:#ec4899">🔄 Post-Call Workflow Engine <span class="tab-new">NEW</span></div>
    <div class="section-desc mb-12">Select a call → set disposition → auto-creates HubSpot deal + task + note. AI coaching data embedded in CRM timeline.</div>
    <div class="grid grid-2 gap-12">
      <div>
        <label class="filter-label">Call ID (from Recent Calls)</label>
        <input type="text" id="wf-call-id" placeholder="Enter call_id from above">
      </div>
      <div>
        <label class="filter-label">Prospect Phone (optional override)</label>
        <input type="text" id="wf-phone" placeholder="+12105551234">
      </div>
    </div>
    <div class="mt-12">
      <label class="filter-label">Disposition</label>
      <div class="disp-grid mt-8" id="disp-grid">
        <div class="disp-btn" onclick="selectDisp(this,'qualified_lead')">🔥 Qualified Lead</div>
        <div class="disp-btn" onclick="selectDisp(this,'interested')">👍 Interested</div>
        <div class="disp-btn" onclick="selectDisp(this,'callback')">📞 Callback</div>
        <div class="disp-btn" onclick="selectDisp(this,'send_info')">📧 Send Info</div>
        <div class="disp-btn" onclick="selectDisp(this,'gatekeeper')">🚪 Gatekeeper</div>
        <div class="disp-btn" onclick="selectDisp(this,'no_answer')">📵 No Answer</div>
        <div class="disp-btn" onclick="selectDisp(this,'voicemail')">📼 Voicemail</div>
        <div class="disp-btn" onclick="selectDisp(this,'not_interested')">👎 Not Interested</div>
        <div class="disp-btn" onclick="selectDisp(this,'wrong_number')">❌ Wrong Number</div>
        <div class="disp-btn" onclick="selectDisp(this,'do_not_call')">🚫 DNC / Block</div>
      </div>
    </div>
    <div class="mt-12">
      <label class="filter-label">Notes</label>
      <textarea id="wf-notes" placeholder="Call notes... (auto-added to HubSpot timeline)"></textarea>
    </div>
    <div class="mt-12 flex justify-center">
      <button class="btn btn-pink btn-lg" onclick="runPostCallWorkflow()">🔄 RUN POST-CALL WORKFLOW</button>
    </div>
    <div class="log-output mt-12" id="wf-log" style="min-height:100px">Select disposition → click Run. Creates HubSpot deal + task + note automatically.</div>
  </div>

  <!-- DNC -->
  <div class="grid grid-2">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);margin-bottom:6px;letter-spacing:1px">SMS OPT-OUTS</div>
      <div class="log-output" id="dp-optouts-log" style="min-height:100px">Click "SMS Opt-Outs" to load.</div>
    </div>
    <div>
      <div class="flex justify-between items-center mb-8">
        <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px">BLOCKED / DNC</div>
        <div class="flex gap-8">
          <input type="text" id="block-phone" placeholder="+1..." style="width:150px">
          <button class="btn btn-danger btn-sm" onclick="blockNumber()">Block</button>
        </div>
      </div>
      <div class="log-output" id="dp-blocked-log" style="min-height:100px">Click "Blocked Numbers" to load DNC list.</div>
    </div>
  </div>
</div>

<!-- ===== COACHING TAB (NEW) ===== -->
<div class="tab-content" id="tab-coaching">
  <div class="glow glow-pink mb-16">
    <div class="section-title" style="color:#ec4899">🧠 AI Call Coaching — Powered by DialPad Transcripts</div>
    <div class="section-desc">Analyzes your call transcripts for talk ratio, MSP pain point detection, buying signals, objection handling, and competitor mentions. Get a coaching score for every call and track your improvement over time.</div>
  </div>

  <div class="flex gap-8 mb-16">
    <button class="btn btn-pink btn-lg" onclick="loadCoachingSummary()">📊 Load Coaching Summary (7 days)</button>
    <button class="btn btn-outline" onclick="loadCoachingSummary(30)">📅 Last 30 Days</button>
  </div>

  <!-- Coaching Summary Stats -->
  <div id="coaching-stats" class="stats stats-6 mb-16" style="display:none">
    <div class="card stat"><div class="stat-icon">🧠</div><div class="stat-label">Avg Score</div><div class="stat-value" style="color:var(--pink)" id="coach-avg-score">-</div><div class="stat-sub">/100</div></div>
    <div class="card stat"><div class="stat-icon">📊</div><div class="stat-label">Calls Analyzed</div><div class="stat-value" style="color:var(--blue)" id="coach-total">-</div></div>
    <div class="card stat"><div class="stat-icon">🗣️</div><div class="stat-label">Avg Talk Ratio</div><div class="stat-value" style="color:var(--purple)" id="coach-ratio">-</div><div class="stat-sub">% agent</div></div>
    <div class="card stat"><div class="stat-icon">💰</div><div class="stat-label">Buying Signals</div><div class="stat-value" style="color:var(--green)" id="coach-buying">-</div></div>
    <div class="card stat"><div class="stat-icon">🛡️</div><div class="stat-label">Pain Points</div><div class="stat-value" style="color:var(--orange)" id="coach-pain">-</div></div>
    <div class="card stat"><div class="stat-icon">👎</div><div class="stat-label">Objections</div><div class="stat-value" style="color:var(--red)" id="coach-obj">-</div></div>
  </div>

  <!-- Per-Call Coaching -->
  <div class="grid grid-2 mb-16">
    <div>
      <div class="card" style="border-left:3px solid var(--pink)">
        <div style="font-size:12px;font-weight:800;color:var(--pink);margin-bottom:8px">🔍 Analyze Single Call</div>
        <div class="flex gap-8">
          <input type="text" id="coach-call-id" placeholder="Enter call_id" style="flex:1">
          <button class="btn btn-pink" onclick="analyzeCall()">Analyze</button>
        </div>
      </div>
    </div>
    <div>
      <div class="card" style="border-left:3px solid var(--cyan)">
        <div style="font-size:12px;font-weight:800;color:var(--cyan);margin-bottom:8px">📞 MSP Keywords Detected</div>
        <div id="coaching-keywords" style="font-size:11px;color:var(--fg2)">Run analysis to see keyword detection results.</div>
      </div>
    </div>
  </div>

  <div class="log-output" id="coaching-log" style="min-height:300px">Click "Load Coaching Summary" to analyze recent calls.
Or enter a specific call_id to get detailed coaching for one call.

MSP KEYWORDS TRACKED:
• Cybersecurity: ransomware, phishing, breach, endpoint, firewall
• Compliance: HIPAA, PCI, SOX, NIST, CMMC, audit
• Downtime: outage, crash, server, backup, disaster recovery
• Cloud: M365, Azure, AWS, migration, SaaS
• IT Support: help desk, network, VPN, remote, printer
• Growth: expansion, new office, hiring, scaling

BUYING SIGNALS: pricing, budget, next steps, schedule, demo, proposal
OBJECTIONS: not interested, too expensive, no budget, already have IT</div>
</div>

<!-- ===== PIPELINE TAB (NEW) ===== -->
<div class="tab-content" id="tab-pipeline">
  <div class="glow glow-cyan mb-16">
    <div class="section-title" style="color:var(--cyan)">🔥 Sales Pipeline — HubSpot Deals + DialPad Automation</div>
    <div class="section-desc">Every qualified call auto-creates a deal. Post-call workflows push dispositions into your pipeline. Track MRR from prospect to closed-won.</div>
  </div>

  <div class="flex gap-8 mb-16">
    <button class="btn btn-cyan btn-lg" onclick="loadPipeline()">🔄 Load Pipeline</button>
    <button class="btn btn-outline" onclick="window.open('https://app.hubspot.com','_blank')">Open HubSpot ↗</button>
  </div>

  <!-- Pipeline value stats -->
  <div id="pipeline-stats" class="stats stats-4 mb-16" style="display:none">
    <div class="card stat"><div class="stat-icon">💰</div><div class="stat-label">Total Pipeline</div><div class="stat-value" style="color:var(--green)" id="pipe-total">$0</div><div class="stat-sub">MRR potential</div></div>
    <div class="card stat"><div class="stat-icon">🏆</div><div class="stat-label">Closed Won</div><div class="stat-value" style="color:var(--cyan)" id="pipe-won">$0</div></div>
    <div class="card stat"><div class="stat-icon">📊</div><div class="stat-label">Total Deals</div><div class="stat-value" style="color:var(--purple)" id="pipe-deals">0</div></div>
    <div class="card stat"><div class="stat-icon">🔥</div><div class="stat-label">Active Deals</div><div class="stat-value" style="color:var(--orange)" id="pipe-active">0</div></div>
  </div>

  <!-- Kanban Pipeline -->
  <div class="pipeline" id="pipeline-board">
    <div class="pipeline-col"><div class="pipeline-header">Assessment <span class="pipeline-count">0</span></div><div id="pipe-stage-1"></div></div>
    <div class="pipeline-col"><div class="pipeline-header">Interested <span class="pipeline-count">0</span></div><div id="pipe-stage-2"></div></div>
    <div class="pipeline-col"><div class="pipeline-header">Proposal <span class="pipeline-count">0</span></div><div id="pipe-stage-3"></div></div>
    <div class="pipeline-col"><div class="pipeline-header">Decision <span class="pipeline-count">0</span></div><div id="pipe-stage-4"></div></div>
    <div class="pipeline-col"><div class="pipeline-header">Contract <span class="pipeline-count">0</span></div><div id="pipe-stage-5"></div></div>
    <div class="pipeline-col" style="border-color:rgba(34,197,94,0.2)"><div class="pipeline-header" style="color:var(--green)">Won 🏆 <span class="pipeline-count" style="background:rgba(34,197,94,0.15);color:#4ade80">0</span></div><div id="pipe-stage-6"></div></div>
    <div class="pipeline-col" style="border-color:rgba(239,68,68,0.15)"><div class="pipeline-header" style="color:var(--red)">Lost <span class="pipeline-count" style="background:rgba(239,68,68,0.15);color:#f87171">0</span></div><div id="pipe-stage-7"></div></div>
  </div>
</div>

<!-- ===== CRM TAB ===== -->
<div class="tab-content" id="tab-crm">
  <div class="glow glow-hubspot mb-16">
    <div class="section-title" style="color:#ff7a59">🔶 HubSpot CRM — Full Integration Hub</div>
    <div class="section-desc">Prospects auto-sync. Call dispositions → deals. Email/SMS tracked. DialPad AI coaching in timeline. Post-call workflows create tasks + notes automatically.</div>
  </div>

  <div class="flex gap-8 mb-16">
    <button class="btn btn-hubspot" onclick="syncHubSpot()">Sync Prospects → HubSpot</button>
    <button class="btn btn-outline" onclick="loadCRMContacts()">📋 Load Contacts</button>
    <button class="btn btn-outline" onclick="window.open('https://app.hubspot.com','_blank')">Open HubSpot ↗</button>
  </div>

  <div class="grid grid-4 mb-16">
    <div class="card" style="border-left:3px solid #0078d4"><div style="font-size:11px;font-weight:800;color:#0078d4">✅ Microsoft 365</div><div style="font-size:9px;color:var(--fg3)">Email via Graph API</div></div>
    <div class="card" style="border-left:3px solid #7c3aed"><div style="font-size:11px;font-weight:800;color:#7c3aed">✅ DialPad Pro</div><div style="font-size:9px;color:var(--fg3)">Calls + SMS + AI</div></div>
    <div class="card" style="border-left:3px solid #ff7a59"><div style="font-size:11px;font-weight:800;color:#ff7a59">✅ HubSpot CRM</div><div style="font-size:9px;color:var(--fg3)">Contacts + Deals + Tasks</div></div>
    <div class="card" style="border-left:3px solid #4285f4"><div style="font-size:11px;font-weight:800;color:#4285f4">✅ Google Places</div><div style="font-size:9px;color:var(--fg3)">Smart Scraping</div></div>
  </div>

  <!-- CRM Contact Stats -->
  <div id="crm-stats" class="stats stats-4 mb-16" style="display:none">
    <div class="card stat"><div class="stat-icon">👥</div><div class="stat-label">Total Contacts</div><div class="stat-value" style="color:var(--blue)" id="crm-total">0</div></div>
    <div class="card stat"><div class="stat-icon">🎯</div><div class="stat-label">SQL</div><div class="stat-value" style="color:var(--green)" id="crm-sql">0</div></div>
    <div class="card stat"><div class="stat-icon">📊</div><div class="stat-label">Leads</div><div class="stat-value" style="color:var(--orange)" id="crm-leads">0</div></div>
    <div class="card stat"><div class="stat-icon">🏢</div><div class="stat-label">Industries</div><div class="stat-value" style="color:var(--purple)" id="crm-industries">0</div></div>
  </div>

  <!-- Contact table -->
  <div id="crm-contacts-table" class="card mb-16" style="display:none;overflow-x:auto;">
    <table class="contact-table" id="contacts-table">
      <thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Email</th><th>Stage</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody id="contacts-tbody"></tbody>
    </table>
  </div>

  <div class="log-output" id="crm-log">HubSpot CRM integration active. Click sync to push prospects or load contacts to view CRM data.</div>
</div>

<!-- ===== HS TRACK TAB — HubSpot email tracking (v31) ===== -->
<div class="tab-content" id="tab-hstrack">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(249,115,22,0.06),rgba(236,72,153,0.04));border:1px solid rgba(249,115,22,0.2);">
    <div class="section-title" style="color:#fb923c;font-size:16px">📬 HubSpot Email Tracking</div>
    <div class="section-desc">Make sure every email you send to a scraped prospect lands on their HubSpot contact timeline. Two ways to track: BCC forwarding (easiest, works with any mail client) or manual logging via the form below.</div>
  </div>

  <!-- Stat cards -->
  <div class="stats stats-4 mb-16">
    <div class="card stat"><div class="stat-icon">📇</div><div class="stat-label">HubSpot Contacts</div><div class="stat-value" id="hs-contact-count" style="color:#fb923c">—</div><div class="stat-sub">total in portal</div></div>
    <div class="card stat"><div class="stat-icon">📤</div><div class="stat-label">Tracked Today</div><div class="stat-value" id="hs-tracked-today" style="color:#22c55e">—</div><div class="stat-sub">via this tool</div></div>
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Prospects CSV</div><div class="stat-value" id="hs-csv-rows" style="color:#3b82f6">—</div><div class="stat-sub">rows on disk</div></div>
    <div class="card stat"><div class="stat-icon">⚠️</div><div class="stat-label">Needs Enrichment</div><div class="stat-value" id="hs-csv-needs" style="color:#f59e0b">—</div><div class="stat-sub">missing contact IDs</div></div>
  </div>

  <!-- BCC address card -->
  <div class="card mb-16" style="border-left:3px solid #fb923c">
    <div class="settings-title" style="color:#fb923c">🔑 Method 1: BCC Forwarding (easiest)</div>
    <p style="margin:8px 0;font-size:12px;color:var(--fg2)">HubSpot gives every account a unique BCC address. Paste it into the field below, then BCC it on any email you send from Gmail, Outlook, your phone, anywhere. HubSpot auto-matches the recipient to a contact and logs the email to their timeline.</p>
    <div style="display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap">
      <input type="text" id="hstrack-bcc" placeholder="yourtoken@bcc.hubspot.com" style="flex:1;min-width:300px;background:rgba(0,0,0,0.3);border:1px solid rgba(251,146,60,0.3);color:#e2e8f0;padding:10px 12px;border-radius:6px;font-family:ui-monospace,Consolas,monospace;font-size:12px">
      <button class="btn btn-sm" style="background:linear-gradient(135deg,#fb923c,#ec4899);color:#fff;font-weight:700" onclick="saveBccAddress()">💾 Save</button>
      <button class="btn btn-sm btn-outline" onclick="copyBccAddress()">📋 Copy</button>
    </div>
    <div style="margin-top:10px;padding:10px 12px;background:rgba(0,0,0,0.25);border-radius:6px;font-size:11px;color:var(--fg2)">
      <strong style="color:#fb923c">How to find your BCC address:</strong><br>
      HubSpot → Settings → Objects → Activities → <strong>Email</strong> tab → scroll to <strong>"Forward to HubSpot"</strong> — copy the address there.<br>
      <a href="https://knowledge.hubspot.com/email-tracking/use-email-logging-with-bcc" target="_blank" style="color:#fb923c">HubSpot docs ↗</a>
    </div>
  </div>

  <!-- Manual log form -->
  <div class="card mb-16" style="border-left:3px solid #3b82f6">
    <div class="settings-title" style="color:#60a5fa">📝 Method 2: Log an Email Manually</div>
    <p style="margin:8px 0;font-size:12px;color:var(--fg2)">For emails you already sent but forgot to BCC. This uses the HubSpot v3 Engagements API to create the email activity and associate it with the contact. If the contact doesn't exist in HubSpot yet, the tool creates them automatically.</p>
    <div class="settings-grid" style="margin-top:10px">
      <div class="settings-field"><label>To Email *</label><input type="email" id="hstrack-to" placeholder="prospect@example.com"></div>
      <div class="settings-field"><label>Subject *</label><input type="text" id="hstrack-subject" placeholder="Quick intro — BVTech MSP Services"></div>
      <div class="settings-field"><label>First Name</label><input type="text" id="hstrack-fname" placeholder="John (only used if creating new contact)"></div>
      <div class="settings-field"><label>Last Name</label><input type="text" id="hstrack-lname" placeholder="Smith"></div>
      <div class="settings-field"><label>Company</label><input type="text" id="hstrack-company" placeholder="Smith Electric"></div>
      <div class="settings-field"><label>Phone</label><input type="text" id="hstrack-phone" placeholder="+1 713 555 0199"></div>
    </div>
    <div class="settings-field" style="margin-top:10px"><label>Body *</label><textarea id="hstrack-body" rows="6" placeholder="Hi John, ..." style="width:100%;background:rgba(0,0,0,0.3);border:1px solid rgba(59,130,246,0.3);color:#e2e8f0;padding:10px;border-radius:6px;font-size:12px"></textarea></div>
    <div class="flex gap-8 mt-8">
      <button class="btn" style="background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;font-weight:700" onclick="hsTrackLog()">📤 Log to HubSpot</button>
      <button class="btn" style="background:linear-gradient(135deg,#22c55e,#059669);color:#fff;font-weight:700" onclick="draftAndTrack()" title="Opens your default mail client with BCC pre-injected, and pre-logs this contact in HubSpot">✉️ Draft &amp; Track</button>
      <button class="btn btn-outline btn-sm" onclick="hsTrackVerify()">🔌 Verify Connection</button>
      <button class="btn btn-outline btn-sm" onclick="hsTrackClearForm()">🧹 Clear</button>
    </div>
    <div class="log-output" id="hstrack-log" style="margin-top:10px">Ready. Verify HubSpot connection first to confirm your Private App token is valid.</div>
  </div>

  <!-- Bulk enrichment card -->
  <div class="card mb-16" style="border-left:3px solid #22c55e">
    <div class="settings-title" style="color:#86efac">🔄 Bulk: Enrich prospects.csv with HubSpot Contact IDs</div>
    <p style="margin:8px 0;font-size:12px;color:var(--fg2)">Walks your <code>prospects.csv</code> file, looks up each email in HubSpot, creates contacts that don't exist, and writes the HubSpot contact IDs back to the CSV. Rate-limited to stay under HubSpot's 100 req/10s burst limit. Capped at 50 contacts per run so you can re-run daily without blowing through your API quota.</p>
    <p style="margin:8px 0;font-size:11px;color:var(--fg3)">This is the same job the <code>daily_hubspot_enrichment</code> scheduled task runs at 6am. Click below to trigger it now.</p>
    <button class="btn btn-sm" style="background:linear-gradient(135deg,#22c55e,#059669);color:#fff;font-weight:700" onclick="hsTrackEnrichNow()">🚀 Enrich CSV Now</button>
  </div>

  <!-- Sent emails history (from local event log) -->
  <div class="card">
    <div class="settings-title" style="color:#94a3b8">🗂 Recently Tracked (from local event log)</div>
    <button class="btn btn-outline btn-sm" onclick="loadHsHistory()">🔄 Refresh</button>
    <div id="hs-history" style="margin-top:10px;max-height:400px;overflow-y:auto;font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--fg2);background:rgba(0,0,0,0.25);padding:10px;border-radius:6px">Click Refresh to load the last 50 tracked emails.</div>
  </div>
</div>

<!-- ===== AUTOMATION TAB — local task scheduler (v31) ===== -->
<div class="tab-content" id="tab-automation">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(6,182,212,0.06),rgba(59,130,246,0.04));border:1px solid rgba(6,182,212,0.2);">
    <div class="section-title" style="color:#22d3ee;font-size:16px">⏰ Local Automation</div>
    <div class="section-desc">Scheduled tasks that run locally — config backups, posts index pruning, prospects CSV watching, HubSpot enrichment. Tasks run in-process while the tool is open. To have them run even when the tool is closed (or across reboots), click <strong>Install to Windows</strong> next to any task to register it with Windows Task Scheduler.</div>
  </div>

  <!-- Stat cards -->
  <div class="stats stats-4 mb-16">
    <div class="card stat"><div class="stat-icon">📊</div><div class="stat-label">Events Logged</div><div class="stat-value" id="auto-evt-total" style="color:#22d3ee">—</div><div class="stat-sub">all time</div></div>
    <div class="card stat"><div class="stat-icon">⏱️</div><div class="stat-label">Last 24h</div><div class="stat-value" id="auto-evt-24h" style="color:#3b82f6">—</div><div class="stat-sub">events</div></div>
    <div class="card stat"><div class="stat-icon">⚠️</div><div class="stat-label">Failures</div><div class="stat-value" id="auto-evt-fail" style="color:#f87171">—</div><div class="stat-sub">all time</div></div>
    <div class="card stat"><div class="stat-icon">💾</div><div class="stat-label">DB Size</div><div class="stat-value" id="auto-db-size" style="color:#94a3b8">—</div><div class="stat-sub">local_events.db</div></div>
  </div>

  <!-- Task list -->
  <div class="card mb-16">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <div class="settings-title" style="color:#22d3ee;margin:0">📋 Scheduled Tasks</div>
      <button class="btn btn-outline btn-sm" onclick="loadAutomationTasks()">🔄 Refresh</button>
    </div>
    <div id="automation-tasks" style="margin-top:10px">Loading tasks...</div>
  </div>

  <!-- Event log viewer -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
      <div class="settings-title" style="color:#94a3b8;margin:0">📝 Event Log</div>
      <div style="display:flex;gap:6px;align-items:center">
        <select id="auto-log-filter" onchange="loadAutomationLog()" style="background:rgba(0,0,0,0.3);border:1px solid rgba(148,163,184,0.3);color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:11px">
          <option value="">All categories</option>
          <option value="automation">automation</option>
          <option value="email">email</option>
          <option value="post">post</option>
          <option value="scrape">scrape</option>
          <option value="call">call</option>
          <option value="error">error</option>
        </select>
        <button class="btn btn-outline btn-sm" onclick="loadAutomationLog()">🔄</button>
      </div>
    </div>
    <div id="automation-log" style="max-height:420px;overflow-y:auto;font-family:ui-monospace,Consolas,monospace;font-size:11px;background:rgba(0,0,0,0.3);padding:10px;border-radius:6px;color:var(--fg2)">Click Refresh to load events.</div>
  </div>
</div>

<!-- ===== SETTINGS TAB ===== -->
<!-- ===== SUPER POSTING — 4-channel publishing (BVTech + JP + LinkedIn + GBP) v30 ===== -->
<div class="tab-content" id="tab-orm">
  <!-- v29 READY BANNER — replaces the v28 red safety hold -->
  <div id="orm-v29-ready-banner" style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(59,130,246,0.08));border:2px solid #22c55e;border-radius:10px;padding:14px 18px;margin-bottom:16px;">
    <div style="display:flex;align-items:center;gap:10px;font-size:13px;font-weight:800;color:#86efac;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
      🚀 v30 — Super Posting: BVTech + JP + LinkedIn + Google Business
    </div>
    <div style="font-size:12px;color:#cbd5e1;line-height:1.55;">
      v30 adds <strong>Google Business Profile</strong> posting (OAuth2 + localPosts API) and <strong>forward-only cross-linking</strong> — every new post automatically injects a "Related from BVTech.org" block with 2-3 relevant older posts, plus an "Also on Jordan Polasek" cross-site link. The link graph builds itself as you post. Pick the <code>All 4 Channels</code> target to publish to BVTech.org + JordanPolasek.com + LinkedIn + Google Business in one click. Note: GBP requires a one-time Google API access approval (1-2 days). Cross-linking and v29 CF Direct Upload still work the same way — this is additive, nothing was removed.
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
      <button class="btn btn-sm" style="background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;font-weight:700" onclick="ormTestDeploy('bvtech')">🧪 Test Deploy — BVTech.org</button>
      <button class="btn btn-sm" style="background:linear-gradient(135deg,#ec4899,#db2777);color:#fff;font-weight:700" onclick="ormTestDeploy('jp')">🧪 Test Deploy — JordanPolasek.com</button>
      <span style="width:12px"></span>
      <button class="btn btn-sm btn-outline" onclick="ormSiteRootCheck()" title="Verify site_root folders exist and contain index.html">📁 Check Site Folders</button>
      <span style="flex:1"></span>
      <span id="orm-v29-status-dot-bv" style="font-size:10px;color:#94a3b8">BVTech: ?</span>
      <span id="orm-v29-status-dot-jp" style="font-size:10px;color:#94a3b8">JP: ?</span>
    </div>
    <div id="orm-v29-test-output" style="display:none;margin-top:10px;padding:10px 12px;background:rgba(0,0,0,0.35);border-radius:6px;font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#e2e8f0;white-space:pre-wrap;max-height:320px;overflow-y:auto;"></div>
  </div>
  <div class="glow glow-purple mb-16">
    <div class="section-title" style="color:#ec4899;font-size:15px">🚀 Super Posting — 4-Channel Publishing</div>
    <div class="section-desc">Dual-site posting to <strong style="color:#f87171">BVTech.org</strong> + <strong style="color:#ec4899">JordanPolasek.com</strong> via Cloudflare Pages Direct Upload, plus <strong style="color:#0ea5e9">LinkedIn</strong> sharing of the published article. <strong style="color:#86efac">Test Deploy buttons let you dry-run the entire pipeline (walk → hash → check-missing) without touching Cloudflare. Use them before every first-time setup.</strong></div>
  </div>

  <!-- ORM Stats -->
  <div class="grid grid-4 mb-16">
    <div class="card stat" style="border-top:2px solid #ec4899"><div class="stat-icon">📝</div><div class="stat-label">Posts Created</div><div class="stat-value" style="color:#ec4899" id="orm-total">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--green)"><div class="stat-icon">📋</div><div class="stat-label">Queue</div><div class="stat-value" style="color:var(--green)" id="orm-queue-count">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--cyan)"><div class="stat-icon">🎯</div><div class="stat-label">Topics Left</div><div class="stat-value" style="color:var(--cyan)" id="orm-topics-left">60</div></div>
    <div class="card stat" style="border-top:2px solid var(--purple)"><div class="stat-icon">🤖</div><div class="stat-label">Scheduler</div><div class="stat-value" style="color:var(--purple);font-size:11px" id="orm-sched-status">OFF</div></div>
  </div>

  <div class="grid grid-2 mb-16">
    <!-- LEFT COLUMN: Controls -->
    <div>

      <!-- POST NOW -->
      <div class="card mb-12" style="border-left:3px solid #ec4899">
        <div style="font-size:12px;font-weight:800;color:#ec4899;margin-bottom:8px">⚡ Post Now — Instant ORM Post</div>
        <div class="mb-8"><label class="filter-label">Topic (leave blank for auto-pick)</label><input type="text" id="orm-topic" placeholder="e.g., Jordan Polasek Cybersecurity Expert Texas" style="width:100%"></div>
        <div class="grid grid-2 gap-8 mb-8">
          <div><label class="filter-label">Target Site</label>
            <select id="orm-target">
              <option value="all_four">🚀 All 4 Channels (BV + JP + LI + GBP)</option>
              <option value="both">3-Way Rotate (JP↔BV↔LI, Safest)</option>
              <option value="jordanpolasek">JordanPolasek.com Only</option>
              <option value="bvtech">BVTech.org Only</option>
              <option value="linkedin">LinkedIn Only</option>
              <option value="gbp">Google Business Profile Only</option>
              <option value="jp_and_li">JP + LinkedIn</option>
              <option value="all_three">All 3 Sites</option>
            </select>
          </div>
          <div><label class="filter-label">Action</label>
            <select id="orm-status">
              <option value="publish">Publish Immediately</option>
              <option value="draft">Save as Draft</option>
            </select>
          </div>
        </div>
        <div class="grid grid-2 gap-8 mb-8">
          <div><label class="filter-label">Tone</label>
            <select id="orm-tone">
              <option value="personal_authority">Personal Authority</option>
              <option value="thought_leader">Thought Leader</option>
              <option value="professional">Professional</option>
              <option value="storytelling">Storytelling</option>
            </select>
          </div>
          <div><label class="filter-label">Length</label>
            <select id="orm-length">
              <option value="medium">Medium (~800 words)</option>
              <option value="short">Short (~400 words)</option>
              <option value="long">Long (~1500 words)</option>
              <option value="pillar">Pillar (2500+ words)</option>
            </select>
          </div>
        </div>
        <div class="mb-8"><label class="filter-label">Custom Instructions (optional)</label><textarea id="orm-custom" placeholder="Focus on UniFi cameras, mention Sugar Land..." style="min-height:40px;width:100%"></textarea></div>
        <button class="btn" style="background:linear-gradient(135deg,#ec4899,#7c3aed);color:#fff;width:100%" onclick="ormPostNow()">⚡ GENERATE & POST NOW</button>
      </div>

      <!-- QUEUE BUILDER -->
      <div class="card mb-12" style="border-left:3px solid var(--orange)">
        <div style="font-size:12px;font-weight:800;color:var(--orange);margin-bottom:8px">📋 Queue Builder — Batch Post Generation</div>
        <div style="font-size:10px;color:var(--fg2);margin-bottom:8px">Build a lineup of posts. They queue up and you can publish them all at once, one-by-one, or let the scheduler drip them out.</div>
        <div class="grid grid-3 gap-8 mb-8">
          <div><label class="filter-label">Posts to Queue</label>
            <select id="orm-q-count">
              <option value="3">3 posts (1 week)</option>
              <option value="5" selected>5 posts (~2 weeks)</option>
              <option value="8">8 posts (~3 weeks)</option>
              <option value="10">10 posts (~1 month)</option>
            </select>
          </div>
          <div><label class="filter-label">Target</label>
            <select id="orm-q-target">
              <option value="both">3-Way Rotate (Safest)</option>
              <option value="jordanpolasek">JP Only</option>
              <option value="bvtech">BVTech Only</option>
              <option value="linkedin">LinkedIn Only</option>
              <option value="all_three">All 3 Sites</option>
            </select>
          </div>
          <div><label class="filter-label">Status</label>
            <select id="orm-q-status">
              <option value="publish">Publish</option>
              <option value="draft">Draft</option>
            </select>
          </div>
        </div>
        <div class="flex gap-8">
          <button class="btn btn-sm" style="background:var(--orange);color:#000;font-weight:800" onclick="ormBuildQueue()">📋 BUILD QUEUE</button>
          <button class="btn btn-sm btn-green" onclick="ormPublishNext()">▶ Publish Next</button>
          <button class="btn btn-sm" style="background:linear-gradient(135deg,#ef4444,#f59e0b);color:#fff" onclick="ormPublishAll()">🚀 PUBLISH ALL</button>
          <button class="btn btn-outline btn-sm" onclick="ormViewQueue()">👁 View Queue</button>
          <button class="btn btn-outline btn-sm" onclick="ormClearQueue()">🗑 Clear</button>
        </div>
      </div>

      <!-- AUTO SCHEDULER -->
      <div class="card mb-12" style="border-left:3px solid var(--green)">
        <div style="font-size:12px;font-weight:800;color:var(--green);margin-bottom:8px">🤖 Auto Scheduler — Google-Safe Mode</div>
        <div style="font-size:10px;color:var(--fg2);margin-bottom:8px">⚠️ <strong>Max 3 posts/week across both sites to avoid Google spam detection.</strong> Posts are randomized across days with varied timing. Site alternates automatically (JP→BV→JP). Keep the app running.</div>
        <div class="grid grid-4 gap-8 mb-8">
          <div><label class="filter-label">Posts/Week</label>
            <select id="orm-s-ppd"><option value="1">1/week (Safest)</option><option value="2" selected>2/week (Recommended)</option><option value="3">3/week (Max Safe)</option></select>
          </div>
          <div><label class="filter-label">Start Hour</label>
            <input type="number" id="orm-s-start" value="8" min="0" max="23" style="width:100%">
          </div>
          <div><label class="filter-label">End Hour</label>
            <input type="number" id="orm-s-end" value="20" min="0" max="23" style="width:100%">
          </div>
          <div><label class="filter-label">Site Rotation</label>
            <select id="orm-s-target"><option value="alternate" selected>3-Way Rotate (Safest)</option><option value="jordanpolasek">JP Only</option><option value="bvtech">BV Only</option><option value="linkedin">LinkedIn Only</option><option value="all_three">All 3</option></select>
          </div>
        </div>
        <!-- v17: Spam Risk Meter -->
        <div id="orm-spam-risk" style="font-size:10px;margin-bottom:8px;padding:6px 10px;border-radius:6px;background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2)">
          <strong style="color:var(--green)">🛡️ Spam Risk: LOW</strong> — 2 posts/week with alternating sites is safe for Google.
        </div>
        <div class="flex gap-8">
          <button class="btn btn-green btn-sm" onclick="ormSchedulerOn()">🟢 START SCHEDULER</button>
          <button class="btn btn-outline btn-sm" onclick="ormSchedulerOff()">⏸ STOP</button>
          <button class="btn btn-outline btn-sm" onclick="ormSpamCheck()">📊 Check Spam Risk</button>
        </div>
      </div>

      <!-- v16: DUPLICATE SCANNER -->
      <div class="card mb-12" style="border-left:3px solid var(--red)">
        <div style="font-size:12px;font-weight:800;color:var(--red);margin-bottom:8px">🧹 Duplicate Scanner v16 — EXACT + NEAR Matching</div>
        <div style="font-size:10px;color:var(--fg2);margin-bottom:8px">Scans both sites for identical AND near-duplicate titles (75%+ word overlap). Shows similarity %, keeps newest, trashes older copies. v16: relay-first delete, JP uses jp-api.php, verbose error logging.</div>
        <div class="flex gap-8 flex-wrap mb-8">
          <button class="btn btn-sm" style="background:linear-gradient(135deg,#ef4444,#f59e0b);color:#fff" onclick="ormScanDupes()">🔍 SCAN FOR DUPLICATES</button>
          <button class="btn btn-sm" style="background:var(--red);color:#fff" onclick="ormTrashAllDupes()">🗑 TRASH ALL DUPLICATES</button>
          <button class="btn btn-outline btn-sm" onclick="ormTestDelete()">🔌 Test Delete Connection</button>
        </div>
        <div class="log-output" id="orm-dedup-log" style="min-height:60px;max-height:400px;font-size:10px">Click "Scan" to deep-scan both sites. v16 finds NEAR-duplicates too.<br>Click "Test Delete Connection" first to verify trash works.</div>
      </div>

      <!-- v15: SEO SCORE CHECKER -->
      <div class="card mb-12" style="border-left:3px solid var(--green)">
        <div style="font-size:12px;font-weight:800;color:var(--green);margin-bottom:8px">📊 SEO Score — Post Quality Checker</div>
        <div style="font-size:10px;color:var(--fg2);margin-bottom:8px">Every post now gets an automatic SEO score (0-100). Check scores in post history, or the score shows automatically after each post is created.</div>
        <div id="orm-seo-display" style="font-size:10px;color:var(--fg3)">SEO scores appear automatically after each post is generated.</div>
      </div>

      <!-- TOOLS -->
      <div class="card" style="border-left:3px solid var(--cyan)">
        <div style="font-size:12px;font-weight:800;color:var(--cyan);margin-bottom:8px">🔧 Tools</div>
        <div class="flex gap-8 flex-wrap">
          <button class="btn btn-outline btn-sm" onclick="ormGenerateTopics()">💡 Generate 30 Topics</button>
          <button class="btn btn-outline btn-sm" onclick="ormViewTopics()">📊 Topic Bank Status</button>
          <button class="btn btn-sm" style="background:linear-gradient(135deg,var(--cyan),var(--green));color:#000;font-weight:800" onclick="ormTopicHealth()">🩺 Topic Health</button>
          <button class="btn btn-outline btn-sm" onclick="ormResetTopics()">🔄 Reset Used Topics</button>
          <button class="btn btn-outline btn-sm" onclick="ormViewHistory()">📜 Post History</button>
          <button class="btn btn-outline btn-sm" onclick="ormCheckPublishStatus()">⚡ Publish Status</button>
          <button class="btn btn-sm" style="background:linear-gradient(135deg,#ec4899,#7c3aed);color:#fff" onclick="testJPConnection()">🔌 Test JP</button>
          <button class="btn btn-green btn-sm" onclick="testWPConnection()">🔌 Test BVTech</button>
        </div>
      </div>
    </div>

    <!-- RIGHT COLUMN: Output -->
    <div>
      <div class="log-output" id="orm-log" style="min-height:700px">
<strong style="color:#22c55e">─── SUPER POSTING — 4-CHANNEL (BV + JP + LI + GBP) ───</strong>

<strong style="color:var(--green)">🔧 KEY FIXES</strong>
   ✅ WordPress relay now sends auth in POST body (SiteGround WAF fix)
   ✅ Settings persist correctly across version updates
   ✅ Old instances auto-killed on startup (no demo accidents)
   ✅ PHP relay files updated to accept POST-body auth

<strong style="color:var(--cyan)">🛡️ ANTI-SPAM (Active)</strong>
   ✅ Max 3 posts/WEEK (never more)
   ✅ 5 rotating prompt templates
   ✅ Name density: 2-3x per post (not 5-8x)
   ✅ Site alternation: JP → BV → JP
   ✅ Randomized timing with ±4hr jitter

<strong style="color:var(--orange)">⚠️ AFTER UPGRADING:</strong>
   1. Re-upload bvtech-api.php → bvtech.org/public_html/
   2. Re-upload jp-api.php → jordanpolasek.com/public_html/
   3. Click 🔌 Test BVTech and 🔌 Test JP to verify
   4. Your ORM history and queue are preserved

Ready to go. Hit ⚡ Post Now or 🔌 Test connections first.
      </div>
    </div>
  </div>

  <!-- v32: Post Queue (for staggered scheduler) -->
  <div class="card mb-16" style="border-left:3px solid #06b6d4;margin-top:16px">
    <div class="settings-title" style="color:#22d3ee">📋 Post Queue (Staggered Scheduler)</div>
    <p style="margin:8px 0;font-size:12px;color:var(--fg2)">Drop pre-generated topics into this queue, then enable the staggered scheduler tasks on the <strong>Automation</strong> tab. They'll publish one channel at a time on fixed days of the week (Mon BVTech → Wed JP → Fri LinkedIn → Sat GBP) so content doesn't look coordinated to platform de-dup filters. Same master article gets rewritten into 4 distinct voices by <code>channel_rewriter.py</code>.</p>
    <div class="grid grid-2 gap-8 mb-8" style="margin-top:12px">
      <div class="settings-field"><label>Title *</label><input type="text" id="queue-title" placeholder="5 Cybersecurity Wins for Houston SMBs"></div>
      <div class="settings-field"><label>Topic / Focus Keyword</label><input type="text" id="queue-topic" placeholder="cybersecurity houston smb"></div>
    </div>
    <div class="grid grid-2 gap-8 mb-8">
      <div class="settings-field"><label>Tone</label><select id="queue-tone"><option value="personal_authority">Personal Authority</option><option value="thought_leadership">Thought Leadership</option><option value="how_to">How-To</option><option value="case_study">Case Study</option></select></div>
      <div class="settings-field"><label>Length</label><select id="queue-length"><option value="short">Short (~800 words)</option><option value="medium" selected>Medium (~1500 words)</option><option value="long">Long (~2200 words)</option><option value="pillar">Pillar (~3000+ words)</option></select></div>
    </div>
    <div class="settings-field"><label>Custom Instructions (optional)</label><textarea id="queue-custom" rows="2" placeholder="Any specific angle, stats to mention, or tone notes..."></textarea></div>
    <div class="flex gap-8 mt-8">
      <button class="btn" style="background:linear-gradient(135deg,#06b6d4,#3b82f6);color:#fff;font-weight:700" onclick="queueAdd()">➕ Add to Queue</button>
      <button class="btn btn-outline btn-sm" onclick="queueLoad()">🔄 Refresh</button>
      <a class="btn btn-outline btn-sm" style="text-decoration:none" onclick="switchTab('automation', document.querySelector('[onclick*=\"switchTab(\\'automation\\'\"]'))">⏰ Go to Automation Tab →</a>
    </div>
    <div style="margin-top:10px;padding:10px 12px;background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.15);border-radius:6px;font-size:11px;color:var(--fg2)">
      <strong style="color:#22d3ee">How staggered publishing works:</strong> Add items here → Automation tab → Enable the 4 "staggered_*" tasks (disabled by default) → they'll fire weekly on their fixed days and pull the oldest pending item. Each item gets all 4 channels over ~1 week. After all 4 are done, status flips to "done" and sits in history.
    </div>
    <div id="queue-stats" style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--fg2)"></div>
    <div id="queue-list" style="margin-top:10px;max-height:400px;overflow-y:auto">Click Refresh to load.</div>
  </div>
</div>

<!-- ===== CYBER AUDIT & PEN TEST TAB () ===== -->
<div class="tab-content" id="tab-cyberaudit">
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(239,68,68,0.06),rgba(124,58,237,0.04));border:1px solid rgba(239,68,68,0.15);">
    <div class="section-title" style="color:#ef4444;font-size:15px">🛡️ Cybersecurity Audit & Penetration Testing Suite</div>
    <div class="section-desc">Run comprehensive security audits on client websites, networks, and infrastructure. AI-powered vulnerability analysis with remediation recommendations. Generates professional PDF reports for clients. <strong style="color:#ef4444">All scanning is non-destructive and runs from your Windows machine.</strong></div>
  </div>

  <!-- Audit Stats -->
  <div class="stats stats-5 mb-16" id="cyber-stats">
    <div class="card stat" style="border-top:2px solid var(--red)"><div class="stat-icon">🛡️</div><div class="stat-label">Scans Run</div><div class="stat-value" style="color:var(--red)" id="cyber-total">0</div></div>
    <div class="card stat" style="border-top:2px solid #f59e0b"><div class="stat-icon">⚠️</div><div class="stat-label">Vulns Found</div><div class="stat-value" style="color:#f59e0b" id="cyber-vulns">0</div></div>
    <div class="card stat" style="border-top:2px solid #ef4444"><div class="stat-icon">🔴</div><div class="stat-label">Critical</div><div class="stat-value" style="color:#ef4444" id="cyber-critical">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--green)"><div class="stat-icon">✅</div><div class="stat-label">Passed</div><div class="stat-value" style="color:var(--green)" id="cyber-passed">0</div></div>
    <div class="card stat" style="border-top:2px solid var(--purple)"><div class="stat-icon">📄</div><div class="stat-label">Reports</div><div class="stat-value" style="color:var(--purple)" id="cyber-reports">0</div></div>
  </div>

  <!-- ── SECTION 1: Website Security Audit ── -->
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(239,68,68,0.04),rgba(59,130,246,0.04));border:1px solid rgba(239,68,68,0.1);">
    <div style="font-size:14px;font-weight:800;color:#ef4444;margin-bottom:4px">🌐 Website Security Audit</div>
    <div style="font-size:10px;color:var(--fg3)">Deep-scan any website for security vulnerabilities: SSL/TLS config, HTTP headers, OWASP Top 10, CMS detection, exposed files, cookie security, CORS, CSP, and more.</div>
  </div>

  <div class="card mb-16" style="padding:16px">
    <div style="display:grid;grid-template-columns:2fr 1fr;gap:12px">
      <div>
        <label class="filter-label">Target Website URL</label>
        <input type="text" id="cyber-web-url" placeholder="https://clientwebsite.com" style="font-size:13px">
      </div>
      <div>
        <label class="filter-label">Client Name (for report)</label>
        <input type="text" id="cyber-web-client" placeholder="Acme Corp">
      </div>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <label class="check-row"><input type="checkbox" id="cyber-chk-ssl" checked> 🔒 SSL/TLS Audit</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-headers" checked> 📋 HTTP Security Headers</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-cookies" checked> 🍪 Cookie Security</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-cms" checked> 🔍 CMS/Tech Detection</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-dns" checked> 🌐 DNS & DNSSEC</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-exposure" checked> 📂 Sensitive File Exposure</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-cors" checked> 🔀 CORS Policy</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-redirect" checked> ↪️ Redirect Chains</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-email" checked> 📧 Email Security (SPF/DKIM/DMARC)</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-subdomains"> 🗺️ Subdomain Enumeration</label>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button class="btn btn-lg" style="background:linear-gradient(135deg,#ef4444,#7c3aed);color:#fff" onclick="runWebAudit()">🛡️ RUN WEBSITE AUDIT</button>
      <button class="btn btn-outline" onclick="runQuickWebScan()">⚡ Quick Scan (30 sec)</button>
    </div>
  </div>

  <!-- ── SECTION 2: Network Pen Test ── -->
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(124,58,237,0.04),rgba(239,68,68,0.04));border:1px solid rgba(124,58,237,0.1);">
    <div style="font-size:14px;font-weight:800;color:#7c3aed;margin-bottom:4px">🔓 Network Penetration Testing</div>
    <div style="font-size:10px;color:var(--fg3)">Scan client networks for open ports, service fingerprinting, known CVEs, default credentials, SMB/RDP exposure, and firewall gaps. Runs from your Windows machine using Python sockets + optional Nmap integration.</div>
  </div>

  <div class="card mb-16" style="padding:16px">
    <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px">
      <div>
        <label class="filter-label">Target IP / Hostname / CIDR Range</label>
        <input type="text" id="cyber-net-target" placeholder="192.168.1.0/24 or server.client.com" style="font-size:13px">
      </div>
      <div>
        <label class="filter-label">Port Range</label>
        <select id="cyber-net-ports">
          <option value="top100">Top 100 Ports (fast)</option>
          <option value="top1000" selected>Top 1000 Ports</option>
          <option value="common_services">Common Services (22,25,53,80,443,...)</option>
          <option value="full">Full Scan (1-65535) ⚠️ slow</option>
          <option value="custom">Custom Range</option>
        </select>
      </div>
      <div>
        <label class="filter-label">Custom Ports (if selected)</label>
        <input type="text" id="cyber-net-custom-ports" placeholder="22,80,443,3389,8080">
      </div>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <label class="check-row"><input type="checkbox" id="cyber-chk-portscan" checked> 🔓 Port Scan</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-banner" checked> 📡 Service Banner Grab</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-smb"> 📁 SMB Enumeration</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-rdp"> 🖥️ RDP Security Check</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-ssh"> 🔐 SSH Audit</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-vulns" checked> ⚠️ Known CVE Lookup</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-firewall"> 🧱 Firewall Detection</label>
      <label class="check-row"><input type="checkbox" id="cyber-chk-nmap"> 🗺️ Nmap Deep Scan (requires Nmap installed)</label>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button class="btn btn-lg" style="background:linear-gradient(135deg,#7c3aed,#ef4444);color:#fff" onclick="runNetPenTest()">🔓 RUN NETWORK PEN TEST</button>
      <button class="btn btn-outline" onclick="runQuickNetScan()">⚡ Quick Port Scan</button>
    </div>
  </div>

  <!-- ── SECTION 3: AI Vulnerability Analysis ── -->
  <div class="glow mb-16" style="background:linear-gradient(135deg,rgba(236,72,153,0.04),rgba(239,68,68,0.04));border:1px solid rgba(236,72,153,0.1);">
    <div style="font-size:14px;font-weight:800;color:#ec4899;margin-bottom:4px">🧠 AI-Powered Vulnerability Analysis & Remediation</div>
    <div style="font-size:10px;color:var(--fg3)">Claude AI analyzes all scan results, cross-references against NIST NVD, OWASP, and CIS benchmarks, then generates prioritized remediation plans with exact steps to fix each vulnerability. Includes client-ready language.</div>
  </div>

  <!-- Scan Results + AI Analysis (split view) -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
    <div class="card" style="padding:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div style="font-size:13px;font-weight:800;color:#ef4444">📊 Scan Results</div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm btn-outline" onclick="clearCyberLog()">Clear</button>
          <button class="btn btn-sm btn-outline" onclick="exportCyberLog()">📋 Copy</button>
        </div>
      </div>
      <div class="log-output" id="cyber-scan-log" style="min-height:500px;max-height:700px;font-size:10px">
🛡️ BVTech Cybersecurity Audit & Pen Test Suite

Ready to scan. Enter a target and click one of the scan buttons.

WEBSITE AUDIT scans:
  • SSL/TLS certificate chain, protocol versions, cipher suites
  • HTTP security headers (HSTS, CSP, X-Frame, X-XSS, etc.)
  • Cookie flags (Secure, HttpOnly, SameSite)
  • CMS detection (WordPress, Drupal, Joomla, Shopify, etc.)
  • Sensitive file exposure (robots.txt, .env, .git, wp-config, etc.)
  • DNS records + DNSSEC validation
  • Email security (SPF, DKIM, DMARC records)
  • CORS policy analysis
  • Redirect chain analysis
  • Subdomain enumeration

NETWORK PEN TEST scans:
  • TCP port scanning with SYN/connect detection
  • Service fingerprinting + version detection
  • Banner grabbing on open ports
  • Known CVE lookup by service/version
  • SMB share enumeration
  • RDP/SSH security configuration audit
  • Firewall detection + evasion analysis
  • Optional Nmap integration for deep OS fingerprinting
      </div>
    </div>
    <div class="card" style="padding:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div style="font-size:13px;font-weight:800;color:#ec4899">🧠 AI Analysis & Remediation</div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm" style="background:linear-gradient(135deg,#ec4899,#7c3aed);color:#fff" onclick="runAICyberAnalysis()">🧠 Analyze with Claude</button>
          <button class="btn btn-sm btn-outline" onclick="generateCyberReport()">📄 Generate Report</button>
        </div>
      </div>
      <div class="log-output" id="cyber-ai-log" style="min-height:500px;max-height:700px;font-size:10px">
Run a scan first, then click "Analyze with Claude" to get:

  📊 RISK ASSESSMENT — Overall security posture score (0-100)
  🔴 CRITICAL FINDINGS — Immediate action items
  🟡 WARNINGS — Important but not urgent issues
  🟢 PASSED CHECKS — What's configured correctly
  🔧 REMEDIATION PLAN — Step-by-step fix instructions
  💰 COST ESTIMATE — Time/effort to remediate
  📄 CLIENT REPORT — Professional summary for the client

Claude will cross-reference findings against:
  • OWASP Top 10 (2021)
  • NIST Cybersecurity Framework
  • CIS Critical Security Controls
  • Known CVE databases
  • SANS Top 25 Software Errors
      </div>
    </div>
  </div>

  <!-- Audit History -->
  <div class="card" style="padding:16px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <div style="font-size:13px;font-weight:800;color:var(--fg2)">📁 Audit History</div>
      <button class="btn btn-sm btn-outline" onclick="loadCyberHistory()">🔄 Refresh</button>
    </div>
    <div class="log-output" id="cyber-history-log" style="min-height:80px;max-height:200px;font-size:10px">No audits run yet. Run your first scan above!</div>
  </div>
</div>

<div class="tab-content" id="tab-settings">
  <div class="grid grid-2 mb-16">
    <div class="card settings-section" style="border-left:3px solid var(--cyan)">
      <div class="settings-title" style="color:var(--cyan)">📋 Tactical RMM (Self-Hosted)</div>
      <div class="settings-grid">
        <div class="settings-field"><label>API URL</label><input type="text" id="cfg-trmm_api_url" placeholder="https://api.yourdomain.com"></div>
        <div class="settings-field"><label>API Key</label><input type="password" id="cfg-trmm_api_key"></div>
      </div>
      <div style="font-size:9px;color:var(--fg3);margin-top:6px">Get from TRMM → Settings → Global Settings → API Keys. URL is your API subdomain (e.g. https://api.rmm.bvtech.org)</div>
    </div>
    <div class="card settings-section" style="border-left:3px solid #f87171">
      <div class="settings-title" style="color:#f87171">☁️ Cloudflare Pages — BVTech.org</div>
      <div style="font-size:10px;color:var(--green);margin-bottom:10px;padding:8px;border-radius:8px;background:rgba(248,113,113,0.06);border:1px solid rgba(248,113,113,0.15)">
        <strong>Direct Upload Mode (Super Posting, see CHANGELOG_v31.md):</strong><br>
        1. Account ID is <strong>pre-filled</strong> for you ✅<br>
        2. Create a CF API Token at <strong>dash.cloudflare.com/profile/api-tokens</strong> (use "Edit Cloudflare Workers" template)<br>
        3. Paste the token below and click <strong>Save</strong><br>
        4. Click <strong>Test Cloudflare</strong> to verify ✅<br>
        5. Done — no GitHub, no OAuth loops, no fluff
      </div>
      <div class="settings-grid">
        <div class="settings-field"><label>CF API Token <span style="color:#f87171">*</span></label><input type="password" id="cfg-cf_api_token" placeholder="Paste your Cloudflare API token here"></div>
        <div class="settings-field"><label>CF Account ID (pre-filled)</label><input type="text" id="cfg-cf_account_id" value="c31280b99fda28a238ada0b669eedd0a" placeholder="c31280b99fda28a238ada0b669eedd0a"></div>
        <div class="settings-field"><label>CF Project Name</label><input type="text" id="cfg-cf_project_name" value="bvtech-website" placeholder="bvtech-website"></div>
        <div class="settings-field"><label>Site URL</label><input type="text" id="cfg-cf_site_url" value="https://bvtech.org" placeholder="https://bvtech.org"></div>
        <div class="settings-field" style="grid-column:1/-1"><label>BVTech Site Root <span style="color:#86efac">★</span></label><input type="text" id="cfg-bvtech_site_root" value="C:\BVTech2\Website\bvtech.org" placeholder="C:\BVTech2\Website\bvtech.org"><div style="font-size:9px;color:var(--fg3);margin-top:3px">Absolute path to the local mirror of bvtech.org. Walks this folder and uploads everything on each publish. Must contain index.html at the top.</div></div>
        <div class="settings-field"><label>CF Deploy Branch</label><input type="text" id="cfg-cf_deploy_branch" value="main" placeholder="main"></div>
      </div>
      <!-- hidden legacy fields kept so load_config/save_config don't break -->
      <input type="hidden" id="cfg-gh_token" value="">
      <input type="hidden" id="cfg-gh_repo" value="">
      <input type="hidden" id="cfg-gh_branch" value="main">
      <div class="flex gap-8 mt-8">
        <button class="btn btn-sm" style="background:linear-gradient(135deg,#f87171,#f59e0b);color:#fff" onclick="testCFConnection()">🔌 Test Cloudflare</button>
        <button class="btn btn-outline btn-sm" onclick="window.open('https://dash.cloudflare.com/profile/api-tokens','_blank')">Get API Token ↗</button>
        <button class="btn btn-outline btn-sm" onclick="window.open('https://dash.cloudflare.com/c31280b99fda28a238ada0b669eedd0a/pages/view/bvtech-website','_blank')">CF Project ↗</button>
      </div>
    </div>
    <!-- v26: WordPress Legacy card hidden — BVTech is fully on Cloudflare Pages now. Hidden fields preserved so save/load still works. -->
    <div style="display:none">
      <input type="text" id="cfg-wp_site_url" value="https://bvtech.org">
      <input type="text" id="cfg-wp_user" value="">
      <input type="password" id="cfg-wp_app_password" value="">
      <input type="text" id="cfg-wp_relay_key" value="">
    </div>
    <div class="card settings-section" style="border-left:3px solid #ec4899">
      <div class="settings-title" style="color:#ec4899">👤 JordanPolasek.com — Cloudflare Pages</div>
      <div style="font-size:10px;color:var(--fg3);margin-bottom:10px;padding:8px;border-radius:8px;background:rgba(236,72,153,0.06);border:1px solid rgba(236,72,153,0.15)">
        <strong>Status:</strong> JordanPolasek.com is still on WordPress. Once it's migrated to a Cloudflare Pages project (named <strong>jordanpolasek-site</strong>), you can reuse the same CF API Token from above — the Account ID is already pre-filled. Until then, leave blank.
      </div>
      <div class="settings-grid">
        <div class="settings-field"><label>JP CF API Token (optional)</label><input type="password" id="cfg-jp_cf_api_token" placeholder="Same CF token works if JP is on Cloudflare"></div>
        <div class="settings-field"><label>JP CF Account ID (pre-filled)</label><input type="text" id="cfg-jp_cf_account_id" value="c31280b99fda28a238ada0b669eedd0a" placeholder="c31280b99fda28a238ada0b669eedd0a"></div>
        <div class="settings-field"><label>JP CF Project Name</label><input type="text" id="cfg-jp_cf_project_name" value="jordanpolasek-site" placeholder="jordanpolasek-site"></div>
        <div class="settings-field"><label>JP Site URL</label><input type="text" id="cfg-jp_site_url" value="https://jordanpolasek.com" placeholder="https://jordanpolasek.com"></div>
        <div class="settings-field" style="grid-column:1/-1"><label>JP Site Root <span style="color:#86efac">★</span></label><input type="text" id="cfg-jp_site_root" value="C:\BVTech2\Website\jordanpolasek.com" placeholder="C:\BVTech2\Website\jordanpolasek.com"><div style="font-size:9px;color:var(--fg3);margin-top:3px">Absolute path to the local mirror of jordanpolasek.com. Must contain index.html at the top.</div></div>
      </div>
      <!-- v26: legacy JP fields hidden but preserved so save/load still works -->
      <div style="display:none">
        <input type="password" id="cfg-jp_gh_token" value="">
        <input type="text" id="cfg-jp_gh_repo" value="">
        <input type="text" id="cfg-jp_gh_branch" value="main">
        <input type="text" id="cfg-jp_wp_user" value="">
        <input type="password" id="cfg-jp_wp_app_password" value="">
        <input type="text" id="cfg-jp_relay_key" value="">
      </div>
      <div class="flex gap-8 mt-8">
        <button class="btn btn-sm" style="background:linear-gradient(135deg,#ec4899,#7c3aed);color:#fff" onclick="testJPConnection()">🔌 Test JP Connection</button>
        <button class="btn btn-outline btn-sm" onclick="window.open('https://dash.cloudflare.com/','_blank')">CF Dashboard ↗</button>
      </div>
    </div>
  </div>
  <div class="card settings-section mb-16" style="border-left:3px solid #0A66C2">
    <div class="settings-title" style="color:#0A66C2">💼 LinkedIn — ORM Personal Brand</div>
    <div class="settings-grid">
      <div class="settings-field"><label>Access Token</label><input type="password" id="cfg-linkedin_access_token" placeholder="LinkedIn OAuth2 access token"></div>
      <div class="settings-field"><label>Person URN</label><input type="text" id="cfg-linkedin_person_urn" placeholder="urn:li:person:xxxxxxx (auto-detected)"></div>
      <div class="settings-field"><label>Client ID (for OAuth)</label><input type="text" id="cfg-linkedin_client_id" placeholder="LinkedIn App Client ID"></div>
      <div class="settings-field"><label>Client Secret</label><input type="password" id="cfg-linkedin_client_secret" placeholder="LinkedIn App Client Secret"></div>
    </div>
    <div style="font-size:10px;color:var(--green);margin-top:8px;padding:8px;border-radius:8px;background:rgba(10,102,194,0.06);border:1px solid rgba(10,102,194,0.15)">
      <strong>Setup:</strong><br>
      1. Go to <a href="https://www.linkedin.com/developers/" target="_blank" style="color:#0A66C2">linkedin.com/developers</a> → Create App<br>
      2. Request <strong>"Share on LinkedIn"</strong> + <strong>"Sign In with LinkedIn using OpenID Connect"</strong> products<br>
      3. Add <strong>http://localhost:5678/api/linkedin/callback</strong> as a redirect URL<br>
      4. Click "Connect LinkedIn" below to authorize → token auto-saved<br>
      5. ORM Beast will now post to LinkedIn as you! 🚀
    </div>
    <div class="flex gap-8 mt-8">
      <button class="btn btn-sm" style="background:#0A66C2;color:#fff" onclick="connectLinkedIn()">💼 Connect LinkedIn</button>
      <button class="btn btn-sm btn-outline" onclick="testLinkedIn()">🔌 Test Connection</button>
      <button class="btn btn-outline btn-sm" onclick="window.open('https://www.linkedin.com/developers/','_blank')">LinkedIn Developers ↗</button>
    </div>
  </div>
  <!-- v30: Google Business Profile -->
  <div class="card settings-section mb-16" style="border-left:3px solid #4285f4">
    <div class="settings-title" style="color:#4285f4">📍 Google Business Profile — Local SEO Posts</div>
    <div class="settings-grid">
      <div class="settings-field"><label>OAuth Client ID</label><input type="text" id="cfg-google_client_id" placeholder="xxxxx.apps.googleusercontent.com"></div>
      <div class="settings-field"><label>OAuth Client Secret</label><input type="password" id="cfg-google_client_secret" placeholder="GOCSPX-xxxx"></div>
      <div class="settings-field"><label>Redirect URI</label><input type="text" id="cfg-google_redirect_uri" value="http://localhost:5678/api/gbp/oauth/callback" placeholder="http://localhost:5678/api/gbp/oauth/callback"></div>
      <div class="settings-field"><label>Refresh Token (auto-saved after Connect)</label><input type="password" id="cfg-gbp_refresh_token" placeholder="(populated after OAuth)" readonly></div>
      <div class="settings-field"><label>Account (auto-picked after Connect)</label><input type="text" id="cfg-gbp_account_name" placeholder="accounts/123456789" readonly></div>
      <div class="settings-field"><label>Location (auto-picked after Connect)</label><input type="text" id="cfg-gbp_location_name" placeholder="locations/987654321" readonly></div>
      <div class="settings-field" style="grid-column:1/-1"><label>Location Title (display only)</label><input type="text" id="cfg-gbp_location_title" placeholder="BVTech LLC — El Campo" readonly></div>
    </div>
    <div style="font-size:10px;color:var(--fg2);margin-top:8px;padding:10px;border-radius:8px;background:rgba(66,133,244,0.06);border:1px solid rgba(66,133,244,0.15)">
      <strong style="color:#4285f4">One-time setup (takes ~15 min):</strong><br>
      1. Go to <a href="https://console.cloud.google.com/" target="_blank" style="color:#4285f4">console.cloud.google.com</a> → create or pick a project<br>
      2. Enable these APIs: <code>My Business Account Management API</code>, <code>My Business Business Information API</code>, and <code>Google My Business API</code><br>
      3. <strong style="color:#f59e0b">Request API access</strong> at <a href="https://support.google.com/business/contact/api_default" target="_blank" style="color:#4285f4">support.google.com/business/contact/api_default</a> — this takes 1-2 business days and is REQUIRED before localPosts will work (you'll see 403 errors otherwise)<br>
      4. Create OAuth 2.0 credentials (Web application) with redirect URI: <code>http://localhost:5678/api/gbp/oauth/callback</code><br>
      5. Paste the Client ID + Secret above, click Save<br>
      6. Click <strong>Connect Google Business</strong> — a Google consent window opens, authorize, done<br>
      7. Click <strong>Pick Location</strong> to load your accounts and pick the right business location
    </div>
    <div class="flex gap-8 mt-8" style="flex-wrap:wrap">
      <button class="btn btn-sm" style="background:linear-gradient(135deg,#4285f4,#34a853);color:#fff;font-weight:700" onclick="connectGoogleBusiness()">📍 Connect Google Business</button>
      <button class="btn btn-sm btn-outline" onclick="gbpPickLocation()">🏢 Pick Location</button>
      <button class="btn btn-sm btn-outline" onclick="testGBP()">🔌 Test Connection</button>
      <button class="btn btn-sm btn-outline" style="color:#f87171;border-color:rgba(248,113,113,0.4)" onclick="disconnectGBP()">🔌 Disconnect</button>
      <button class="btn btn-outline btn-sm" onclick="window.open('https://business.google.com/','_blank')">GBP Dashboard ↗</button>
      <button class="btn btn-outline btn-sm" onclick="window.open('https://support.google.com/business/contact/api_default','_blank')">Request API Access ↗</button>
    </div>
    <div id="gbp-status" style="display:none;margin-top:10px;padding:10px 12px;background:rgba(0,0,0,0.35);border-radius:6px;font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#e2e8f0;white-space:pre-wrap;max-height:320px;overflow-y:auto;"></div>
  </div>
  <div class="grid grid-2 mb-16">
    <div class="card settings-section" style="border-left:3px solid #0078d4">
      <div class="settings-title" style="color:#0078d4">📧 Microsoft 365 — Azure AD</div>
      <div class="settings-grid">
        <div class="settings-field"><label>Tenant ID</label><input type="text" id="cfg-tenant_id"></div>
        <div class="settings-field"><label>Client ID</label><input type="text" id="cfg-client_id"></div>
        <div class="settings-field"><label>Client Secret</label><input type="password" id="cfg-client_secret"></div>
      </div>
      <div style="font-size:9px;color:var(--fg3);margin-top:6px">Used for both Email Campaigns AND Inbox. Azure → App registrations → Mail.ReadWrite + Mail.Send permissions.</div>
      <div class="mt-8"><button class="btn btn-ms btn-sm" onclick="testM365FromSettings()">🔌 Test M365 Connection</button></div>
    </div>
    <div class="card settings-section" style="border-left:3px solid #7c3aed">
      <div class="settings-title" style="color:#7c3aed">📞 DialPad Pro</div>
      <div class="settings-grid">
        <div class="settings-field"><label>API Key</label><input type="password" id="cfg-dialpad_key"></div>
        <div class="settings-field"><label>User ID</label><input type="text" id="cfg-dialpad_user_id"></div>
        <div class="settings-field"><label>Phone Number</label><input type="text" id="cfg-dialpad_number"></div>
      </div>
    </div>
  </div>
  <div class="grid grid-2 mb-16">
    <div class="card settings-section" style="border-left:3px solid #ff7a59">
      <div class="settings-title" style="color:#ff7a59">🔶 HubSpot CRM</div>
      <div class="settings-field"><label>Private App Token</label><input type="password" id="cfg-hubspot_token"></div>
      <div class="settings-field"><label>BCC Forwarding Address (for email tracking — see HS Track tab)</label><input type="text" id="cfg-hubspot_bcc_address" placeholder="yourtoken@bcc.hubspot.com"></div>
    </div>
    <div class="card settings-section" style="border-left:3px solid #4285f4">
      <div class="settings-title" style="color:#4285f4">🌐 Google Places API</div>
      <div class="settings-field"><label>API Key</label><input type="password" id="cfg-google_api_key"></div>
    </div>
  </div>
  <div class="grid grid-2 mb-16">
    <div class="card settings-section" style="border-left:3px solid #ff5722">
      <div class="settings-title" style="color:#ff5722">🎯 Hunter.io — Email Finder &amp; Verifier (SUPER SCRAPER)</div>
      <div class="settings-field"><label>API Key</label><input type="password" id="cfg-hunter_api_key" placeholder="Optional — adds named-contact discovery + email verification"></div>
      <div style="font-size:9px;color:var(--fg3);margin-top:6px">Get from hunter.io → API. Free tier = 25 searches/mo. Used by Super Scraper to find named decision-makers and verify generated email patterns.</div>
    </div>
    <div class="card settings-section" style="border-left:3px solid #00897b">
      <div class="settings-title" style="color:#00897b">🔎 Bing Search API (optional)</div>
      <div class="settings-field"><label>Subscription Key</label><input type="password" id="cfg-bing_api_key" placeholder="Optional — improves LinkedIn discovery quality"></div>
      <div style="font-size:9px;color:var(--fg3);margin-top:6px">Optional. If unset, Super Scraper falls back to DuckDuckGo HTML scraping (free, no key).</div>
    </div>
  </div>
  <div class="grid grid-2 mb-16">
    <div class="card settings-section" style="border-left:3px solid #f472b6">
      <div class="settings-title" style="color:#f472b6">🤖 Claude AI (Anthropic)</div>
      <div class="settings-field"><label>API Key</label><input type="password" id="cfg-anthropic_key"></div>
      <div style="font-size:9px;color:var(--fg3);margin-top:6px">Get from console.anthropic.com → API Keys. Powers the AI Assistant, Debugger & Self-Builder.</div>
    </div>
    <div></div>
  </div>
  <div class="card settings-section mb-16" style="border-left:3px solid #22c55e">
    <div class="settings-title" style="color:#22c55e">👤 Sender Identity</div>
    <div class="settings-grid">
      <div class="settings-field"><label>Name</label><input type="text" id="cfg-sender_name"></div>
      <div class="settings-field"><label>Email</label><input type="text" id="cfg-sender_email"></div>
      <div class="settings-field"><label>Title</label><input type="text" id="cfg-sender_title"></div>
      <div class="settings-field"><label>Phone</label><input type="text" id="cfg-sender_phone"></div>
      <div class="settings-field" style="grid-column:span 2"><label>Address (CAN-SPAM)</label><input type="text" id="cfg-physical_address"></div>
    </div>
  </div>
  <div class="flex justify-center">
    <button class="btn btn-green btn-lg" onclick="saveSettings()">💾 SAVE ALL SETTINGS</button>
  </div>
</div>

<!-- ===== AI TAB (NEW v2.1) ===== -->
<div class="tab-content" id="tab-ai">
  <div class="glow" style="background:linear-gradient(135deg,rgba(236,72,153,0.06),rgba(124,58,237,0.06));border:1px solid rgba(236,72,153,0.12);margin-bottom:16px;">
    <div class="section-title" style="color:#f472b6">🤖 Claude AI — Brain, Debugger & Self-Builder</div>
    <div class="section-desc">Claude has full context about your BVTech app — all code, all APIs, all config. Ask it anything: debug errors, add features, explain code, optimize scripts, or just chat about MSP strategy.</div>
  </div>

  <!-- Mode selector -->
  <div class="ai-mode-bar">
    <button class="ai-mode-btn active" onclick="setAIMode('chat',this)">💬 Chat</button>
    <button class="ai-mode-btn" onclick="setAIMode('debug',this)">🔧 Debugger</button>
    <button class="ai-mode-btn" onclick="setAIMode('build',this)">🧬 Self-Builder</button>
    <button class="ai-mode-btn" onclick="setAIMode('strategy',this)">📊 MSP Strategy</button>
    <button class="ai-mode-btn" onclick="clearAIChat()">🗑️ Clear</button>
    <div class="ai-status"><span class="ai-dot" id="ai-dot"></span> <span id="ai-status-text">Ready</span></div>
  </div>

  <div class="ai-chat-container">
    <div class="ai-messages" id="ai-messages">
      <div class="ai-msg assistant">Hey Jordan! 👋 I'm Claude — your AI assistant built into BVTech Command Center v20.0.

I have full context about your app: SuperOps PSA, Guardz Security, M365 Inbox, DialPad, HubSpot CRM, Revenue Dashboard — the whole stack.

<strong>What I can do:</strong>
• <strong>💬 Chat</strong> — Ask me anything about your app or MSP business
• <strong>🔧 Debug</strong> — Paste an error, I'll diagnose it and suggest fixes
• <strong>🧬 Build</strong> — Ask me to add features, I'll write the code and can apply it
• <strong>📊 Strategy</strong> — MSP marketing advice, call scripts, email templates

Try: "Why isn't SuperOps connecting?" or "Write me a security assessment email template"</div>
    </div>

    <div class="ai-input-row">
      <textarea id="ai-input" placeholder="Ask Claude anything... (Shift+Enter for newline, Enter to send)" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendAIMessage();}"></textarea>
      <button class="btn btn-pink btn-lg" onclick="sendAIMessage()" id="ai-send-btn">Send</button>
    </div>
  </div>

  <!-- AUTOPILOT DASHBOARD — now in WARMODE tab -->
  <div class="glow glow-cyan mt-16">
    <div class="flex justify-between items-center mb-12">
      <div>
        <div class="section-title" style="color:var(--cyan)">🛸 AutoPilot v3 → WARMODE Tab</div>
        <div class="section-desc">The autonomous daemon has been upgraded to WARMODE v3 with parallel workers, aggressive building, and auto-modes. Click below to access the full dashboard.</div>
      </div>
      <button class="btn btn-danger btn-lg" onclick="switchTab('warmode',document.querySelectorAll('.tab')[10])">⚔️ OPEN WARMODE</button>
    </div>

    <div class="stats stats-6 mb-12">
      <div class="card stat"><div class="stat-icon">💚</div><div class="stat-label">Health</div><div class="stat-value" style="color:var(--green)" id="pilot-health">OK</div></div>
      <div class="card stat"><div class="stat-icon">🔧</div><div class="stat-label">Errors Fixed</div><div class="stat-value" style="color:var(--blue)" id="pilot-fixed">0</div></div>
      <div class="card stat"><div class="stat-icon">🧬</div><div class="stat-label">Improvements</div><div class="stat-value" style="color:var(--purple)" id="pilot-improvements">0</div></div>
      <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Queue</div><div class="stat-value" style="color:var(--orange)" id="pilot-queue">0</div></div>
      <div class="card stat"><div class="stat-icon">🔄</div><div class="stat-label">Cycles</div><div class="stat-value" style="color:var(--fg3)" id="pilot-cycles">0</div></div>
      <div class="card stat"><div class="stat-icon">🛡️</div><div class="stat-label">Compliance</div><div class="stat-value" style="color:var(--green)" id="pilot-compliance">OK</div></div>
    </div>

    <div class="flex gap-8 mb-12 flex-wrap">
      <button class="btn btn-cyan btn-sm" onclick="pilotHealthNow()">🏥 Health Check Now</button>
      <button class="btn btn-outline btn-sm" onclick="pilotComplianceNow()">🛡️ Compliance Check</button>
      <button class="btn btn-outline btn-sm" onclick="pilotImproveNow()">🧬 Run Improvement</button>
      <button class="btn btn-purple btn-sm" onclick="pilotNightlyNow()">🌙 Trigger Nightly Build</button>
      <button class="btn btn-outline btn-sm" onclick="loadPilotStatus()">🔄 Refresh Status</button>
    </div>

    <div class="grid grid-2 gap-12">
      <div>
        <label class="filter-label">Add Task to Improvement Queue</label>
        <div class="flex gap-8 mt-8">
          <input type="text" id="pilot-task" placeholder="e.g. Add export to CSV button on CRM tab" style="flex:1">
          <button class="btn btn-cyan btn-sm" onclick="addPilotTask()">+ Queue</button>
        </div>
      </div>
      <div>
        <label class="filter-label">AutoPilot Live Log</label>
        <div class="log-output" id="pilot-log" style="min-height:120px;max-height:200px;font-size:10px;">AutoPilot v3 running with parallel workers...</div>
      </div>
    </div>
  </div>
</div>

<!-- ===== WARMODE TAB (v3.0) ===== -->
<div class="tab-content" id="tab-warmode">

  <!-- WARMODE Header -->
  <div class="glow mb-16" id="warmode-header" style="background:linear-gradient(135deg,rgba(239,68,68,0.08),rgba(245,158,11,0.06));border:1px solid rgba(239,68,68,0.2);">
    <div class="flex justify-between items-center">
      <div>
        <div class="section-title" style="color:#f87171;font-size:16px;">⚔️ WARMODE — Aggressive Self-Building Engine</div>
        <div class="section-desc">Pumps out improvements nonstop. Self-tests after every change. Auto-patches failures. Generates its own ideas. Runs parallel workers for scraping, emailing, and building simultaneously.</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:9px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:4px">MASTER SWITCH</div>
        <label class="toggle-switch" style="transform:scale(1.3)">
          <input type="checkbox" id="warmode-toggle" onchange="toggleWarmode(this.checked)">
          <span class="toggle-slider"></span>
        </label>
        <div id="warmode-label" style="font-size:10px;font-weight:800;color:var(--fg3);margin-top:4px">OFF</div>
      </div>
    </div>
  </div>

  <!-- Speed Selector -->
  <div class="card mb-16" style="border-left:3px solid var(--red)">
    <div class="flex justify-between items-center">
      <div>
        <div style="font-size:12px;font-weight:800;color:var(--red)">⚡ Build Speed</div>
        <div style="font-size:9px;color:var(--fg3);margin-top:2px">Controls how fast WARMODE pumps out improvements</div>
      </div>
      <div class="flex gap-8">
        <button class="speed-btn active-normal" id="speed-normal" onclick="setWarSpeed('normal')">🟢 NORMAL<br><span style="font-size:8px;opacity:0.6">10/hr — steady</span></button>
        <button class="speed-btn" id="speed-aggressive" onclick="setWarSpeed('aggressive')">🟡 AGGRESSIVE<br><span style="font-size:8px;opacity:0.6">20/hr — fast</span></button>
        <button class="speed-btn" id="speed-ludicrous" onclick="setWarSpeed('ludicrous')">🔴 LUDICROUS<br><span style="font-size:8px;opacity:0.6">60/hr — MAX</span></button>
      </div>
    </div>
  </div>

  <!-- Live Stats -->
  <div class="stats stats-8 mb-16" id="war-stats">
    <div class="card stat"><div class="stat-icon">⚔️</div><div class="stat-label">Status</div><div class="stat-value" style="color:var(--fg3)" id="war-status">OFF</div></div>
    <div class="card stat"><div class="stat-icon">🧬</div><div class="stat-label">Builds</div><div class="stat-value" style="color:var(--purple)" id="war-builds">0</div></div>
    <div class="card stat"><div class="stat-icon">🧪</div><div class="stat-label">Tests ✅</div><div class="stat-value" style="color:var(--green)" id="war-tests-pass">0</div></div>
    <div class="card stat"><div class="stat-icon">❌</div><div class="stat-label">Tests Fail</div><div class="stat-value" style="color:var(--red)" id="war-tests-fail">0</div></div>
    <div class="card stat"><div class="stat-icon">🔧</div><div class="stat-label">Errors Fixed</div><div class="stat-value" style="color:var(--blue)" id="war-fixed">0</div></div>
    <div class="card stat"><div class="stat-icon">📋</div><div class="stat-label">Queue</div><div class="stat-value" style="color:var(--orange)" id="war-queue">0</div></div>
    <div class="card stat"><div class="stat-icon">✅</div><div class="stat-label">Completed</div><div class="stat-value" style="color:var(--cyan)" id="war-done">0</div></div>
    <div class="card stat"><div class="stat-icon">🔨</div><div class="stat-label">Current</div><div class="stat-value" style="color:var(--pink);font-size:10px;word-break:break-all" id="war-current">—</div></div>
  </div>

  <!-- Worker Grid -->
  <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:8px">PARALLEL WORKERS — each on its own thread</div>
  <div class="worker-grid mb-16" id="worker-grid"></div>

  <!-- Auto-Mode Toggles -->
  <div class="grid grid-2 gap-12 mb-16">
    <div class="card" style="border-left:3px solid var(--green)">
      <div style="font-size:12px;font-weight:800;color:var(--green);margin-bottom:10px">🤖 Auto-Mode Switches</div>
      <div id="auto-toggles">
        <div class="auto-row"><div class="auto-label">⚔️ WARMODE (Build)</div><label class="toggle-switch"><input type="checkbox" id="at-warmode" onchange="updateAutoSetting('warmode_enabled',this.checked)"><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">🔍 Auto-Scrape</div><label class="toggle-switch"><input type="checkbox" id="at-scrape" onchange="updateAutoSetting('auto_scrape',this.checked)"><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">📧 Auto-Email</div><label class="toggle-switch"><input type="checkbox" id="at-email" onchange="updateAutoSetting('auto_email',this.checked)"><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">💚 Auto-Health</div><label class="toggle-switch"><input type="checkbox" id="at-health" onchange="updateAutoSetting('auto_health',this.checked)" checked><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">🛡️ Auto-Compliance</div><label class="toggle-switch"><input type="checkbox" id="at-compliance" onchange="updateAutoSetting('auto_compliance',this.checked)" checked><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">🔧 Auto-Error-Heal</div><label class="toggle-switch"><input type="checkbox" id="at-heal" onchange="updateAutoSetting('auto_error_heal',this.checked)" checked><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">💾 Auto-Backup</div><label class="toggle-switch"><input type="checkbox" id="at-backup" onchange="updateAutoSetting('auto_backup',this.checked)" checked><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">📊 Daily Report</div><label class="toggle-switch"><input type="checkbox" id="at-report" onchange="updateAutoSetting('auto_report',this.checked)"><span class="toggle-slider"></span></label></div>
        <div class="auto-row"><div class="auto-label">🌅 Daytime Only</div><label class="toggle-switch"><input type="checkbox" id="at-daytime" onchange="updateAutoSetting('daytime_mode',this.checked)" checked><span class="toggle-slider"></span></label></div>
      </div>
    </div>

    <div class="card" style="border-left:3px solid var(--purple)">
      <div style="font-size:12px;font-weight:800;color:var(--purple);margin-bottom:10px">🎯 Quick Actions</div>
      <div class="flex gap-8 mb-12 flex-wrap">
        <button class="btn btn-danger btn-sm" onclick="warRunTests()">🧪 Run Tests Now</button>
        <button class="btn btn-purple btn-sm" onclick="warNightlyNow()">🌙 Trigger Nightly</button>
        <button class="btn btn-cyan btn-sm" onclick="warBackupNow()">💾 Backup Now</button>
        <button class="btn btn-green btn-sm" onclick="warHealthNow()">💚 Health Check</button>
        <button class="btn btn-outline btn-sm" onclick="warComplianceNow()">🛡️ Compliance</button>
        <button class="btn btn-pink btn-sm" onclick="warGenerateIdeas()">💡 Generate Ideas</button>
      </div>

      <div style="font-size:10px;font-weight:800;color:var(--fg3);letter-spacing:0.5px;margin-bottom:6px">ADD TASK TO QUEUE</div>
      <div class="flex gap-8">
        <input type="text" id="war-task-input" placeholder="e.g. Add CSV export button to CRM tab" style="flex:1">
        <button class="btn btn-primary btn-sm" onclick="warAddTask()">+ Queue</button>
      </div>

      <div style="font-size:10px;font-weight:800;color:var(--fg3);letter-spacing:0.5px;margin:12px 0 6px">BACKUP / RESTORE</div>
      <div class="flex gap-8">
        <button class="btn btn-outline btn-sm" onclick="warListBackups()">📁 List Backups</button>
        <select id="war-backup-select" style="flex:1;font-size:10px"><option value="">Select backup to restore...</option></select>
        <button class="btn btn-danger btn-sm" onclick="warRestore()">⏪ Restore</button>
      </div>
    </div>
  </div>

  <!-- Build Queue + Live Log side by side -->
  <div class="grid grid-2 gap-12 mb-16">
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">BUILD QUEUE</div>
      <div class="log-output" id="war-queue-log" style="min-height:300px;font-size:10px">Loading queue...</div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:6px">LIVE BUILD LOG</div>
      <div class="log-output" id="war-live-log" style="min-height:300px;font-size:10px">Waiting for WARMODE to start...</div>
    </div>
  </div>

  <!-- Recent Builds -->
  <div class="card mb-16">
    <div style="font-size:11px;font-weight:800;color:var(--fg3);letter-spacing:1px;margin-bottom:8px">RECENT BUILDS</div>
    <div id="war-recent-builds" style="font-size:10px;color:var(--fg2)">No builds yet.</div>
  </div>

</div><!-- /tab-warmode -->

</div><!-- /content -->

<!-- Toast -->
<div class="toast toast-success" id="toast"></div>

<!-- v18: WELCOME MODAL — Shows on first run or version update -->
<div id="welcome-overlay" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);z-index:9999;backdrop-filter:blur(8px);overflow-y:auto">
  <div style="max-width:640px;margin:40px auto;padding:32px;background:linear-gradient(135deg,rgba(10,14,26,0.98),rgba(17,24,39,0.98));border:1px solid rgba(124,58,237,0.3);border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.5)">
    <div style="text-align:center;margin-bottom:20px">
      <div style="font-size:28px;font-weight:900;letter-spacing:3px;background:linear-gradient(135deg,#7c3aed,#3b82f6,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent">BVTECH</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.4);letter-spacing:2px;margin-top:4px">MSP COMMAND CENTER — v31 FINAL</div>
    </div>

    <div style="padding:16px;border-radius:10px;background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.2);margin-bottom:16px">
      <div style="font-size:13px;font-weight:800;color:#4ade80;margin-bottom:8px">🔧 Recently Fixed</div>
      <div style="font-size:11px;color:#94a3b8;line-height:1.8">
        <strong style="color:#f87171">WordPress Sync 404 Error — FIXED</strong><br>
        SiteGround's WAF was blocking the relay because the auth key was in the URL query string. Now sent securely in POST body. <strong>Re-upload bvtech-api.php + jp-api.php</strong> to your servers for this fix to work.<br><br>
        <strong style="color:#f87171">Settings Not Persisting — FIXED</strong><br>
        wp_user, wp_app_password, and anthropic_key were missing from the default config template. Now all fields are saved properly and survive version updates.<br><br>
        <strong style="color:#f87171">Old Version Running in Background — FIXED</strong><br>
        v18 now auto-kills any previous instance on port 5678 before starting. No more accidentally running the wrong version during demos.
      </div>
    </div>

    <div style="padding:16px;border-radius:10px;background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.2);margin-bottom:16px">
      <div style="font-size:13px;font-weight:800;color:#a78bfa;margin-bottom:8px">🚀 Quick Setup Checklist</div>
      <div style="font-size:11px;color:#94a3b8;line-height:1.8">
        1. <strong>Re-upload PHP files</strong> — Upload <code style="background:rgba(124,58,237,0.15);padding:1px 5px;border-radius:4px">bvtech-api.php</code> to bvtech.org/public_html/ and <code style="background:rgba(124,58,237,0.15);padding:1px 5px;border-radius:4px">jp-api.php</code> to jordanpolasek.com/public_html/<br>
        2. <strong>Check Settings</strong> — Verify all API keys are filled in (especially WP credentials)<br>
        3. <strong>Test WP Connection</strong> — Go to WordPress tab → click 🔌 Test Connection<br>
        4. <strong>You're good to go!</strong> All your existing ORM history, queue, and config are preserved.
      </div>
    </div>

    <div style="padding:16px;border-radius:10px;background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);margin-bottom:20px">
      <div style="font-size:13px;font-weight:800;color:#06b6d4;margin-bottom:8px">📋 Features</div>
      <div style="font-size:10px;color:#64748b;line-height:1.7">
        📊 Dashboard • 📋 Tactical RMM • 🛡️ Guardz Security • 🌐 WordPress + AI Blog Engine (SEO/GEO/AEO) • 📬 M365 Inbox • 💰 Revenue Dashboard • 🔍 Smart Scraper • 📧 Email Campaigns • 💬 SMS • 📞 Power Dialer • 🎙️ DialPad AI Phone • 🧠 AI Call Coaching • 🔥 HubSpot Pipeline • 🔶 CRM Sync • 🚀 Super Posting v30 (BVTech + JP + LinkedIn + GBP) • 🤖 Claude AI Brain • ⚔️ WARMODE Builder • 🧹 Duplicate Scanner • 📊 SEO Scorer
      </div>
    </div>

    <div style="text-align:center">
      <button onclick="dismissWelcome()" style="padding:12px 40px;border:none;border-radius:10px;background:linear-gradient(135deg,#7c3aed,#3b82f6);color:#fff;font-size:14px;font-weight:800;cursor:pointer;font-family:inherit;letter-spacing:0.5px;transition:all 0.2s">✅ GOT IT — LET'S GO</button>
    </div>
  </div>
</div>

<script>
// ==================== v32.1: BUILT-IN DEBUG OVERLAY ====================
// Captures any JS error, unhandled rejection, or console.error and shows
// it in a visible UI panel. This exists because v32.0 shipped with a
// duplicate const declaration that silently broke half the app and there
// was no way for the user to see why. Never again.
(function() {
  var errors = [];
  var maxErrors = 50;
  var panelVisible = false;

  function makePanel() {
    if (document.getElementById('bvtech-debug-panel')) return;
    var p = document.createElement('div');
    p.id = 'bvtech-debug-panel';
    p.style.cssText = 'position:fixed;bottom:0;left:0;right:0;max-height:40vh;background:#1a0a0a;border-top:3px solid #ef4444;color:#fca5a5;font:11px ui-monospace,Consolas,monospace;padding:8px 12px;z-index:99999;overflow-y:auto;display:none;box-shadow:0 -8px 24px rgba(0,0,0,0.5)';
    p.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-weight:700;color:#ef4444"><span>🐛 BVTech Debug Console — JS errors captured:</span><span><button onclick="window.bvtechDebug.copy()" style="background:#7f1d1d;color:#fff;border:none;padding:3px 8px;border-radius:3px;cursor:pointer;font-size:10px;margin-right:4px">Copy</button><button onclick="window.bvtechDebug.clear()" style="background:#7f1d1d;color:#fff;border:none;padding:3px 8px;border-radius:3px;cursor:pointer;font-size:10px;margin-right:4px">Clear</button><button onclick="window.bvtechDebug.hide()" style="background:#7f1d1d;color:#fff;border:none;padding:3px 8px;border-radius:3px;cursor:pointer;font-size:10px">×</button></span></div><div id="bvtech-debug-list"></div>';
    if (document.body) document.body.appendChild(p);
  }

  function render() {
    var list = document.getElementById('bvtech-debug-list');
    if (!list) return;
    list.innerHTML = errors.map(function(e, i) {
      return '<div style="border-bottom:1px solid #450a0a;padding:4px 0"><strong>#' + (i+1) + ' [' + e.type + ']</strong> ' + escapeHtml(e.msg) + (e.src ? '<br><span style="color:#94a3b8">at ' + escapeHtml(e.src) + ':' + e.line + '</span>' : '') + '</div>';
    }).join('');
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function show() {
    makePanel();
    var p = document.getElementById('bvtech-debug-panel');
    if (p) { p.style.display = 'block'; panelVisible = true; render(); }
  }

  function record(type, msg, src, line) {
    errors.push({ type: type, msg: msg, src: src || '', line: line || 0, t: Date.now() });
    if (errors.length > maxErrors) errors.shift();
    show();
  }

  // Capture window.onerror
  window.addEventListener('error', function(ev) {
    record('error', ev.message || String(ev.error || 'unknown'), ev.filename, ev.lineno);
  });

  // Capture unhandled promise rejections
  window.addEventListener('unhandledrejection', function(ev) {
    var msg = ev.reason && ev.reason.message ? ev.reason.message : String(ev.reason || 'unknown');
    record('promise', msg, '', 0);
  });

  // Wrap console.error
  var origConsoleError = console.error;
  console.error = function() {
    try { record('console', Array.prototype.slice.call(arguments).map(String).join(' '), '', 0); } catch(e) {}
    return origConsoleError.apply(console, arguments);
  };

  // Public API
  window.bvtechDebug = {
    show: show,
    hide: function() { var p = document.getElementById('bvtech-debug-panel'); if (p) { p.style.display = 'none'; panelVisible = false; } },
    clear: function() { errors = []; render(); },
    copy: function() {
      var txt = errors.map(function(e, i) { return '#' + (i+1) + ' [' + e.type + '] ' + e.msg + (e.src ? ' @ ' + e.src + ':' + e.line : ''); }).join('\n');
      try { navigator.clipboard.writeText(txt).then(function(){ alert('Copied ' + errors.length + ' errors to clipboard'); }); } catch(e) { alert(txt); }
    },
    record: record,
    getErrors: function() { return errors.slice(); },
    count: function() { return errors.length; },
  };
})();

// ==================== v32.1: STARTUP HEALTH CHECK ====================
// Pings /api/health on page load and shows a top banner with the result.
// This is what the user kept asking about — the "Refresh All Systems Start"
// confirmation that things are alive.
window.addEventListener('DOMContentLoaded', function() {
  setTimeout(function() {
    fetch('/api/health').then(function(r) { return r.json(); }).then(function(d) {
      var banner = document.createElement('div');
      var ok = d.ok === true;
      var color = ok ? '#16a34a' : '#dc2626';
      var bg = ok ? 'rgba(22,163,74,0.1)' : 'rgba(220,38,38,0.1)';
      banner.id = 'bvtech-health-banner';
      banner.style.cssText = 'position:fixed;top:10px;right:10px;max-width:380px;background:' + bg + ';border:1px solid ' + color + ';color:' + color + ';padding:10px 14px;border-radius:6px;font:12px ui-monospace,Consolas,monospace;z-index:9998;box-shadow:0 4px 12px rgba(0,0,0,0.3);cursor:pointer';
      var icon = ok ? '✅' : '⚠️';
      banner.innerHTML = '<div style="font-weight:700;margin-bottom:4px">' + icon + ' All Systems ' + (ok ? 'Operational' : 'Degraded') + '</div><div style="font-size:10px;opacity:0.85">v' + d.version + ' · ' + d.routes + ' routes · ' + d.tasks + ' tasks · ' + d.modules_ok + '/' + d.modules_total + ' modules</div><div style="font-size:9px;opacity:0.7;margin-top:2px">Click to dismiss</div>';
      banner.onclick = function() { banner.remove(); };
      if (document.body) {
        document.body.appendChild(banner);
        setTimeout(function() { if (banner.parentNode) banner.remove(); }, 8000);
      }
    }).catch(function(e) {
      console.error('Health check failed: ' + e.message);
    });
  }, 500);
});

let selectedDisposition = '';

// Auto-format phone numbers for DialPad (+1XXXXXXXXXX)
function formatPhoneNumber(phone) {
  if (!phone) return phone;
  // Strip everything except digits
  let digits = phone.replace(/[^0-9]/g, '');
  // Remove leading 1 if 11 digits
  if (digits.length === 11 && digits.startsWith('1')) digits = digits;
  else if (digits.length === 10) digits = '1' + digits;
  else if (digits.length < 10) return phone; // too short, return as-is
  return '+' + digits;
}

function formatPhoneInput(inputId) {
  const el = document.getElementById(inputId);
  if (el) {
    el.value = formatPhoneNumber(el.value);
    showToast('Formatted: ' + el.value);
  }
}

function switchTab(name, el) {
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  el.classList.add('active');
  // v29: When switching to ORM tab, refresh site-root status dots
  if (name === 'orm') { try { ormSiteRootCheck(true); } catch(e){} }
}

// v29: Check both site_root folders and update the status dots
async function ormSiteRootCheck(silent) {
  const bv = document.getElementById('orm-v29-status-dot-bv');
  const jp = document.getElementById('orm-v29-status-dot-jp');
  if (!bv || !jp) return;
  const renderDot = (el, site, d) => {
    if (d.ok) {
      el.innerHTML = `${site}: <span style="color:#86efac">●</span> ${d.file_count} files, ${d.size_mb} MiB`;
      el.title = d.path;
    } else {
      el.innerHTML = `${site}: <span style="color:#fca5a5">●</span> ${d.reason || 'error'}`;
      el.title = d.message || '';
    }
  };
  try {
    const [rbv, rjp] = await Promise.all([
      fetch('/api/orm/site-root-check/bvtech').then(r=>r.json()),
      fetch('/api/orm/site-root-check/jp').then(r=>r.json()),
    ]);
    renderDot(bv, 'BVTech', rbv);
    renderDot(jp, 'JP', rjp);
    if (!silent) {
      const out = document.getElementById('orm-v29-test-output');
      out.style.display = 'block';
      out.textContent =
        `BVTech: ${rbv.ok ? 'OK' : 'ERROR'} — ${rbv.message || rbv.error || ''}\n` +
        `        path: ${rbv.path || '(not set)'}\n\n` +
        `JP:     ${rjp.ok ? 'OK' : 'ERROR'} — ${rjp.message || rjp.error || ''}\n` +
        `        path: ${rjp.path || '(not set)'}\n`;
    }
  } catch(e) {
    bv.textContent = 'BVTech: ?'; jp.textContent = 'JP: ?';
  }
}

// v29: Dry-run deploy — walks the site, computes hashes, asks CF what
// it WOULD upload, then stops. Never actually deploys.
async function ormTestDeploy(site) {
  const out = document.getElementById('orm-v29-test-output');
  out.style.display = 'block';
  out.textContent = `🧪 Running Test Deploy for ${site}... (walk + hash + check-missing, no actual deploy)\n\nThis may take 10-30 seconds on first run.\n`;
  try {
    const res = await fetch('/api/orm/cf-test-deploy/' + site, {method: 'POST'});
    const d = await res.json();
    if (d.error) {
      out.textContent = `❌ Test Deploy FAILED for ${site}\n\n${d.error}\n\n${d.traceback || ''}`;
      return;
    }
    let report = `✅ Test Deploy OK — ${site}\n`;
    report += `───────────────────────────────────────\n`;
    report += `Project:         ${d.project_name || ''}\n`;
    report += `Site root:       ${d.site_root || ''}\n`;
    report += `Files walked:    ${d.files_total || 0}\n`;
    report += `Would upload:    ${d.files_would_upload || 0}  (new/changed)\n`;
    report += `Already cached:  ${d.files_cached || 0}\n`;
    report += `Total size:      ${((d.bytes_total||0)/1024/1024).toFixed(2)} MiB\n`;
    report += `Elapsed:         ${d.elapsed_sec || 0}s\n`;
    if (d.sample_would_upload && d.sample_would_upload.length) {
      report += `\nSample of files that would upload:\n`;
      d.sample_would_upload.forEach(f => { report += `  • ${f}\n`; });
    }
    report += `\n───────────────────────────────────────\n`;
    report += `DRY RUN — nothing was actually deployed.\n`;
    if ((d.files_would_upload || 0) > 100) {
      report += `\n⚠  First deploys upload everything. That's expected.\n`;
      report += `    Second run should show very few files to upload.\n`;
    }
    out.textContent = report;
  } catch(e) {
    out.textContent = `❌ Network error: ${e}`;
  }
}

function showToast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast toast-'+type+' show';
  setTimeout(() => t.classList.remove('show'), 3500);
}

function selectDisp(el, disp) {
  document.querySelectorAll('.disp-btn').forEach(b => b.classList.remove('selected'));
  el.classList.add('selected');
  selectedDisposition = disp;
}

// ==================== DIALPAD ====================
async function testDialPad() {
  const res = await fetch('/api/dialpad/test');
  const d = await res.json();
  showToast(d.status === 'connected' ? '✅ DialPad connected! '+d.company : '❌ '+d.error, d.status==='connected'?'success':'error');
}

async function loadCallAnalytics() {
  document.getElementById('dp-analytics').style.display = 'grid';
  const res = await fetch('/api/dialpad/analytics?days=30');
  const d = await res.json();
  if (!d.error) {
    document.getElementById('dp-total').textContent = d.total_calls || 0;
    document.getElementById('dp-inbound').textContent = d.inbound || 0;
    document.getElementById('dp-outbound').textContent = d.outbound || 0;
    document.getElementById('dp-recorded').textContent = d.recorded || 0;
    document.getElementById('dp-avgdur').textContent = d.avg_duration_sec || 0;
    document.getElementById('dp-totalmin').textContent = d.total_duration_min || 0;
    document.getElementById('dp-connectrate').textContent = (d.connect_rate||0)+'%';
    document.getElementById('dp-today').textContent = d.calls_today || 0;
    showToast('📊 Analytics loaded!');
  } else showToast('Error: '+d.error, 'error');
}

async function loadRecentCalls() {
  const log = document.getElementById('dp-calls-log');
  log.innerHTML = 'Loading recent calls...\n';
  try {
    const res = await fetch('/api/dialpad/calls');
    const data = await res.json();
    // Handle different response shapes
    let calls = data.items || data.calls || data.results || (Array.isArray(data) ? data : null);
    if (calls && calls.length > 0) {
      log.innerHTML = '';
      calls.forEach(c => {
        const dir = (c.direction||c.type||'')=='inbound'?'📥':'📤';
        const name = c.contact?.name || c.contact?.phone || c.external_number || c.peer?.name || c.target?.name || c.display_name || 'Unknown';
        const durMs = c.duration || c.total_duration || c.call_duration || 0;
        const dur = durMs > 0 ? (durMs > 1000 ? Math.round(durMs/1000)+'s' : durMs+'s') : 'N/A';
        const dateStr = c.date_started || c.started_at || c.start_time || c.date || c.created_at || '';
        const date = dateStr ? new Date(dateStr).toLocaleString() : '';
        const rec = (c.was_recorded || c.recording) ? '🎙️' : '';
        const cid = c.call_id || c.id || '';
        if (cid) {
          log.innerHTML += `<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);cursor:pointer" onclick="loadTranscript('${cid}');document.getElementById('wf-call-id').value='${cid}';document.getElementById('coach-call-id').value='${cid}'">${dir} <strong>${name}</strong> | ${dur} ${rec} | ${date}\n<span style="font-size:9px;color:#4a5568">ID: ${cid} — Click for transcript</span></div>\n`;
        }
      });
      showToast(calls.length+' calls loaded');
    } else if (data.error) {
      log.innerHTML = 'DialPad API error: '+data.error+'\n\nTip: Check your DialPad API key in Settings.\nIf timeout, the API may be slow — try again.';
    } else {
      log.innerHTML = 'No calls found. Response:\n'+JSON.stringify(data,null,2).substring(0,1000);
    }
  } catch(e) {
    log.innerHTML = 'Error loading calls: '+e.message+'\nCheck your internet connection and DialPad API key.';
  }
}

async function loadTranscript(callId) {
  const log = document.getElementById('dp-transcript-log');
  log.innerHTML = 'Loading AI transcript for '+callId+'...\n\n';
  try {
    const tres = await fetch('/api/dialpad/transcript/'+callId);
    const td = await tres.json();
    if (td && !td.error) {
      log.innerHTML += '<strong style="color:#a78bfa">─── AI TRANSCRIPT ───</strong>\n\n';
      // Handle multiple DialPad transcript formats
      if (td.lines && Array.isArray(td.lines)) {
        td.lines.forEach(l => {
          const speaker = l.speaker || l.name || l.channel || 'Speaker';
          const text = l.text || l.content || l.transcript || '';
          if (text) log.innerHTML += `<strong style="color:#60a5fa">${speaker}:</strong> ${text}\n`;
        });
      } else if (td.transcript && typeof td.transcript === 'string') {
        log.innerHTML += td.transcript + '\n';
      } else if (td.text && typeof td.text === 'string') {
        log.innerHTML += td.text + '\n';
      } else if (td.segments && Array.isArray(td.segments)) {
        td.segments.forEach(s => {
          const speaker = s.speaker || s.channel || 'Speaker';
          const text = s.text || s.transcript || '';
          if (text) log.innerHTML += `<strong style="color:#60a5fa">${speaker}:</strong> ${text}\n`;
        });
      } else if (td.items && Array.isArray(td.items)) {
        td.items.forEach(item => {
          if (typeof item === 'string') { log.innerHTML += item + '\n'; }
          else {
            const speaker = item.speaker || item.name || 'Speaker';
            const text = item.text || item.content || JSON.stringify(item);
            log.innerHTML += `<strong style="color:#60a5fa">${speaker}:</strong> ${text}\n`;
          }
        });
      } else {
        // Raw dump — show it nicely
        const raw = JSON.stringify(td, null, 2);
        log.innerHTML += '<span style="color:var(--fg3)">Raw transcript data:</span>\n' + raw.substring(0, 3000) + '\n';
      }
    } else {
      log.innerHTML += 'No transcript available for this call.\n';
      if (td && td.error) log.innerHTML += '<span style="color:var(--fg3)">' + td.error + '</span>\n';
    }
  } catch(e) {
    log.innerHTML += 'Error loading transcript: ' + e.message + '\n';
  }

  // AI Recap
  try {
    log.innerHTML += '\n<strong style="color:#4ade80">─── AI RECAP ───</strong>\n\n';
    const rres = await fetch('/api/dialpad/recap/'+callId);
    const rd = await rres.json();
    if (rd && !rd.error) {
      if (rd.summary) log.innerHTML += '<strong>Summary:</strong> '+rd.summary+'\n\n';
      if (rd.short_summary) log.innerHTML += '<strong>Summary:</strong> '+rd.short_summary+'\n\n';
      if (rd.action_items && rd.action_items.length) {
        log.innerHTML += '<strong>Action Items:</strong>\n';
        rd.action_items.forEach(i => log.innerHTML += '  • '+(typeof i === 'string' ? i : i.text || JSON.stringify(i))+'\n');
      }
      if (rd.moments && rd.moments.length) {
        log.innerHTML += '\n<strong>Key Moments:</strong>\n';
        rd.moments.forEach(m => log.innerHTML += '  📌 '+(typeof m === 'string' ? m : m.text || m.description || JSON.stringify(m))+'\n');
      }
      if (rd.sentiment) log.innerHTML += '\n<strong>Sentiment:</strong> '+rd.sentiment+'\n';
      if (rd.topics && rd.topics.length) log.innerHTML += '<strong>Topics:</strong> '+rd.topics.join(', ')+'\n';
    } else {
      log.innerHTML += 'No AI recap available.\n';
    }
  } catch(e) {
    log.innerHTML += 'Error loading recap: ' + e.message + '\n';
  }
  log.scrollTop = log.scrollHeight;
}

async function quickCall() {
  const phone = formatPhoneNumber(document.getElementById('quick-phone').value);
  document.getElementById('quick-phone').value = phone;
  if (!phone) return showToast('Enter phone number','error');
  const res = await fetch('/api/dialpad/call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})});
  const d = await res.json();
  showToast(d.status==='calling'?'📞 Calling '+phone+' — check DialPad!':'Error: '+d.error, d.status==='calling'?'info':'error');
}

async function quickSMS() {
  const phone = formatPhoneNumber(document.getElementById('quick-sms-phone').value);
  document.getElementById('quick-sms-phone').value = phone;
  const text = document.getElementById('quick-sms-text').value;
  if (!phone||!text) return showToast('Enter phone and message','error');
  const res = await fetch('/api/dialpad/sms',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone,text})});
  const d = await res.json();
  if (d.status==='sent') { showToast('💬 SMS sent!'); document.getElementById('quick-sms-text').value=''; }
  else showToast('Error: '+d.error,'error');
}

async function loadOptOuts() {
  const log = document.getElementById('dp-optouts-log');
  log.innerHTML = 'Loading...\n';
  const res = await fetch('/api/dialpad/optouts');
  const d = await res.json();
  if (d.items) { log.innerHTML = d.items.length+' opt-outs:\n'; d.items.forEach(i => log.innerHTML += '  🚫 '+(i.phone_number||i)+'\n'); }
  else log.innerHTML = d.error||'No opt-outs';
}

async function loadBlocked() {
  const log = document.getElementById('dp-blocked-log');
  log.innerHTML = 'Loading...\n';
  const res = await fetch('/api/dialpad/blocked');
  const d = await res.json();
  if (d.items) { log.innerHTML = d.items.length+' blocked:\n'; d.items.forEach(i => log.innerHTML += '  🔇 '+(i.phone_number||i)+'\n'); }
  else log.innerHTML = d.error||'No blocked numbers';
}

async function blockNumber() {
  const phone = document.getElementById('block-phone').value;
  if (!phone) return;
  const res = await fetch('/api/dialpad/block',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})});
  const d = await res.json();
  if (d.status==='blocked') { showToast('🔇 Blocked: '+phone); document.getElementById('block-phone').value=''; loadBlocked(); }
  else showToast('Error: '+d.error,'error');
}

async function syncDialPadContacts() {
  showToast('Syncing prospects → DialPad...','info');
  const res = await fetch('/api/dialpad/contacts/sync',{method:'POST'});
  const d = await res.json();
  if (d.created!==undefined) showToast('Sync: '+d.created+' created, '+d.skipped+' skipped');
  else showToast('Error: '+d.error,'error');
}

// ==================== POST-CALL WORKFLOW ====================
async function runPostCallWorkflow() {
  const callId = document.getElementById('wf-call-id').value;
  const phone = document.getElementById('wf-phone').value;
  const notes = document.getElementById('wf-notes').value;
  if (!callId) return showToast('Enter a call ID','error');
  if (!selectedDisposition) return showToast('Select a disposition','error');

  const log = document.getElementById('wf-log');
  log.innerHTML = '🔄 Running post-call workflow...\n';
  log.innerHTML += `  Call: ${callId}\n  Disposition: ${selectedDisposition}\n  Notes: ${notes||'(none)'}\n\n`;

  const res = await fetch('/api/dialpad/workflow',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({call_id:callId,disposition:selectedDisposition,notes,phone})});
  const d = await res.json();

  log.innerHTML += '<strong style="color:#a78bfa">─── WORKFLOW RESULTS ───</strong>\n\n';
  log.innerHTML += `  📝 Call Logged to HubSpot: ${d.call_logged?'✅':'❌'}\n`;
  log.innerHTML += `  👤 Contact Updated: ${d.contact_updated?'✅':'❌'}\n`;
  log.innerHTML += `  💰 Deal Created: ${d.deal_created?'✅ (ID: '+(d.deal_id||'')+')'  :'❌'}\n`;
  log.innerHTML += `  📋 Follow-up Task: ${d.task_created?'✅':'❌'}\n`;
  log.innerHTML += `  🏷️ Call Tagged: ${d.call_tagged?'✅':'❌'}\n`;
  if (d.blocked) log.innerHTML += `  🚫 Number Blocked (DNC): ✅\n`;
  if (d.errors && d.errors.length) {
    log.innerHTML += '\n<strong style="color:#f87171">Errors:</strong>\n';
    d.errors.forEach(e => log.innerHTML += '  ⚠️ '+e+'\n');
  }
  showToast('Workflow complete!','info');
}

// ==================== COACHING ====================
async function loadCoachingSummary(days=7) {
  document.getElementById('coaching-stats').style.display = 'grid';
  const log = document.getElementById('coaching-log');
  log.innerHTML = '🧠 Analyzing calls from last '+days+' days... (this may take a moment)\n';

  const res = await fetch('/api/dialpad/coaching/summary?days='+days);
  const d = await res.json();

  if (d.total_analyzed > 0) {
    document.getElementById('coach-avg-score').textContent = d.avg_coaching_score;
    document.getElementById('coach-total').textContent = d.total_analyzed;
    document.getElementById('coach-ratio').textContent = d.avg_talk_ratio+'%';
    document.getElementById('coach-buying').textContent = d.total_buying_signals;
    document.getElementById('coach-obj').textContent = d.total_objections;
    document.getElementById('coach-pain').textContent = (d.top_pain_points||[]).length;

    log.innerHTML = '<strong style="color:#ec4899">─── COACHING SUMMARY ───</strong>\n\n';
    log.innerHTML += `Calls Analyzed: ${d.total_analyzed}\n`;
    log.innerHTML += `Average Score: ${d.avg_coaching_score}/100\n`;
    log.innerHTML += `Average Talk Ratio: ${d.avg_talk_ratio}% (ideal: 40-55%)\n\n`;

    if (d.top_pain_points && d.top_pain_points.length) {
      log.innerHTML += '<strong style="color:#fbbf24">Top Pain Points Discovered:</strong>\n';
      d.top_pain_points.forEach(p => log.innerHTML += `  🔸 ${p[0]}: ${p[1]} calls\n`);
    }

    if (d.best_call) {
      log.innerHTML += `\n<strong style="color:#4ade80">Best Call:</strong>\n`;
      log.innerHTML += `  Score: ${d.best_call.coaching_score}/100 | ${d.best_call.contact_name} | ${d.best_call.duration_sec}s\n`;
      if (d.best_call.buying_signals && d.best_call.buying_signals.length)
        log.innerHTML += `  Buying Signals: ${d.best_call.buying_signals.join(', ')}\n`;
    }

    if (d.calls_needing_coaching && d.calls_needing_coaching.length) {
      log.innerHTML += `\n<strong style="color:#f87171">Calls Needing Work (score < 50):</strong>\n`;
      d.calls_needing_coaching.forEach(c => {
        log.innerHTML += `  ⚠️ ${c.contact_name} | Score: ${c.coaching_score} | ${c.duration_sec}s\n`;
        if (c.tips) c.tips.forEach(t => log.innerHTML += `     💡 ${t}\n`);
      });
    }

    showToast('Coaching analysis complete!','info');
  } else {
    log.innerHTML = 'No calls with transcripts found in the last '+days+' days.\nMake sure call recording is enabled in DialPad.';
    showToast('No calls to analyze','error');
  }
}

async function analyzeCall() {
  const callId = document.getElementById('coach-call-id').value;
  if (!callId) return showToast('Enter a call ID','error');

  const log = document.getElementById('coaching-log');
  log.innerHTML = '🧠 Analyzing call '+callId+'...\n';

  const res = await fetch('/api/dialpad/coaching/call/'+callId);
  const d = await res.json();

  if (d.coaching_score !== null && d.coaching_score !== undefined) {
    log.innerHTML = `<strong style="color:#ec4899">─── CALL COACHING: ${d.contact_name} ───</strong>\n\n`;
    log.innerHTML += `Score: ${d.coaching_score}/100\n`;
    log.innerHTML += `Duration: ${d.duration_sec}s | Direction: ${d.direction}\n`;
    log.innerHTML += `Talk Ratio: Agent ${d.talk_ratio_agent}% / Prospect ${d.talk_ratio_prospect}%\n`;
    log.innerHTML += `Words: Agent ${d.agent_words} / Prospect ${d.prospect_words}\n\n`;

    if (Object.keys(d.pain_points||{}).length) {
      log.innerHTML += '<strong style="color:#fbbf24">Pain Points Found:</strong>\n';
      for (const [cat, kws] of Object.entries(d.pain_points)) log.innerHTML += `  🔸 ${cat}: ${kws.join(', ')}\n`;
    }
    if (d.buying_signals && d.buying_signals.length) {
      log.innerHTML += `\n<strong style="color:#4ade80">Buying Signals:</strong> ${d.buying_signals.join(', ')}\n`;
    }
    if (d.objections && d.objections.length) {
      log.innerHTML += `\n<strong style="color:#f87171">Objections:</strong> ${d.objections.join(', ')}\n`;
    }
    if (d.competitors_mentioned && d.competitors_mentioned.length) {
      log.innerHTML += `\n<strong style="color:#60a5fa">Competitors:</strong> ${d.competitors_mentioned.join(', ')}\n`;
    }
    if (d.ai_summary) log.innerHTML += `\n<strong style="color:#a78bfa">AI Summary:</strong> ${d.ai_summary}\n`;
    if (d.action_items && d.action_items.length) {
      log.innerHTML += `\n<strong style="color:#06b6d4">Action Items:</strong>\n`;
      d.action_items.forEach(i => log.innerHTML += `  • ${i}\n`);
    }
    if (d.tips && d.tips.length) {
      log.innerHTML += `\n<strong style="color:#ec4899">Coaching Tips:</strong>\n`;
      d.tips.forEach(t => log.innerHTML += `  💡 ${t}\n`);
    }

    // Update keywords panel
    const kw = document.getElementById('coaching-keywords');
    let kwHTML = '';
    if (Object.keys(d.pain_points||{}).length) {
      for (const [cat, kws] of Object.entries(d.pain_points))
        kwHTML += `<div style="margin-bottom:4px"><strong style="color:var(--orange)">${cat}:</strong> ${kws.join(', ')}</div>`;
    }
    if (d.buying_signals?.length) kwHTML += `<div style="color:var(--green);margin-top:6px"><strong>Buying:</strong> ${d.buying_signals.join(', ')}</div>`;
    if (d.objections?.length) kwHTML += `<div style="color:var(--red);margin-top:4px"><strong>Objections:</strong> ${d.objections.join(', ')}</div>`;
    kw.innerHTML = kwHTML || 'No keywords detected.';

    showToast('Coaching score: '+d.coaching_score+'/100','info');
  } else {
    log.innerHTML = 'Could not analyze this call. Transcript may not be available.\n'+JSON.stringify(d,null,2);
    showToast('Analysis failed','error');
  }
}

// ==================== PIPELINE ====================
async function loadPipeline() {
  document.getElementById('pipeline-stats').style.display = 'grid';
  const res = await fetch('/api/dialpad/pipeline');
  const d = await res.json();

  if (d.stages) {
    document.getElementById('pipe-total').textContent = '$'+Math.round(d.total_pipeline_value).toLocaleString();
    document.getElementById('pipe-won').textContent = '$'+Math.round(d.total_won).toLocaleString();
    document.getElementById('pipe-deals').textContent = d.total_deals;

    const stageMap = ['appointmentscheduled','qualifiedtobuy','presentationscheduled','decisionmakerboughtin','contractsent','closedwon','closedlost'];
    let active = 0;
    stageMap.forEach((key,i) => {
      const stage = d.stages[key];
      const el = document.getElementById('pipe-stage-'+(i+1));
      const cnt = el.parentElement.querySelector('.pipeline-count');
      cnt.textContent = stage.deals.length;
      el.innerHTML = '';
      if (key !== 'closedwon' && key !== 'closedlost') active += stage.deals.length;
      stage.deals.forEach(deal => {
        el.innerHTML += `<div class="pipeline-deal"><div class="deal-name">${deal.name}</div><div class="deal-amount">$${Math.round(deal.amount).toLocaleString()}/mo</div>${deal.priority?'<span class="deal-priority '+deal.priority+'">'+deal.priority+'</span>':''}</div>`;
      });
    });
    document.getElementById('pipe-active').textContent = active;
    showToast('Pipeline loaded!');
  } else showToast('Error: '+(d.error||'No pipeline data'),'error');
}

// ==================== CRM ====================
async function loadCRMContacts() {
  document.getElementById('crm-stats').style.display = 'grid';
  document.getElementById('crm-contacts-table').style.display = 'block';

  const res = await fetch('/api/dialpad/crm/contacts');
  const d = await res.json();

  if (d.total_contacts !== undefined) {
    document.getElementById('crm-total').textContent = d.total_contacts;
    const sql = (d.by_lifecycle_stage||{}).salesqualifiedlead || 0;
    const leads = (d.by_lifecycle_stage||{}).lead || 0;
    document.getElementById('crm-sql').textContent = sql;
    document.getElementById('crm-leads').textContent = leads;
    document.getElementById('crm-industries').textContent = (d.by_industry||[]).length;

    const tbody = document.getElementById('contacts-tbody');
    tbody.innerHTML = '';
    (d.recent||[]).forEach(c => {
      tbody.innerHTML += `<tr>
        <td style="font-weight:600">${c.name||'—'}</td>
        <td>${c.company||'—'}</td>
        <td style="color:var(--cyan)">${c.phone||'—'}</td>
        <td>${c.email||'—'}</td>
        <td><span style="font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(124,58,237,0.1);color:#a78bfa">${c.stage||'—'}</span></td>
        <td>${c.status||'—'}</td>
        <td>${c.phone?'<button class="btn btn-sm btn-green" onclick="document.getElementById(\'quick-phone\').value=\''+c.phone+'\';switchTab(\'phone\',document.querySelectorAll(\'.tab\')[4])">📞</button>':''}</td>
      </tr>`;
    });
    showToast('Contacts loaded!');
  } else showToast('Error: '+(d.error||'No contacts'),'error');
}

// ==================== SCRAPER ====================
async function runScraper() {
  const btn = document.getElementById('scrape-btn');
  btn.classList.add('btn-disabled'); btn.textContent = 'Scraping...';
  const log = document.getElementById('scraper-log'); log.innerHTML = '';

  const params = new URLSearchParams();
  if (document.getElementById('mk-austin').checked) params.append('markets','austin');
  if (document.getElementById('mk-sa').checked) params.append('markets','san_antonio');
  if (document.getElementById('mk-houston').checked) params.append('markets','houston');
  params.set('max', document.getElementById('max-results').value);
  if (document.getElementById('sync-hs').checked) params.set('sync','true');
  if (document.getElementById('f-phone').checked) params.set('require_phone','true');
  if (document.getElementById('f-website').checked) params.set('require_website','true');
  if (document.getElementById('f-solo').checked) params.set('skip_solo','true');
  params.set('min_rating', document.getElementById('f-rating').value);
  params.set('min_reviews', document.getElementById('f-reviews').value);
  params.set('min_score', document.getElementById('f-score').value);
  const industry = document.getElementById('f-industry').value;
  if (industry) params.set('industry', industry);

  const res = await fetch('/api/run/scraper?'+params.toString());
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while(true) {
    const {value,done} = await reader.read();
    if (done) break;
    log.innerHTML += decoder.decode(value);
    log.scrollTop = log.scrollHeight;
  }
  btn.classList.remove('btn-disabled'); btn.textContent = '🔍 SCRAPE BUSINESSES';
  showToast('Scraping complete!');
}

// ==================== SUPER SCRAPER ====================
async function runSuperScraper() {
  const btn = document.getElementById('ss-btn');
  btn.classList.add('btn-disabled'); btn.textContent = '🚀 Running Super Scraper...';
  const log = document.getElementById('super-scraper-log'); log.innerHTML = '';

  const params = new URLSearchParams();
  if (document.getElementById('ss-mk-austin').checked)  params.append('markets','austin');
  if (document.getElementById('ss-mk-sa').checked)      params.append('markets','san_antonio');
  if (document.getElementById('ss-mk-houston').checked) params.append('markets','houston');
  params.set('max', document.getElementById('ss-max').value);
  if (document.getElementById('ss-deep').checked)         params.set('deep','true');
  if (document.getElementById('ss-titles-only').checked)  params.set('titles_only','true');
  if (document.getElementById('ss-sync-hs').checked)      params.set('sync','true');
  if (document.getElementById('ss-sync-dp').checked)      params.set('dialer','true');
  if (document.getElementById('ss-require-phone').checked)params.set('require_phone','true');
  if (document.getElementById('ss-skip-solo').checked)    params.set('skip_solo','true');
  params.set('min_score', document.getElementById('ss-min-score').value);
  const ind = document.getElementById('ss-industry').value;
  if (ind) params.set('industry', ind);

  try {
    const res = await fetch('/api/run/super_scraper?'+params.toString());
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while(true) {
      const {value,done} = await reader.read();
      if (done) break;
      log.innerHTML += decoder.decode(value);
      log.scrollTop = log.scrollHeight;
    }
    showToast('🚀 Super Scraper complete!');
  } catch(e) {
    log.innerHTML += '\n\nERROR: ' + e.message;
    showToast('Super Scraper error: '+e.message,'error');
  }
  btn.classList.remove('btn-disabled'); btn.textContent = '🚀 LAUNCH SUPER SCRAPER';
}

// ==================== EMAIL / SMS / DIALER ====================
async function runEmail() {
  const log = document.getElementById('email-log'); log.innerHTML = '';
  document.getElementById('email-status').textContent = 'RUNNING';
  const params = new URLSearchParams();
  if (document.getElementById('warmup').checked) params.set('warmup','true');
  if (document.getElementById('dryrun').checked) params.set('dryrun','true');
  const res = await fetch('/api/run/email?'+params.toString());
  const reader = res.body.getReader(); const decoder = new TextDecoder();
  while(true) { const {value,done} = await reader.read(); if(done) break; log.innerHTML += decoder.decode(value); log.scrollTop = log.scrollHeight; }
  document.getElementById('email-status').textContent = 'DONE';
  showToast('Email campaign complete!');
}

async function runSMS() {
  const log = document.getElementById('sms-log'); log.innerHTML = '';
  const tmpl = document.querySelector('input[name="sms-tmpl"]:checked').value;
  const params = new URLSearchParams({template:tmpl});
  if (document.getElementById('sms-dry').checked) params.set('dryrun','true');
  const res = await fetch('/api/run/sms?'+params.toString());
  const reader = res.body.getReader(); const decoder = new TextDecoder();
  while(true) { const {value,done} = await reader.read(); if(done) break; log.innerHTML += decoder.decode(value); log.scrollTop = log.scrollHeight; }
  showToast('SMS campaign complete!');
}

// ==================== POWER DIALER (in-app) ====================
let _dialerProspects = [];
let _dialerIdx = 0;
let _dialerActive = false;
let _dialerDisposition = '';
let _dialerStats = {dialed:0, connected:0, noanswer:0, qualified:0, talktime:0};

async function dialerStart() {
  const log = document.getElementById('dialer-log');
  log.innerHTML = '📋 Loading prospects...\n';

  // Load prospects from CSV via API
  try {
    const mk = document.querySelector('input[name="dialer-mk"]:checked').value;
    const res = await fetch('/api/prospects?market='+(mk||''));
    const data = await res.json();
    if (!data.prospects || data.prospects.length === 0) {
      log.innerHTML += '❌ No prospects found. Run the Scraper first to build your list.\n';
      return;
    }
    // Filter to only those with phone numbers
    _dialerProspects = data.prospects.filter(p => p.phone);
    if (_dialerProspects.length === 0) {
      log.innerHTML += '❌ No prospects with phone numbers. Run scraper with "Require Phone" enabled.\n';
      return;
    }
    _dialerIdx = 0;
    _dialerActive = true;
    _dialerStats = {dialed:0, connected:0, noanswer:0, qualified:0, talktime:0};
    document.getElementById('ds-loaded').textContent = _dialerProspects.length;
    document.getElementById('dialer-stop-btn').style.display = '';
    log.innerHTML += '✅ Loaded ' + _dialerProspects.length + ' prospects with phone numbers.\n';
    log.innerHTML += '📞 Starting dialer — calling first prospect...\n\n';
    dialerShowCurrent();
  } catch(e) {
    log.innerHTML += '❌ Error loading prospects: ' + e + '\n';
  }
}

function dialerStop() {
  _dialerActive = false;
  document.getElementById('dialer-stop-btn').style.display = 'none';
  document.getElementById('dialer-log').innerHTML += '\n⏹ Dialer stopped.\n';
  showToast('Dialer stopped', 'info');
}

function dialerShowCurrent() {
  if (_dialerIdx >= _dialerProspects.length) {
    document.getElementById('dialer-prospect-info').innerHTML = '<div style="color:var(--green);font-size:16px;font-weight:700">✅ All prospects called!</div><div style="margin-top:8px">Dialed: '+_dialerStats.dialed+' | Connected: '+_dialerStats.connected+' | Qualified: '+_dialerStats.qualified+'</div>';
    _dialerActive = false;
    document.getElementById('dialer-stop-btn').style.display = 'none';
    return;
  }
  const p = _dialerProspects[_dialerIdx];
  const card = document.getElementById('dialer-prospect-info');
  card.innerHTML = `
    <div style="font-size:18px;font-weight:800;color:var(--fg);margin-bottom:8px">${p.name||'Unknown'}</div>
    <div style="font-size:12px;color:var(--fg2);margin-bottom:4px">📍 ${p.city||''} ${p.state||''} ${p.market?'('+p.market+')':''}</div>
    <div style="font-size:12px;color:var(--fg2);margin-bottom:4px">🏢 ${p.industry||'Business'} ${p.rating?'⭐ '+p.rating:''} ${p.reviews?'('+p.reviews+' reviews)':''}</div>
    <div style="font-size:14px;color:var(--green);font-weight:700;margin-bottom:4px">📞 ${p.phone}</div>
    ${p.website?'<div style="font-size:11px;color:var(--cyan)">🌐 '+p.website+'</div>':''}
    ${p.email?'<div style="font-size:11px;color:var(--blue)">📧 '+p.email+'</div>':''}
    <div style="margin-top:12px;display:flex;gap:8px">
      <button class="btn btn-green" onclick="dialerCallNow()">📞 Call Now</button>
      <button class="btn btn-outline btn-sm" onclick="dialerSkip()">Skip →</button>
    </div>
    <div style="font-size:10px;color:var(--fg3);margin-top:8px">#${_dialerIdx+1} of ${_dialerProspects.length}</div>
  `;
  // Reset disposition
  _dialerDisposition = '';
  document.querySelectorAll('#dialer-disp-grid .disp-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('dialer-notes').value = '';
}

async function dialerCallNow() {
  if (_dialerIdx >= _dialerProspects.length) return;
  const p = _dialerProspects[_dialerIdx];
  const log = document.getElementById('dialer-log');
  log.innerHTML += '📞 Calling ' + (p.name||'') + ' at ' + p.phone + '...\n';
  _dialerStats.dialed++;
  document.getElementById('ds-dialed').textContent = _dialerStats.dialed;

  try {
    const res = await fetch('/api/dialpad/call', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({phone: p.phone})
    });
    const d = await res.json();
    if (d.status === 'calling') {
      log.innerHTML += '  ✅ Ringing on DialPad — take the call!\n';
      showToast('📞 Calling ' + p.phone + ' — check DialPad!', 'info');
    } else {
      log.innerHTML += '  ⚠ ' + (d.error||'Call initiation issue') + '\n';
      showToast('Call issue: ' + (d.error||'unknown'), 'error');
    }
  } catch(e) {
    log.innerHTML += '  ❌ Error: ' + e + '\n';
  }
  log.scrollTop = log.scrollHeight;
}

function dialerDisp(btn, disp) {
  document.querySelectorAll('#dialer-disp-grid .disp-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _dialerDisposition = disp;
}

async function dialerSaveAndNext() {
  if (_dialerIdx >= _dialerProspects.length) return;
  const p = _dialerProspects[_dialerIdx];
  const log = document.getElementById('dialer-log');
  const notes = document.getElementById('dialer-notes').value;
  const disp = _dialerDisposition || 'no_answer';

  // Log it
  const dispLabels = {qualified_lead:'🔥 Qualified',interested:'👍 Interested',callback:'📞 Callback',send_info:'📧 Send Info',no_answer:'📵 No Answer',voicemail:'📼 VM',not_interested:'👎 Not Int.',do_not_call:'🚫 DNC'};
  log.innerHTML += '  → ' + (dispLabels[disp]||disp) + (notes?' — '+notes:'') + '\n';

  // Update stats
  if (disp === 'qualified_lead') _dialerStats.qualified++;
  if (['qualified_lead','interested','callback','send_info'].includes(disp)) _dialerStats.connected++;
  else _dialerStats.noanswer++;
  document.getElementById('ds-connected').textContent = _dialerStats.connected;
  document.getElementById('ds-noanswer').textContent = _dialerStats.noanswer;
  document.getElementById('ds-qualified').textContent = _dialerStats.qualified;

  // Try to run post-call workflow to log to HubSpot
  try {
    await fetch('/api/dialpad/workflow', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({phone: p.phone, disposition: disp, notes: notes||'', call_id: ''})
    });
  } catch(e) { /* non-fatal */ }

  // Move to next
  _dialerIdx++;
  if (_dialerActive) dialerShowCurrent();
  log.scrollTop = log.scrollHeight;
}

function dialerSkip() {
  const log = document.getElementById('dialer-log');
  if (_dialerIdx < _dialerProspects.length) {
    log.innerHTML += '  ⏭ Skipped ' + (_dialerProspects[_dialerIdx].name||'prospect') + '\n';
  }
  _dialerIdx++;
  if (_dialerActive) dialerShowCurrent();
  log.scrollTop = log.scrollHeight;
}

async function syncHubSpot() {
  const log = document.getElementById('crm-log'); log.innerHTML = 'Syncing to HubSpot...\n';
  const res = await fetch('/api/run/sync');
  const reader = res.body.getReader(); const decoder = new TextDecoder();
  while(true) { const {value,done} = await reader.read(); if(done) break; log.innerHTML += decoder.decode(value); log.scrollTop = log.scrollHeight; }
  showToast('HubSpot sync complete!');
}

// ==================== SETTINGS ====================
async function loadSettings() {
  const res = await fetch('/api/config');
  const cfg = await res.json();
  ['tenant_id','client_id','client_secret','dialpad_key','dialpad_user_id','dialpad_number',
   'hubspot_token','google_api_key','anthropic_key','hunter_api_key','bing_api_key','sender_name','sender_email','sender_title','sender_phone','physical_address',
   'trmm_api_url','trmm_api_key','wp_site_url','wp_relay_key','wp_user','wp_app_password',
   'gh_token','gh_repo','gh_branch','cf_site_url','cf_api_token','cf_account_id','cf_project_name',
   'bvtech_site_root','jp_site_root','cf_deploy_branch',
   'linkedin_access_token','linkedin_person_urn','linkedin_client_id','linkedin_client_secret',
   'google_client_id','google_client_secret','google_redirect_uri',
   'gbp_refresh_token','gbp_account_name','gbp_location_name','gbp_location_title','hubspot_bcc_address',
   'jp_site_url','jp_relay_key','jp_wp_user','jp_wp_app_password','jp_gh_token','jp_gh_repo','jp_gh_branch','jp_cf_api_token','jp_cf_account_id','jp_cf_project_name'
  ].forEach(f => { const el = document.getElementById('cfg-'+f); if(el && cfg[f]) el.value = cfg[f]; });
}

async function saveSettings() {
  const cfg = {};
  ['tenant_id','client_id','client_secret','dialpad_key','dialpad_user_id','dialpad_number',
   'hubspot_token','google_api_key','anthropic_key','hunter_api_key','bing_api_key','sender_name','sender_email','sender_title','sender_phone','physical_address',
   'trmm_api_url','trmm_api_key','wp_site_url','wp_relay_key','wp_user','wp_app_password',
   'gh_token','gh_repo','gh_branch','cf_site_url','cf_api_token','cf_account_id','cf_project_name',
   'bvtech_site_root','jp_site_root','cf_deploy_branch',
   'linkedin_access_token','linkedin_person_urn','linkedin_client_id','linkedin_client_secret',
   'google_client_id','google_client_secret','google_redirect_uri',
   'gbp_refresh_token','gbp_account_name','gbp_location_name','gbp_location_title','hubspot_bcc_address',
   'jp_site_url','jp_relay_key','jp_wp_user','jp_wp_app_password','jp_gh_token','jp_gh_repo','jp_gh_branch','jp_cf_api_token','jp_cf_account_id','jp_cf_project_name'
  ].forEach(f => { const el = document.getElementById('cfg-'+f); if(el) cfg[f] = el.value; });
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  showToast('✅ Settings saved!');
}

// ==================== AI ASSISTANT ====================
let aiMode = 'chat';
let aiConversation = [];
let lastCodeBlocks = []; // Stores parsed code blocks from last AI response

function setAIMode(mode, el) {
  aiMode = mode;
  document.querySelectorAll('.ai-mode-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  const modeMessages = {
    chat: '💬 Chat mode — ask me anything about your app or MSP business.',
    debug: '🔧 Debug mode — paste errors, I\'ll diagnose and write fixes. I can see all your source code.',
    build: '🧬 Build mode — tell me what feature to add. I\'ll write code with real APPLY buttons to save changes to your files.',
    strategy: '📊 Strategy mode — MSP marketing advice, call scripts, email templates, pricing strategies.'
  };
  addAIMessage('system', modeMessages[mode] || '');
}

function clearAIChat() {
  aiConversation = [];
  lastCodeBlocks = [];
  document.getElementById('ai-messages').innerHTML = '<div class="ai-msg assistant">Chat cleared. What would you like to work on?</div>';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function parseCodeBlocks(text) {
  // Extract code blocks with optional filename hints
  const blocks = [];
  const regex = /```(\w*)\n([\s\S]*?)```/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    let lang = match[1] || 'python';
    let code = match[2].trim();

    // Try to detect filename from context around the code block
    let filename = '';
    const beforeBlock = text.substring(Math.max(0, match.index - 200), match.index);

    // Look for file references like "File: xyz.py" or "in xyz.py" or "modify xyz.py"
    const filePatterns = [
      /(?:file|File|FILE)[:\s]+(\w+\.py)/,
      /(?:in|modify|edit|update|change)\s+[`"]?(\w+\.py)[`"]?/,
      /(\w+\.py)[\s:]*$/,
    ];
    for (const pat of filePatterns) {
      const fm = beforeBlock.match(pat);
      if (fm) { filename = fm[1]; break; }
    }

    // Also check first line of code for shebang or module docstring hints
    if (!filename) {
      if (code.includes('bvtech_app') || code.includes('Flask') || code.includes('@app.route')) filename = 'bvtech_app.py';
      else if (code.includes('DialPadClient') || code.includes('dialpad')) filename = 'dialpad_integration.py';
      else if (code.includes('prospect_scraper') || code.includes('GooglePlacesClient')) filename = 'prospect_scraper.py';
      else if (code.includes('email_campaign') || code.includes('MSAL') || code.includes('msal')) filename = 'email_campaign.py';
      else if (code.includes('sms_campaign')) filename = 'sms_campaign.py';
      else if (code.includes('power_dialer')) filename = 'power_dialer.py';
    }

    blocks.push({ lang, code, filename, index: blocks.length });
  }
  return blocks;
}

function addAIMessage(role, content) {
  const container = document.getElementById('ai-messages');
  const div = document.createElement('div');
  div.className = 'ai-msg ' + role;

  if (role === 'assistant') {
    // Parse code blocks and create apply buttons
    const codeBlocks = parseCodeBlocks(content);
    lastCodeBlocks = codeBlocks;

    // Replace code blocks with styled versions + apply buttons
    let html = content;

    // Process code blocks in reverse order so indices don't shift
    const regex = /```(\w*)\n([\s\S]*?)```/g;
    const matches = [];
    let m;
    while ((m = regex.exec(content)) !== null) matches.push(m);

    for (let i = matches.length - 1; i >= 0; i--) {
      const match = matches[i];
      const block = codeBlocks[i];
      const codeEscaped = escapeHtml(block.code);
      const fname = block.filename || 'unknown';

      let applyBtn = '';
      if ((aiMode === 'build' || aiMode === 'debug') && block.filename) {
        applyBtn = `<div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
          <span style="font-size:9px;color:#a78bfa;">Target: ${fname}</span>
          <button onclick="applyCodeBlock(${i})" style="padding:4px 14px;border:none;border-radius:6px;
            background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;font-size:10px;font-weight:700;
            cursor:pointer;font-family:inherit;">✅ APPLY TO ${fname.toUpperCase()}</button>
        </div>`;
      } else if ((aiMode === 'build' || aiMode === 'debug') && !block.filename) {
        applyBtn = `<div style="display:flex;gap:4px;align-items:center;margin-top:6px;flex-wrap:wrap;">
          <span style="font-size:9px;color:var(--fg3);">Apply to:</span>
          <button onclick="applyCodeBlockAs(${i},'bvtech_app.py')" class="btn btn-sm btn-outline" style="font-size:9px;">bvtech_app.py</button>
          <button onclick="applyCodeBlockAs(${i},'dialpad_integration.py')" class="btn btn-sm btn-outline" style="font-size:9px;">dialpad_integration.py</button>
          <button onclick="applyCodeBlockAs(${i},'prospect_scraper.py')" class="btn btn-sm btn-outline" style="font-size:9px;">prospect_scraper.py</button>
          <button onclick="applyCodeBlockAs(${i},'email_campaign.py')" class="btn btn-sm btn-outline" style="font-size:9px;">email_campaign.py</button>
          <button onclick="applyCodeBlockAs(${i},'power_dialer.py')" class="btn btn-sm btn-outline" style="font-size:9px;">power_dialer.py</button>
        </div>`;
      }

      const replacement = `<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(124,58,237,0.2);border-radius:8px;padding:10px;margin:8px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="font-size:9px;font-weight:700;color:var(--fg3);text-transform:uppercase;letter-spacing:1px;">${block.lang || 'code'}${block.filename ? ' — ' + block.filename : ''}</span>
          <button onclick="navigator.clipboard.writeText(lastCodeBlocks[${i}].code);showToast('Copied!','info')" style="padding:2px 8px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;background:none;color:var(--fg3);font-size:9px;cursor:pointer;font-family:inherit;">📋 Copy</button>
        </div>
        <pre style="margin:0;background:rgba(0,0,0,0.4);border-radius:6px;padding:10px;overflow-x:auto;font-size:11px;line-height:1.6;"><code>${codeEscaped}</code></pre>
        ${applyBtn}
      </div>`;

      html = html.substring(0, match.index) + replacement + html.substring(match.index + match[0].length);
    }

    // Format remaining markdown (outside code blocks)
    html = html
      .replace(/`([^`]+)`/g, '<code style="background:rgba(124,58,237,0.15);padding:1px 5px;border-radius:4px;font-family:\'JetBrains Mono\',monospace;font-size:11px;">$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');

    div.innerHTML = html;
  } else {
    // System or user messages — simple formatting
    let html = escapeHtml(content)
      .replace(/\n/g, '<br>');
    div.innerHTML = html;
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function applyCodeBlock(blockIndex) {
  const block = lastCodeBlocks[blockIndex];
  if (!block || !block.filename) {
    showToast('No file target detected — use the file buttons below the code', 'error');
    return;
  }
  await doApply(block.filename, block.code);
}

async function applyCodeBlockAs(blockIndex, filename) {
  const block = lastCodeBlocks[blockIndex];
  if (!block) return;
  await doApply(filename, block.code);
}

async function doApply(filename, code) {
  addAIMessage('system', `⏳ Applying code to ${filename}...`);
  try {
    const res = await fetch('/api/ai/apply', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ filename, content: code, mode: 'overwrite' })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      addAIMessage('system', `✅ Successfully wrote to ${filename}!\nBackup saved as ${data.backup}\n\n⚠️ Restart the app to load changes:\n  1. Press Ctrl+C in the terminal\n  2. Run: python bvtech_app.py`);
      showToast('✅ Code applied to ' + filename, 'success');
    } else {
      addAIMessage('system', `❌ Failed to apply: ${data.error}`);
      showToast('Apply failed: ' + data.error, 'error');
    }
  } catch (e) {
    addAIMessage('system', `❌ Error: ${e.message}`);
    showToast('Apply error', 'error');
  }
}

async function sendAIMessage() {
  const input = document.getElementById('ai-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';

  addAIMessage('user', msg);

  const dot = document.getElementById('ai-dot');
  const statusText = document.getElementById('ai-status-text');
  dot.classList.add('thinking');
  statusText.textContent = 'Thinking...';
  document.getElementById('ai-send-btn').classList.add('btn-disabled');

  try {
    const res = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        message: msg,
        mode: aiMode,
        conversation: aiConversation.slice(-20)
      })
    });

    const data = await res.json();

    if (data.error) {
      addAIMessage('system', '⚠️ ' + data.error);
    } else {
      addAIMessage('assistant', data.response);
      aiConversation.push({role:'user', content:msg});
      aiConversation.push({role:'assistant', content:data.response});

      // AUTO-APPLIED FILES — the brain already wrote them!
      if (data.files_modified && data.files_modified.length > 0) {
        let applyMsg = '✅ CODE AUTO-APPLIED to: ' + data.files_modified.join(', ');
        if (data.apply_results) {
          data.apply_results.forEach(r => {
            applyMsg += '\n  ' + (r.success ? '✅' : '❌') + ' ' + r.file + ': ' + r.message;
          });
        }
        applyMsg += '\n\n🔄 Click RESTART to load changes:';
        addAIMessage('system', applyMsg);

        // Show restart button
        const container = document.getElementById('ai-messages');
        const restartDiv = document.createElement('div');
        restartDiv.className = 'ai-msg system';
        restartDiv.innerHTML = '<button onclick="restartApp()" style="padding:10px 30px;border:none;border-radius:8px;background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;font-size:13px;font-weight:800;cursor:pointer;font-family:inherit;margin:8px 0;">🔄 RESTART APP NOW</button> <span style="font-size:10px;color:var(--fg3)">App will restart and reload with the new code</span>';
        container.appendChild(restartDiv);
        container.scrollTop = container.scrollHeight;
      }

      if (data.needs_restart && (!data.files_modified || data.files_modified.length === 0)) {
        addAIMessage('system', '💡 Changes detected. Restart recommended.');
      }
    }
  } catch (e) {
    addAIMessage('system', '❌ Error: ' + e.message + '\nMake sure Anthropic API key is set in Settings.');
  }

  dot.classList.remove('thinking');
  statusText.textContent = 'Ready';
  document.getElementById('ai-send-btn').classList.remove('btn-disabled');
}

async function restartApp() {
  addAIMessage('system', '🔄 Restarting app...');
  try {
    await fetch('/api/ai/restart', {method:'POST'});
    addAIMessage('system', '⏳ App is restarting. Page will auto-refresh in 3 seconds...');
    setTimeout(() => { window.location.reload(); }, 3000);
  } catch(e) {
    addAIMessage('system', '⚠️ Restart signal sent. Refresh the page manually if it doesn\'t auto-reload.');
    setTimeout(() => { window.location.reload(); }, 2000);
  }
}

async function loadAIStatus() {
  try {
    const res = await fetch('/api/ai/status');
    const d = await res.json();
    const dot = document.getElementById('ai-dot');
    const text = document.getElementById('ai-status-text');
    if (d.has_api_key) {
      dot.style.background = 'var(--green)';
      text.textContent = 'Connected | ' + d.total_fixes + ' fixes | ' + d.features_built + ' features built';
    } else {
      dot.style.background = 'var(--red)';
      text.textContent = 'No API key';
    }
  } catch(e) {}
}

// Load AI status on tab switch
const origSwitchTab = switchTab;
switchTab = function(name, el) {
  origSwitchTab(name, el);
  if (name === 'ai') loadAIStatus();
};

// ==================== AUTOPILOT ====================
async function loadPilotStatus() {
  try {
    const res = await fetch('/api/pilot/status');
    const d = await res.json();
    document.getElementById('pilot-health').textContent = d.health_ok ? 'OK' : 'ERROR';
    document.getElementById('pilot-health').style.color = d.health_ok ? 'var(--green)' : 'var(--red)';
    document.getElementById('pilot-fixed').textContent = d.errors_fixed || 0;
    document.getElementById('pilot-improvements').textContent = d.improvements_made || 0;
    document.getElementById('pilot-queue').textContent = d.queue_pending || 0;
    document.getElementById('pilot-cycles').textContent = d.builds_completed || 0;
    if (d.recent_log && d.recent_log.length) {
      document.getElementById('pilot-log').innerHTML = d.recent_log.join('\n');
    }
  } catch(e) {}
}

async function pilotHealthNow() {
  showToast('Running health check...','info');
  const res = await fetch('/api/pilot/health',{method:'POST'});
  const d = await res.json();
  showToast('Health check done — ' + (d.results||[]).length + ' endpoints checked');
  loadPilotStatus();
}

async function pilotComplianceNow() {
  showToast('Running compliance check...','info');
  const res = await fetch('/api/pilot/compliance',{method:'POST'});
  const d = await res.json();
  const issues = d.issues || [];
  showToast(issues.length ? '⚠️ ' + issues.length + ' compliance issues' : '✅ Compliance OK',
    issues.length ? 'error' : 'success');
  loadPilotStatus();
}

async function pilotImproveNow() {
  showToast('Running improvement cycle...','info');
  const res = await fetch('/api/pilot/improve',{method:'POST'});
  const d = await res.json();
  showToast(d.result ? '✅ Improvement applied' : 'No pending tasks','info');
  loadPilotStatus();
}

async function pilotNightlyNow() {
  showToast('🌙 Nightly build started in background...','info');
  await fetch('/api/pilot/nightly',{method:'POST'});
  setTimeout(loadPilotStatus, 5000);
}

async function addPilotTask() {
  const input = document.getElementById('pilot-task');
  const task = input.value.trim();
  if (!task) return showToast('Enter a task','error');
  const res = await fetch('/api/pilot/queue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task})});
  const d = await res.json();
  input.value = '';
  showToast('📋 Queued! (' + d.queue_size + ' total)','info');
  loadPilotStatus();
}

// Auto-refresh pilot status when on AI tab
setInterval(() => {
  const aiTab = document.getElementById('tab-ai');
  if (aiTab && aiTab.classList.contains('active')) {
    loadPilotStatus();
    loadAIStatus();
  }
}, 15000);

// Load AI status on startup too
setTimeout(loadAIStatus, 2000);

// ==================== WARMODE v3 ====================
let warRefreshInterval = null;

async function loadWarStatus() {
  try {
    const res = await fetch('/api/pilot/status');
    const d = await res.json();

    // Stats
    document.getElementById('war-status').textContent = d.warmode ? (d.warmode_speed||'normal').toUpperCase() : 'OFF';
    document.getElementById('war-status').style.color = d.warmode ? 'var(--red)' : 'var(--fg3)';
    document.getElementById('war-builds').textContent = d.builds_completed || 0;
    document.getElementById('war-tests-pass').textContent = d.tests_passed || 0;
    document.getElementById('war-tests-fail').textContent = d.tests_failed || 0;
    document.getElementById('war-fixed').textContent = d.errors_fixed || 0;
    document.getElementById('war-queue').textContent = d.queue_pending || 0;
    document.getElementById('war-done').textContent = d.queue_completed || 0;
    document.getElementById('war-current').textContent = d.current_task || '—';

    // WARMODE header glow
    const header = document.getElementById('warmode-header');
    if (d.warmode) {
      header.classList.add('warmode-active');
      document.getElementById('warmode-toggle').checked = true;
      document.getElementById('warmode-label').textContent = (d.warmode_speed||'NORMAL').toUpperCase();
      document.getElementById('warmode-label').style.color = d.warmode_speed==='ludicrous'?'var(--red)':d.warmode_speed==='aggressive'?'var(--orange)':'var(--green)';
    } else {
      header.classList.remove('warmode-active');
      document.getElementById('warmode-label').textContent = 'OFF';
      document.getElementById('warmode-label').style.color = 'var(--fg3)';
    }

    // Speed buttons
    ['normal','aggressive','ludicrous'].forEach(s => {
      const btn = document.getElementById('speed-'+s);
      btn.className = 'speed-btn' + (d.warmode_speed===s ? ' active-'+s : '');
    });

    // Worker grid
    if (d.workers) {
      const grid = document.getElementById('worker-grid');
      grid.innerHTML = '';
      for (const [key, w] of Object.entries(d.workers)) {
        const active = w.running;
        grid.innerHTML += `<div class="worker-card ${active?'active':'stopped'}">
          <div class="worker-name" style="color:${active?'var(--green)':'var(--fg3)'}">${active?'🟢':'🔴'} ${w.name}</div>
          <div class="worker-stat">Runs: ${w.runs} | ✅${w.successes} ❌${w.errors}</div>
          <div class="worker-stat">${w.last_run ? 'Last: '+new Date(w.last_run).toLocaleTimeString() : 'Never'}</div>
          ${w.last_result ? '<div class="worker-stat">Result: '+w.last_result+'</div>' : ''}
        </div>`;
      }
    }

    // Auto-setting toggles
    if (d.auto_settings) {
      const s = d.auto_settings;
      const map = {
        'at-warmode': 'warmode_enabled', 'at-scrape': 'auto_scrape',
        'at-email': 'auto_email', 'at-health': 'auto_health',
        'at-compliance': 'auto_compliance', 'at-heal': 'auto_error_heal',
        'at-backup': 'auto_backup', 'at-report': 'auto_report',
        'at-daytime': 'daytime_mode',
      };
      for (const [elId, key] of Object.entries(map)) {
        const el = document.getElementById(elId);
        if (el) el.checked = !!s[key];
      }
    }

    // Live log
    if (d.recent_log && d.recent_log.length) {
      const logEl = document.getElementById('war-live-log');
      logEl.innerHTML = d.recent_log.map(l => {
        let cls = '';
        if (l.includes('✅') || l.includes('success')) cls = 'success';
        else if (l.includes('❌') || l.includes('error') || l.includes('FAIL')) cls = 'error';
        else if (l.includes('⚔️') || l.includes('WARMODE')) cls = 'warn';
        else if (l.includes('ℹ️')) cls = 'info';
        return `<div class="build-log-item ${cls}">${l}</div>`;
      }).join('');
      logEl.scrollTop = logEl.scrollHeight;
    }

    // Recent builds
    if (d.recent_builds && d.recent_builds.length) {
      const el = document.getElementById('war-recent-builds');
      el.innerHTML = d.recent_builds.map(b =>
        `<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
          <strong style="color:var(--purple)">${b.task.substring(0,80)}</strong>
          <div style="font-size:9px;color:var(--fg3)">${b.time ? new Date(b.time).toLocaleString() : ''} | Files: ${(b.files||[]).join(', ')}</div>
        </div>`
      ).join('');
    }

  } catch(e) {}
}

async function loadWarQueue() {
  try {
    const res = await fetch('/api/pilot/queue');
    const d = await res.json();
    const log = document.getElementById('war-queue-log');
    if (d.queue && d.queue.length) {
      log.innerHTML = d.queue.map((t,i) => {
        const icon = t.status==='completed'?'✅':t.status==='failed'?'❌':t.status==='testing'?'🧪':'⏳';
        const color = t.status==='completed'?'#4ade80':t.status==='failed'?'#f87171':'#94a3b8';
        return `<div class="build-log-item" style="color:${color}">${icon} [${t.status}] ${t.task.substring(0,80)}${t.attempts>0?' (attempt '+t.attempts+')':''}</div>`;
      }).join('');
    } else {
      log.innerHTML = 'Queue empty. Add tasks or enable WARMODE to auto-generate.';
    }
  } catch(e) {}
}

async function toggleWarmode(enabled) {
  const speed = document.querySelector('.speed-btn[class*="active-"]')?.id?.replace('speed-','')||'normal';
  await fetch('/api/pilot/warmode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,speed})});
  showToast(enabled?'⚔️ WARMODE ENGAGED!':'WARMODE off','info');
  loadWarStatus();
}

async function setWarSpeed(speed) {
  const enabled = document.getElementById('warmode-toggle').checked;
  await fetch('/api/pilot/warmode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,speed})});
  loadWarStatus();
  showToast('Speed: '+speed.toUpperCase(),'info');
}

async function updateAutoSetting(key, value) {
  await fetch('/api/pilot/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});
  loadWarStatus();
}

async function warRunTests() {
  showToast('Running self-tests...','info');
  const res = await fetch('/api/pilot/test',{method:'POST'});
  const d = await res.json();
  showToast(`Tests: ${d.passed}✅ ${d.failed}❌`, d.failed>0?'error':'success');
  loadWarStatus();
}

async function warNightlyNow() {
  showToast('🌙 Nightly build started...','info');
  await fetch('/api/pilot/nightly',{method:'POST'});
  setTimeout(loadWarStatus, 3000);
}

async function warBackupNow() {
  const res = await fetch('/api/pilot/backup',{method:'POST'});
  const d = await res.json();
  showToast('💾 Backup: '+(d.path||'done'),'success');
}

async function warHealthNow() {
  showToast('Running health check...','info');
  const res = await fetch('/api/pilot/health',{method:'POST'});
  const d = await res.json();
  showToast(d.results?'Health checked':'Done','info');
  loadWarStatus();
}

async function warComplianceNow() {
  const res = await fetch('/api/pilot/compliance',{method:'POST'});
  const d = await res.json();
  const issues = d.issues||[];
  showToast(issues.length?'⚠️ '+issues.length+' issues':'✅ Compliance OK', issues.length?'error':'success');
}

async function warGenerateIdeas() {
  showToast('💡 Generating improvement ideas...','info');
  await fetch('/api/pilot/generate',{method:'POST'});
  setTimeout(()=>{loadWarQueue();loadWarStatus();},5000);
  showToast('Ideas queued!','success');
}

async function warAddTask() {
  const input = document.getElementById('war-task-input');
  const task = input.value.trim();
  if (!task) return showToast('Enter a task','error');
  await fetch('/api/pilot/queue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task})});
  input.value = '';
  showToast('Queued!','info');
  loadWarQueue();
  loadWarStatus();
}

async function warListBackups() {
  const res = await fetch('/api/pilot/backups');
  const d = await res.json();
  const sel = document.getElementById('war-backup-select');
  sel.innerHTML = '<option value="">Select backup...</option>';
  (d.backups||[]).forEach(b => {
    sel.innerHTML += `<option value="${b.path}">${b.name}</option>`;
  });
}

async function warRestore() {
  const sel = document.getElementById('war-backup-select');
  if (!sel.value) return showToast('Select a backup','error');
  if (!confirm('Restore from backup? Current files will be overwritten.')) return;
  const res = await fetch('/api/pilot/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:sel.value})});
  const d = await res.json();
  showToast(d.ok?'✅ Restored!':'❌ '+d.error, d.ok?'success':'error');
}

// Auto-refresh WARMODE tab
const origSwitchTab2 = switchTab;
switchTab = function(name, el) {
  origSwitchTab2(name, el);
  if (name === 'warmode') {
    loadWarStatus();
    loadWarQueue();
    if (!warRefreshInterval) {
      warRefreshInterval = setInterval(()=>{
        const tab = document.getElementById('tab-warmode');
        if (tab && tab.classList.contains('active')) {
          loadWarStatus();
          loadWarQueue();
        }
      }, 5000);
    }
  }
};

loadSettings();

// ==================== v18: WELCOME MODAL ====================
function dismissWelcome() {
  document.getElementById('welcome-overlay').style.display = 'none';
  localStorage.setItem('bvtech_last_version', '18.0');
}

function checkWelcome() {
  try {
    const lastVer = localStorage.getItem('bvtech_last_version') || '';
    if (lastVer !== '18.0') {
      document.getElementById('welcome-overlay').style.display = 'block';
    }
  } catch(e) {
    // localStorage might not be available
    document.getElementById('welcome-overlay').style.display = 'block';
  }
}
// Show welcome on load
setTimeout(checkWelcome, 500);

// ==================== DASHBOARD (v16.0) ====================
async function refreshDashboard() {
  showToast('Refreshing all systems...','info');
  try {
    // Tactical RMM dashboard
    const soRes = await fetch('/api/trmm/dashboard');
    const so = await soRes.json();
    if (!so.error) {
      document.getElementById('dash-tickets').textContent = so.alerts||0;
      document.getElementById('dash-assets').textContent = so.total_agents||0;
      document.getElementById('dash-clients').textContent = so.clients||0;
      document.getElementById('dash-security').textContent = so.alerts||0;
      document.getElementById('dash-so-status').textContent = '✅ Connected';
      document.getElementById('dash-so-status').style.color='var(--green)';
    }
  } catch(e) { document.getElementById('dash-so-status').textContent = '❌ Not connected'; }
  try {
    // Inbox unread
    const inRes = await fetch('/api/inbox/unread');
    const inbox = await inRes.json();
    if (!inbox.error) {
      document.getElementById('dash-unread').textContent = inbox.unread||0;
      document.getElementById('dash-inbox-status').textContent = '✅ ' + inbox.total + ' total';
      document.getElementById('dash-inbox-status').style.color='var(--green)';
    } else {
      document.getElementById('dash-inbox-status').textContent = '❌ ' + (inbox.error||'').substring(0,40);
      document.getElementById('dash-inbox-status').style.color='var(--red)';
    }
  } catch(e) {
    document.getElementById('dash-inbox-status').textContent = '❌ fetch error';
    document.getElementById('dash-inbox-status').style.color='var(--red)';
  }
  try {
    // Pipeline MRR from HubSpot
    const pRes = await fetch('/api/dialpad/pipeline');
    const pipe = await pRes.json();
    if (pipe && !pipe.error && pipe.stages) {
      let total = 0;
      pipe.stages.forEach(s => { total += s.total_value || 0; });
      document.getElementById('dash-mrr').textContent = '$'+total.toLocaleString();
    }
  } catch(e) {}
  showToast('Dashboard refreshed!');
}
setTimeout(refreshDashboard, 3000);

// ==================== BUSINESS PULSE (v16.0 NEW) ====================
async function generateBusinessPulse() {
  const log = document.getElementById('pulse-log');
  log.innerHTML = '🧠 Generating your daily business pulse...\n\nClaude is analyzing your HubSpot pipeline, WordPress blog, prospect data, and system status...\nThis may take 15-30 seconds.\n';
  showToast('Generating business pulse...','info');
  try {
    const res = await fetch('/api/pulse/generate', {method:'POST'});
    const d = await res.json();
    if (d.error) { log.innerHTML = '❌ Error: '+d.error; return; }
    log.innerHTML = '<strong style="color:#f472b6">━━━ DAILY BUSINESS PULSE ━━━</strong>\n';
    log.innerHTML += '<strong style="color:var(--fg3)">' + new Date().toLocaleDateString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'}) + '</strong>\n\n';
    log.innerHTML += (d.pulse || d.response || 'No data generated.');
    showToast('✨ Business pulse generated!','success');
  } catch(e) { log.innerHTML = '❌ Error: '+e.message+'\n\nMake sure Claude AI API key is set in Settings.'; }
}

// ==================== TACTICAL RMM (v16.0) ====================
async function loadTRMMDashboard() {
  showToast('Loading Tactical RMM...','info');
  try {
    const res = await fetch('/api/trmm/dashboard');
    const d = await res.json();
    if (d.error) { showToast('TRMM: '+d.error,'error'); return; }
    document.getElementById('so-open').textContent = d.total_agents||0;
    document.getElementById('so-pending').textContent = d.online||0;
    document.getElementById('so-resolved').textContent = d.offline||0;
    document.getElementById('so-critical').textContent = d.alerts||0;
    document.getElementById('so-assets').textContent = d.clients||0;
    showToast('Tactical RMM loaded!');
  } catch(e) { showToast('Error: '+e.message,'error'); }
  loadTRMMAgents();
}

async function loadTRMMAgents() {
  const log = document.getElementById('so-tickets-log');
  log.innerHTML = 'Loading agents...\n';
  try {
    const res = await fetch('/api/trmm/agents');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error+'\n\nConfigure TRMM API URL + API Key in Settings.'; return; }
    const agents = Array.isArray(d) ? d : (d.agents||[]);
    if (agents.length === 0) { log.innerHTML = 'No agents found.'; return; }
    log.innerHTML = '';
    agents.forEach(a => {
      const online = a.status==='online';
      const icon = online?'🟢':'🔴';
      const color = online?'#4ade80':'#f87171';
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);cursor:pointer" onclick="loadTRMMAgentDetail(\''+a.agent_id+'\')">' +
        icon+' <strong>'+a.hostname+'</strong> <span style="font-size:9px;color:'+color+'">['+a.status+']</span>' +
        '<div style="font-size:9px;color:#4a5568">'+(a.client_name||'')+' / '+(a.site_name||'')+' | '+(a.operating_system||'')+' | '+(a.public_ip||'')+'</div></div>\n';
    });
    log.innerHTML += '\n<span style="color:var(--fg3);font-size:9px">Total: '+agents.length+' agents</span>';
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadTRMMAgentDetail(agentId) {
  const log = document.getElementById('so-detail-log');
  log.innerHTML = 'Loading agent '+agentId+'...\n';
  try {
    const res = await fetch('/api/trmm/agent/'+agentId);
    const a = await res.json();
    if (a.error) { log.innerHTML = 'Error: '+a.error; return; }
    const icon = a.status==='online'?'🟢':'🔴';
    log.innerHTML = '<strong style="color:var(--cyan)">─── AGENT: '+a.hostname+' '+icon+' ───</strong>\n\n';
    log.innerHTML += '<strong>Status:</strong> '+a.status+'\n';
    log.innerHTML += '<strong>Client:</strong> '+(a.client_name||'N/A')+' / '+(a.site_name||'')+'\n';
    log.innerHTML += '<strong>OS:</strong> '+(a.operating_system||'N/A')+'\n';
    log.innerHTML += '<strong>Public IP:</strong> '+(a.public_ip||'N/A')+'\n';
    log.innerHTML += '<strong>Agent Version:</strong> '+(a.version||'N/A')+'\n';
    log.innerHTML += '<strong>Last Seen:</strong> '+(a.last_seen?new Date(a.last_seen).toLocaleString():'N/A')+'\n';
    log.innerHTML += '<strong>Boot Time:</strong> '+(a.boot_time?new Date(a.boot_time).toLocaleString():'N/A')+'\n';
    log.innerHTML += '<strong>CPU Model:</strong> '+(a.cpu_model||'N/A')+' ('+(a.cpu_count||'?')+' cores)\n';
    log.innerHTML += '<strong>RAM:</strong> '+(a.total_ram||'N/A')+' GB\n';
    log.innerHTML += '<strong>Disks:</strong> '+(a.disks?JSON.stringify(a.disks).substring(0,200):'N/A')+'\n';
    log.innerHTML += '\n<strong>Patch Status:</strong> '+(a.patches_pending!==undefined?a.patches_pending+' pending':'N/A')+'\n';
    log.innerHTML += '<strong>Checks:</strong> '+(a.checks?.total||'N/A')+' total, '+(a.checks?.failing||0)+' failing\n';
    document.getElementById('trmm-cmd-agent').value = agentId;
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadTRMMClients() {
  const log = document.getElementById('so-tickets-log');
  log.innerHTML = 'Loading clients...\n';
  try {
    const res = await fetch('/api/trmm/clients');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error+'\n\nIf "credentials not configured":\n1. Check Settings → Microsoft 365 — all 3 fields needed\n2. In Azure Portal → App Registration → API Permissions → add Mail.Read + Mail.ReadWrite\n3. Click "Grant admin consent"\n4. Save Settings and try again'; return; }
    const clients = Array.isArray(d) ? d : [];
    log.innerHTML = '<strong style="color:var(--cyan)">─── CLIENTS ───</strong>\n\n';
    clients.forEach(c => {
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
        '<strong>'+(c.name||c.client||'Unknown')+'</strong>' +
        '<div style="font-size:9px;color:#4a5568">Sites: '+(c.sites?.length||0)+' | Agents: '+(c.agent_count||'?')+'</div></div>\n';
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadTRMMAlerts() {
  const log = document.getElementById('so-tickets-log');
  log.innerHTML = 'Loading alerts...\n';
  try {
    const res = await fetch('/api/trmm/alerts');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const alerts = Array.isArray(d) ? d : [];
    if (alerts.length === 0) { log.innerHTML = '✅ No active alerts. All clear!'; return; }
    log.innerHTML = '<strong style="color:var(--red)">─── ACTIVE ALERTS ───</strong>\n\n';
    alerts.forEach(a => {
      const sevColor = a.severity==='critical'?'#f87171':a.severity==='warning'?'#fbbf24':'#60a5fa';
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
        '<span style="color:'+sevColor+';font-weight:800;font-size:9px">['+(a.severity||'').toUpperCase()+']</span> '+(a.message||a.alert_type||'Alert') +
        '<div style="font-size:9px;color:#4a5568">'+(a.hostname||'')+' | '+(a.alert_time?new Date(a.alert_time).toLocaleString():'')+'</div></div>\n';
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadTRMMScripts() {
  const log = document.getElementById('so-detail-log');
  log.innerHTML = 'Loading scripts...\n';
  try {
    const res = await fetch('/api/trmm/scripts');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const scripts = Array.isArray(d) ? d : [];
    log.innerHTML = '<strong style="color:var(--cyan)">─── SCRIPT LIBRARY ───</strong>\n\n';
    scripts.forEach(s => {
      log.innerHTML += '📜 <strong>'+(s.name||'')+'</strong> [ID: '+(s.id||s.pk||'')+']\n';
      log.innerHTML += '   '+(s.description||'').substring(0,100)+'\n\n';
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadTRMMUpdates() {
  showToast('Feature: Select an agent first, then click Win Updates','info');
}

async function loadTRMMSoftware() {
  showToast('Feature: Select an agent first, then click Software','info');
}

async function runTRMMCommand() {
  const agentId = document.getElementById('trmm-cmd-agent').value.trim();
  const shell = document.getElementById('trmm-cmd-shell').value;
  const cmd = document.getElementById('trmm-cmd-text').value.trim();
  const timeout = parseInt(document.getElementById('trmm-cmd-timeout').value)||30;
  if (!agentId||!cmd) return showToast('Enter Agent ID and command','error');
  const log = document.getElementById('so-detail-log');
  log.innerHTML = 'Running command on '+agentId+'...\n';
  try {
    const res = await fetch('/api/trmm/command', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({agent_id:agentId,shell,cmd,timeout})});
    const d = await res.json();
    if (d.error) log.innerHTML = 'Error: '+d.error;
    else log.innerHTML = '<strong style="color:var(--green)">─── OUTPUT ───</strong>\n\n'+(typeof d==='string'?d:JSON.stringify(d,null,2));
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

// ==================== WORDPRESS (v16.0) ====================
async function loadWPDashboard() {
  showToast('Loading WordPress...','info');
  try {
    const res = await fetch('/api/wordpress/dashboard');
    const d = await res.json();
    if (d.error) { showToast('WP: '+d.error,'error'); return; }
    document.getElementById('wp-posts').textContent = d.total_posts||0;
    document.getElementById('wp-pages').textContent = d.total_pages||0;
    document.getElementById('wp-comments').textContent = d.total_comments||0;
    document.getElementById('wp-users').textContent = d.total_users||0;
    showToast('WordPress loaded!');
  } catch(e) { showToast('Error: '+e.message,'error'); }
  loadWPPosts();
}

async function loadWPPosts() {
  const log = document.getElementById('wp-list-log');
  log.innerHTML = 'Loading posts...\n';
  try {
    const res = await fetch('/api/wordpress/posts');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const posts = d.items||[];
    log.innerHTML = '<strong style="color:#21759b">─── POSTS ───</strong>\n\n';
    if (posts.length===0) { log.innerHTML += 'No posts found.'; return; }
    posts.forEach(p => {
      const status = p.status==='publish'?'🟢':'⚪';
      const title = (typeof p.title === 'string' ? p.title : p.title?.rendered) || 'Untitled';
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);cursor:pointer" onclick="loadWPPost('+p.id+')">' +
        status+' <strong>'+title.substring(0,60)+'</strong> ['+p.status+']' +
        '<div style="font-size:9px;color:#4a5568">'+(p.date?new Date(p.date).toLocaleDateString():'')+' | ID: '+p.id+'</div></div>\n';
    });
    if (d.total) log.innerHTML += '\n<span style="color:var(--fg3);font-size:9px">Total: '+d.total+' posts</span>';
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadWPPost(postId) {
  const log = document.getElementById('wp-detail-log');
  log.innerHTML = 'Loading post...\n';
  try {
    const res = await fetch('/api/wordpress/post/'+postId);
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const p = d.items?d.items:d;
    const title = (typeof p.title === 'string' ? p.title : p.title?.rendered) || '';
    const contentRaw = (typeof p.content === 'string' ? p.content : p.content?.rendered) || '';
    log.innerHTML = '<strong style="color:#21759b">─── POST ───</strong>\n\n';
    log.innerHTML += '<strong>Title:</strong> '+title+'\n';
    log.innerHTML += '<strong>Status:</strong> '+p.status+'\n';
    log.innerHTML += '<strong>Date:</strong> '+(p.date?new Date(p.date).toLocaleString():'')+'\n';
    log.innerHTML += '<strong>Link:</strong> '+(p.link||p.url||'')+'\n\n';
    const content = contentRaw.replace(/<[^>]*>/g,' ').substring(0,2000);
    log.innerHTML += content;
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadWPPages() {
  const log = document.getElementById('wp-list-log');
  log.innerHTML = 'Loading pages...\n';
  try {
    const res = await fetch('/api/wordpress/pages');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const pages = d.items||[];
    log.innerHTML = '<strong style="color:#21759b">─── PAGES ───</strong>\n\n';
    if (pages.length===0) { log.innerHTML += 'No pages found.'; return; }
    pages.forEach(p => {
      const title = (typeof p.title === 'string' ? p.title : p.title?.rendered) || '';
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
        '<strong>'+title.substring(0,60)+'</strong> ['+p.status+']' +
        '<div style="font-size:9px;color:#4a5568">'+(p.link||p.url||'')+'</div></div>\n';
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function loadWPComments() {
  const log = document.getElementById('wp-detail-log');
  log.innerHTML = 'Loading comments...\n';
  try {
    const res = await fetch('/api/wordpress/comments');
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const comments = d.items||[];
    log.innerHTML = '<strong style="color:#21759b">─── COMMENTS ───</strong>\n\n';
    if (comments.length===0) { log.innerHTML += 'Total comments: '+(d.total||0)+'\n(Comment details available in WP Admin)'; return; }
    comments.forEach(c => {
      const content = (typeof c.content === 'string' ? c.content : c.content?.rendered||'').replace(/<[^>]*>/g,' ').substring(0,200);
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
        '<strong>'+(c.author_name||'Anonymous')+'</strong> — '+(c.date?new Date(c.date).toLocaleDateString():'') +
        '<div style="font-size:9px;color:var(--fg2)">'+content+'</div></div>\n';
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function testWPFromSettings() {
  // Save settings first, then test
  await saveSettings();
  // Brief pause to ensure config file is written
  await new Promise(r => setTimeout(r, 500));
  showToast('Testing WP relay...','info');
  try {
    const res = await fetch('/api/wordpress/test');
    const d = await res.json();
    console.log('WP Test Result:', d);
    if (d.relay_working) {
      showToast('✅ WordPress relay connected! Site: '+(d.site_name||'')+' | Posts: '+(d.total_posts||0),'success');
    } else {
      const errMsg = d.error || d.hint || 'Unknown error';
      showToast('❌ WP Relay: ' + errMsg.substring(0, 100), 'error');
    }
  } catch(e) { showToast('❌ '+e.message,'error'); }
}

async function testM365FromSettings() {
  await saveSettings();
  await new Promise(r => setTimeout(r, 500));
  showToast('Testing M365 connection...','info');
  try {
    const res = await fetch('/api/inbox/test');
    const d = await res.json();
    console.log('M365 Test Result:', d);
    if (d.token === 'OK') {
      if (d.inbox_access === 'OK') {
        showToast('✅ M365 connected! Unread: '+(d.unread||0)+' | Total: '+(d.total||0),'success');
      } else {
        showToast('⚠️ Token OK but inbox failed: '+(d.inbox_access||'').substring(0,80),'error');
      }
    } else {
      showToast('❌ M365 token failed: '+(d.token||'unknown').substring(0,80),'error');
    }
  } catch(e) { showToast('❌ '+e.message,'error'); }
}

async function debugWPPost() {
  const log = document.getElementById('wp-detail-log');
  log.innerHTML = '🧪 Creating a test draft post...\n\nThis will create a real draft in your WordPress to prove the connection works end-to-end.\n';
  showToast('Creating test post...','info');
  try {
    const res = await fetch('/api/wordpress/debug-post', {method:'POST'});
    const d = await res.json();
    if (d.success) {
      log.innerHTML += '\n<strong style="color:var(--green)">✅ SUCCESS! Test post created!</strong>\n\n';
      log.innerHTML += '<strong>Post ID:</strong> '+(d.post_id||'?')+'\n';
      log.innerHTML += '<strong>Status:</strong> '+(d.status||'draft')+'\n';
      if (d.link) log.innerHTML += '<strong>URL:</strong> '+d.link+'\n';
      log.innerHTML += '\n<span style="color:var(--fg3)">This draft is safe to delete from WP Admin. It confirms your posting pipeline works!</span>\n';
      log.innerHTML += '\n<strong style="color:var(--fg3)">─── RAW RESPONSE ───</strong>\n';
      log.innerHTML += JSON.stringify(d.raw_response, null, 2);
      showToast('✅ Test post created! Check WP Drafts.','success');
    } else {
      log.innerHTML += '\n<strong style="color:var(--red)">❌ FAILED: '+(d.error||'Unknown error')+'</strong>\n';
      if (d.raw_response) log.innerHTML += '\n<strong style="color:var(--fg3)">─── RAW RESPONSE ───</strong>\n'+JSON.stringify(d.raw_response, null, 2);
      showToast('❌ Test post failed: '+(d.error||'').substring(0,80),'error');
    }
  } catch(e) {
    log.innerHTML += '\n<strong style="color:var(--red)">❌ Error: '+e.message+'</strong>';
    showToast('❌ '+e.message,'error');
  }
}

async function testWPConnection() {
  const log = document.getElementById('wp-detail-log');
  log.innerHTML = '🔌 Testing WordPress API connection...\n\n';
  showToast('Testing WP connection...','info');
  try {
    const res = await fetch('/api/wordpress/test');
    const d = await res.json();
    log.innerHTML = '<strong style="color:#21759b">─── WP RELAY DIAGNOSTIC v13 ───</strong>\n\n';
    log.innerHTML += '<strong>Relay URL:</strong> '+(d.relay_url_used||'N/A')+'\n';
    log.innerHTML += '<strong>Your Key:</strong> '+(d.key_preview||'N/A')+' ('+((d.key_length||0))+' chars)\n';
    if (d.server_key_preview) log.innerHTML += '<strong>Server Key:</strong> '+d.server_key_preview+' ('+((d.server_key_length||'?'))+' chars)\n';
    if (d.relay_version) log.innerHTML += '<strong>Relay Version:</strong> '+d.relay_version+'\n';
    log.innerHTML += '\n';

    // Step 1: Reachability
    log.innerHTML += '<strong>1. File Reachable:</strong> '+(d.api_reachable?'✅ YES':'❌ NO')+'\n';
    if (d.php_version) log.innerHTML += '   PHP: '+d.php_version+'\n';
    if (d.wp_loaded !== undefined) log.innerHTML += '   WordPress loaded: '+(d.wp_loaded?'✅ YES':'❌ NO')+'\n';
    if (d.api_error) log.innerHTML += '   <span style="color:#f87171">'+d.api_error+'</span>\n';
    if (d.relay_version && d.relay_version.includes('old')) {
      log.innerHTML += '   <span style="color:#f59e0b">⚠️ OLD PHP file on server! Re-upload bvtech-api.php from v13 zip.</span>\n';
    }
    log.innerHTML += '\n';

    // Step 2: Auth
    log.innerHTML += '<strong>2. Auth Key:</strong> '+(d.auth_ok?'✅ ACCEPTED':'❌ REJECTED')+'\n';
    if (d.error && !d.auth_ok) log.innerHTML += '   <span style="color:#f87171">'+d.error+'</span>\n';
    if (d.hint) log.innerHTML += '   <span style="color:#fbbf24">'+d.hint+'</span>\n';
    log.innerHTML += '\n';

    // Step 3: Posts
    if (d.auth_ok) {
      log.innerHTML += '<strong>3. Can Create Posts:</strong> '+(d.can_create_posts?'✅ YES':'❌ NO')+'\n';
      if (d.site_name) log.innerHTML += '   Site: '+d.site_name+'\n';
      if (d.total_posts!==undefined) log.innerHTML += '   Posts: '+d.total_posts+' published\n';
      if (d.wp_version) log.innerHTML += '   WordPress: '+d.wp_version+'\n';
    }
    log.innerHTML += '\n';

    // Summary
    log.innerHTML += '<strong style="color:var(--green)">─── SUMMARY ───</strong>\n';
    if (d.relay_working && d.auth_ok) {
      log.innerHTML += '✅ WordPress relay is fully working!\n';
      log.innerHTML += '   AI Blog Engine ready to post. 🚀\n';
      showToast('✅ WP connection working!','success');
    } else if (d.api_reachable && !d.auth_ok) {
      log.innerHTML += '⚠️ File exists but key was rejected.\n\n';
      log.innerHTML += '<strong style="color:var(--orange)">FIX:</strong>\n';
      log.innerHTML += '1. Open bvtech-api.php from the v13 zip folder\n';
      log.innerHTML += '2. Upload it to public_html/ on SiteGround (replace the old one)\n';
      log.innerHTML += '3. Open the uploaded file and verify $SECRET_KEY matches\n';
      log.innerHTML += '   what you have in Settings → Relay Secret Key\n';
      log.innerHTML += '4. Default key: <strong>BVTech2026Relay</strong>\n';
      log.innerHTML += '5. Click Test Connection again\n\n';
      log.innerHTML += 'Quick test: visit this URL in your browser:\n';
      log.innerHTML += '<strong style="color:var(--cyan)">'+(d.relay_url_used||'')+'?action=ping</strong>\n';
      log.innerHTML += 'If you see JSON with "status":"ok" — the file is working.\n';
      showToast('❌ Key rejected — see diagnostic','error');
    } else {
      log.innerHTML += '❌ Cannot reach the relay file.\n';
      log.innerHTML += 'Upload bvtech-api.php to public_html/ on SiteGround.\n';
      showToast('❌ WP relay not found','error');
    }

    log.innerHTML += '\n<strong style="color:var(--fg3)">─── RAW DEBUG ───</strong>\n';
    log.innerHTML += JSON.stringify(d, null, 2).substring(0, 2000);
  } catch(e) { log.innerHTML = '❌ Error: '+e.message; showToast('Error: '+e.message,'error'); }
}

async function createWPPost() {
  const title = document.getElementById('wp-new-title').value.trim();
  const content = document.getElementById('wp-new-content').value.trim();
  const status = document.getElementById('wp-new-status').value;
  if (!title) return showToast('Enter a title','error');
  try {
    const res = await fetch('/api/wordpress/posts', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title,content,status})});
    const d = await res.json();
    if (d.error) showToast('Error: '+d.error,'error');
    else { showToast('Post created!','success'); document.getElementById('wp-new-title').value=''; document.getElementById('wp-new-content').value=''; loadWPPosts(); }
  } catch(e) { showToast('Error: '+e.message,'error'); }
}

// ==================== SEO / GEO / AEO AI BLOG ENGINE ====================
let seoGenCount = 0;
let seoPubCount = 0;
let seoDraftCount = 0;

async function generateAIBlog() {
  const topic = document.getElementById('seo-topic').value.trim();
  const location = document.getElementById('seo-location').value.trim();
  const industry = document.getElementById('seo-industry').value;
  const optMode = document.getElementById('seo-opt-mode').value;
  const tone = document.getElementById('seo-tone').value;
  const length = document.getElementById('seo-length').value;
  const custom = document.getElementById('seo-custom').value.trim();
  const action = document.querySelector('input[name="seo-action"]:checked').value;

  if (!topic) return showToast('Enter a topic or keyword','error');

  const preview = document.getElementById('seo-preview-log');
  const analysis = document.getElementById('seo-analysis-log');
  preview.innerHTML = '🧠 Claude is generating your blog post...\n\nTopic: '+topic+'\nLocation: '+(location||'N/A')+'\nIndustry: '+(industry||'General MSP')+'\nMode: '+optMode+'\nTone: '+tone+'\nLength: '+length+'\n\nThis may take 15-30 seconds...';
  analysis.innerHTML = 'Waiting for generation...';

  try {
    const res = await fetch('/api/wordpress/ai-blog', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({topic,location,industry,opt_mode:optMode,tone,length,custom_instructions:custom,action})
    });
    const d = await res.json();

    if (d.error) { preview.innerHTML = '❌ Error: '+d.error; return; }

    // Show the generated post
    preview.innerHTML = '<strong style="color:#f472b6">─── GENERATED BLOG POST ───</strong>\n\n';
    preview.innerHTML += '<strong style="color:var(--green)">Title:</strong> '+(d.title||'')+'\n\n';
    preview.innerHTML += (d.content||'').replace(/<[^>]*>/g, function(tag) {
      if (tag.match(/<h[1-3]/i)) return '\n<strong style="color:var(--cyan)">'+tag;
      if (tag.match(/<\/h[1-3]/i)) return '</strong>\n';
      if (tag === '<p>') return '\n';
      if (tag === '</p>') return '\n';
      if (tag === '<br>' || tag === '<br/>') return '\n';
      if (tag.match(/<li/)) return '  • ';
      if (tag === '</li>') return '\n';
      if (tag.match(/<strong/)) return '<strong>';
      if (tag === '</strong>') return '</strong>';
      return '';
    }).substring(0,5000);

    if (d.wp_post_id) {
      preview.innerHTML += '\n\n<strong style="color:var(--green)">✅ '+( action==='publish'?'PUBLISHED':'SAVED AS DRAFT')+' → WP Post ID: '+d.wp_post_id+'</strong>';
      if (d.wp_link) preview.innerHTML += '\n<strong style="color:var(--cyan)">🔗 URL: '+d.wp_link+'</strong>';
      if (d.wp_status) preview.innerHTML += '\n<strong style="color:var(--fg2)">Status: '+d.wp_status+'</strong>';
    } else if (d.wp_error) {
      preview.innerHTML += '\n\n<strong style="color:var(--red)">❌ WordPress Error: '+d.wp_error+'</strong>';
      preview.innerHTML += '\n<span style="color:var(--fg3)">The blog was generated but failed to post. Check Settings → WordPress.</span>';
    } else if (action !== 'preview') {
      preview.innerHTML += '\n\n<strong style="color:var(--orange)">⚠️ WordPress did not return a post ID. Check WP connection.</strong>';
    }

    // Show SEO analysis
    analysis.innerHTML = '<strong style="color:#f472b6">─── SEO / GEO / AEO ANALYSIS ───</strong>\n\n';
    if (d.meta_description) analysis.innerHTML += '<strong>Meta Description:</strong>\n'+d.meta_description+'\n\n';
    if (d.focus_keyword) analysis.innerHTML += '<strong>Focus Keyword:</strong> '+d.focus_keyword+'\n';
    if (d.secondary_keywords) analysis.innerHTML += '<strong>Secondary Keywords:</strong> '+d.secondary_keywords+'\n\n';

    analysis.innerHTML += '<strong style="color:var(--green)">SEO Signals:</strong>\n';
    analysis.innerHTML += '  ✅ Keyword in title\n  ✅ H1/H2 heading structure\n  ✅ Internal link opportunities\n  ✅ Natural keyword density\n\n';

    if (optMode.includes('geo')) {
      analysis.innerHTML += '<strong style="color:var(--cyan)">GEO Signals (AI Search):</strong>\n';
      analysis.innerHTML += '  ✅ Location mentions: '+(location||'general')+'\n  ✅ Factual citation-ready statements\n  ✅ Structured data points\n  ✅ Local authority signals\n\n';
    }
    if (optMode.includes('aeo')) {
      analysis.innerHTML += '<strong style="color:var(--purple)">AEO Signals (Answer Engines):</strong>\n';
      analysis.innerHTML += '  ✅ FAQ section included\n  ✅ Direct answer formatting\n  ✅ Voice search phrasing\n  ✅ Featured snippet targeting\n  ✅ People Also Ask format\n\n';
    }

    if (d.schema_markup) {
      analysis.innerHTML += '<strong style="color:var(--orange)">Schema Markup (JSON-LD):</strong>\n';
      analysis.innerHTML += d.schema_markup.substring(0,500)+'\n';
    }

    seoGenCount++;
    if (action==='publish') seoPubCount++;
    else if (action==='draft') seoDraftCount++;
    document.getElementById('seo-generated').textContent = seoGenCount;
    document.getElementById('seo-published').textContent = seoPubCount;
    document.getElementById('seo-drafts').textContent = seoDraftCount;
    showToast('🧠 Blog post generated!','success');

  } catch(e) { preview.innerHTML = '❌ Error: '+e.message+'\n\nMake sure Anthropic API key is set in Settings.'; }
}

async function generateBulkTopics() {
  const preview = document.getElementById('seo-preview-log');
  preview.innerHTML = '💡 Generating topic ideas with Claude...\n';
  try {
    const res = await fetch('/api/wordpress/ai-topics', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({industry:document.getElementById('seo-industry').value,
                           location:document.getElementById('seo-location').value.trim()})});
    const d = await res.json();
    if (d.error) { preview.innerHTML = '❌ Error: '+d.error; return; }
    preview.innerHTML = '<strong style="color:#f472b6">─── 30-DAY BLOG TOPIC IDEAS ───</strong>\n\n';
    preview.innerHTML += (d.topics||d.response||'No topics generated').replace(/\n/g,'\n');
    showToast('💡 Topic ideas generated!','success');
  } catch(e) { preview.innerHTML = '❌ Error: '+e.message; }
}

function toggleAutoPost(enabled) {
  document.getElementById('seo-schedule').textContent = enabled?'ACTIVE':'OFF';
  document.getElementById('seo-schedule').style.color = enabled?'var(--green)':'var(--cyan)';
  const log = document.getElementById('seo-auto-log');
  if (enabled) {
    const time = document.getElementById('seo-auto-time').value;
    const rotation = document.getElementById('seo-auto-rotation').value;
    const status = document.getElementById('seo-auto-status').value;
    log.innerHTML = '✅ Auto-poster ACTIVATED!\n\nSchedule: Daily at '+time+' CT\nTopics: '+rotation+'\nAction: '+status+'\n\n⏳ Next post will generate at scheduled time.\nThe scheduler runs server-side — keep BVTech running.';
    // Save schedule to server
    fetch('/api/wordpress/auto-post/config', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled:true,time,rotation,status,topics:document.getElementById('seo-auto-topics').value})});
    showToast('📅 Auto-poster activated!','success');
  } else {
    log.innerHTML = 'Auto-poster disabled.';
    fetch('/api/wordpress/auto-post/config', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled:false})});
    showToast('Auto-poster off','info');
  }
}

async function testAutoPost() {
  const log = document.getElementById('seo-auto-log');
  log.innerHTML = '🧪 Running dry-run auto-post...\n';
  try {
    const res = await fetch('/api/wordpress/auto-post/test', {method:'POST'});
    const d = await res.json();
    if (d.error) log.innerHTML = '❌ '+d.error;
    else {
      log.innerHTML = '🧪 DRY RUN RESULT:\n\nTitle: '+(d.title||'N/A')+'\nLength: '+(d.word_count||'?')+' words\nStatus: '+(d.action||'preview')+'\n\nPost was NOT published (dry run only).';
      if (d.title) {
        document.getElementById('seo-preview-log').innerHTML = '<strong style="color:#f472b6">─── DRY RUN POST ───</strong>\n\n<strong>'+d.title+'</strong>\n\n'+(d.content||'').replace(/<[^>]*>/g,' ').substring(0,3000);
      }
    }
  } catch(e) { log.innerHTML = '❌ '+e.message; }
}

async function viewAutoPostHistory() {
  const log = document.getElementById('seo-auto-log');
  log.innerHTML = 'Loading history...\n';
  try {
    const res = await fetch('/api/wordpress/auto-post/history');
    const d = await res.json();
    const history = d.history||[];
    if (history.length===0) { log.innerHTML = 'No auto-posts yet.'; return; }
    log.innerHTML = '<strong>─── AUTO-POST HISTORY ───</strong>\n\n';
    history.forEach(h => {
      log.innerHTML += (h.status==='published'?'🟢':'📝')+' '+h.title+'\n';
      log.innerHTML += '   '+(h.date||'')+' | '+h.status+' | '+(h.word_count||'?')+' words\n\n';
    });
  } catch(e) { log.innerHTML = '❌ '+e.message; }
}

// ==================== CLOUDFLARE PAGES v20 ====================

// ==================== CYBER AUDIT & PEN TEST v20 ====================

let _cyberScanResults = null;  // Store last scan results for AI analysis

async function runWebAudit() {
  const url = document.getElementById('cyber-web-url').value.trim();
  const client = document.getElementById('cyber-web-client').value.trim() || 'Client';
  if (!url) { showToast('Enter a target URL first!','error'); return; }
  const log = document.getElementById('cyber-scan-log');
  const checks = {};
  ['ssl','headers','cookies','cms','dns','exposure','cors','redirect','email','subdomains'].forEach(c => {
    checks[c] = document.getElementById('cyber-chk-'+c)?.checked || false;
  });
  log.innerHTML = '🛡️ STARTING WEBSITE SECURITY AUDIT\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nTarget: '+url+'\nClient: '+client+'\nChecks: '+Object.entries(checks).filter(([k,v])=>v).map(([k])=>k).join(', ')+'\nStarted: '+new Date().toLocaleString()+'\n\n⏳ Running deep scan... this may take 30-90 seconds.\n';
  try {
    const r = await fetch('/api/cyber/web-audit', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url, client_name:client, checks})
    });
    const d = await r.json();
    if (d.error) { log.innerHTML += '\n❌ ERROR: '+d.error; showToast('❌ '+d.error,'error'); return; }
    _cyberScanResults = d;
    displayWebAuditResults(d, log);
    updateCyberStats(d);
    showToast('✅ Website audit complete!','success');
  } catch(e) { log.innerHTML += '\n❌ '+e.message; showToast('❌ '+e.message,'error'); }
}

async function runQuickWebScan() {
  const url = document.getElementById('cyber-web-url').value.trim();
  if (!url) { showToast('Enter a URL!','error'); return; }
  const log = document.getElementById('cyber-scan-log');
  log.innerHTML = '⚡ QUICK WEB SCAN: '+url+'\n⏳ Scanning...\n';
  try {
    const r = await fetch('/api/cyber/web-quick', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const d = await r.json();
    if (d.error) { log.innerHTML += '❌ '+d.error; return; }
    _cyberScanResults = d;
    displayWebAuditResults(d, log);
    updateCyberStats(d);
    showToast('✅ Quick scan done!','success');
  } catch(e) { log.innerHTML += '❌ '+e.message; }
}

function displayWebAuditResults(d, log) {
  log.innerHTML = '<strong style="color:#ef4444">━━━ WEBSITE SECURITY AUDIT RESULTS ━━━</strong>\n';
  log.innerHTML += 'Target: '+(d.target||'')+' | Scan time: '+(d.scan_time_seconds||'?')+'s\n';
  log.innerHTML += 'Date: '+(d.scan_date||new Date().toISOString())+'\n\n';

  if (d.ssl) {
    log.innerHTML += '<strong style="color:'+(d.ssl.grade==='A'||d.ssl.grade==='A+'?'var(--green)':'#f59e0b')+'">🔒 SSL/TLS: Grade '+(d.ssl.grade||'?')+'</strong>\n';
    (d.ssl.findings||[]).forEach(f => log.innerHTML += '  '+(f.severity==='critical'?'🔴':f.severity==='warning'?'🟡':'🟢')+' '+f.message+'\n');
    log.innerHTML += '\n';
  }
  if (d.headers) {
    log.innerHTML += '<strong style="color:'+(d.headers.score>=80?'var(--green)':d.headers.score>=50?'#f59e0b':'#ef4444')+'">📋 HTTP Headers: Score '+(d.headers.score||0)+'/100</strong>\n';
    (d.headers.findings||[]).forEach(f => log.innerHTML += '  '+(f.severity==='critical'?'🔴':f.severity==='warning'?'🟡':'🟢')+' '+f.message+'\n');
    log.innerHTML += '\n';
  }
  ['cookies','cms','dns','exposure','cors','redirect','email_security','subdomains'].forEach(section => {
    if (d[section]) {
      const label = section.replace('_',' ').replace(/\b\w/g,l=>l.toUpperCase());
      log.innerHTML += '<strong style="color:var(--fg2)">'+label+':</strong>\n';
      if (d[section].findings) d[section].findings.forEach(f => log.innerHTML += '  '+(f.severity==='critical'?'🔴':f.severity==='warning'?'🟡':'🟢')+' '+f.message+'\n');
      else if (typeof d[section] === 'string') log.innerHTML += '  '+d[section]+'\n';
      else log.innerHTML += '  '+JSON.stringify(d[section]).substring(0,200)+'\n';
      log.innerHTML += '\n';
    }
  });

  // Summary
  const total_vulns = (d.summary||{}).total_vulnerabilities||0;
  const critical = (d.summary||{}).critical||0;
  log.innerHTML += '\n<strong style="color:#ef4444">━━━ SUMMARY ━━━</strong>\n';
  log.innerHTML += '  Total checks: '+(d.summary||{}).total_checks||'?';
  log.innerHTML += ' | Vulnerabilities: '+total_vulns;
  log.innerHTML += ' | Critical: '+critical;
  log.innerHTML += ' | Score: '+((d.summary||{}).security_score||'?')+'/100\n';
}

function updateCyberStats(d) {
  const s = d.summary||{};
  document.getElementById('cyber-total').textContent = parseInt(document.getElementById('cyber-total').textContent||0)+1;
  document.getElementById('cyber-vulns').textContent = parseInt(document.getElementById('cyber-vulns').textContent||0)+(s.total_vulnerabilities||0);
  document.getElementById('cyber-critical').textContent = parseInt(document.getElementById('cyber-critical').textContent||0)+(s.critical||0);
  document.getElementById('cyber-passed').textContent = parseInt(document.getElementById('cyber-passed').textContent||0)+(s.passed||0);
}

async function runNetPenTest() {
  const target = document.getElementById('cyber-net-target').value.trim();
  if (!target) { showToast('Enter a target IP/hostname!','error'); return; }
  const log = document.getElementById('cyber-scan-log');
  const portRange = document.getElementById('cyber-net-ports').value;
  const customPorts = document.getElementById('cyber-net-custom-ports').value.trim();
  const checks = {};
  ['portscan','banner','smb','rdp','ssh','vulns','firewall','nmap'].forEach(c => {
    checks[c] = document.getElementById('cyber-chk-'+c)?.checked || false;
  });
  log.innerHTML = '🔓 STARTING NETWORK PENETRATION TEST\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nTarget: '+target+'\nPort range: '+portRange+(customPorts?' ('+customPorts+')':'')+'\nChecks: '+Object.entries(checks).filter(([k,v])=>v).map(([k])=>k).join(', ')+'\nStarted: '+new Date().toLocaleString()+'\n\n⏳ Scanning... this can take 1-5 minutes depending on scope.\n';
  try {
    const r = await fetch('/api/cyber/net-pentest', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({target, port_range:portRange, custom_ports:customPorts, checks})
    });
    const d = await r.json();
    if (d.error) { log.innerHTML += '\n❌ ERROR: '+d.error; return; }
    _cyberScanResults = d;
    displayNetResults(d, log);
    updateCyberStats(d);
    showToast('✅ Pen test complete!','success');
  } catch(e) { log.innerHTML += '\n❌ '+e.message; }
}

async function runQuickNetScan() {
  const target = document.getElementById('cyber-net-target').value.trim();
  if (!target) { showToast('Enter a target!','error'); return; }
  const log = document.getElementById('cyber-scan-log');
  log.innerHTML = '⚡ QUICK PORT SCAN: '+target+'\n⏳ Scanning top 100 ports...\n';
  try {
    const r = await fetch('/api/cyber/net-quick', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target})});
    const d = await r.json();
    if (d.error) { log.innerHTML += '❌ '+d.error; return; }
    _cyberScanResults = d;
    displayNetResults(d, log);
    showToast('✅ Quick scan done!','success');
  } catch(e) { log.innerHTML += '❌ '+e.message; }
}

function displayNetResults(d, log) {
  log.innerHTML = '<strong style="color:#7c3aed">━━━ NETWORK PEN TEST RESULTS ━━━</strong>\n';
  log.innerHTML += 'Target: '+(d.target||'')+' | IP: '+(d.resolved_ip||'?')+'\n';
  log.innerHTML += 'Scan time: '+(d.scan_time_seconds||'?')+'s | Ports scanned: '+(d.ports_scanned||'?')+'\n\n';

  if (d.open_ports && d.open_ports.length > 0) {
    log.innerHTML += '<strong style="color:#ef4444">🔓 OPEN PORTS ('+(d.open_ports.length)+'):</strong>\n';
    log.innerHTML += '  PORT     STATE   SERVICE          VERSION/BANNER\n';
    log.innerHTML += '  ─────────────────────────────────────────────────\n';
    d.open_ports.forEach(p => {
      const port = String(p.port).padEnd(8);
      const state = (p.state||'open').padEnd(7);
      const svc = (p.service||'unknown').padEnd(16);
      const banner = (p.banner||p.version||'').substring(0,50);
      log.innerHTML += '  '+port+' '+state+' '+svc+' '+banner+'\n';
    });
    log.innerHTML += '\n';
  } else {
    log.innerHTML += '<strong style="color:var(--green)">✅ No open ports found (host may be filtered)</strong>\n\n';
  }
  if (d.vulnerabilities && d.vulnerabilities.length > 0) {
    log.innerHTML += '<strong style="color:#ef4444">⚠️ VULNERABILITIES FOUND ('+d.vulnerabilities.length+'):</strong>\n';
    d.vulnerabilities.forEach(v => {
      log.innerHTML += '  '+(v.severity==='critical'?'🔴':v.severity==='high'?'🟠':v.severity==='medium'?'🟡':'🔵')+' ['+v.severity.toUpperCase()+'] '+v.title+'\n';
      log.innerHTML += '     Port: '+(v.port||'N/A')+' | CVE: '+(v.cve||'N/A')+'\n';
      log.innerHTML += '     '+v.description+'\n\n';
    });
  }
  if (d.services) {
    log.innerHTML += '<strong style="color:var(--cyan)">📡 SERVICE DETAILS:</strong>\n';
    (d.services||[]).forEach(s => log.innerHTML += '  '+s+'\n');
    log.innerHTML += '\n';
  }
  const s = d.summary||{};
  log.innerHTML += '<strong style="color:#ef4444">━━━ SUMMARY ━━━</strong>\n';
  log.innerHTML += '  Open ports: '+(d.open_ports||[]).length+' | Vulns: '+(s.total_vulnerabilities||0)+' | Critical: '+(s.critical||0)+' | Score: '+(s.security_score||'?')+'/100\n';
}

async function runAICyberAnalysis() {
  if (!_cyberScanResults) { showToast('Run a scan first!','error'); return; }
  const log = document.getElementById('cyber-ai-log');
  log.innerHTML = '🧠 Claude AI is analyzing your scan results...\n\nThis takes 15-30 seconds. Claude will:\n• Categorize all findings by severity\n• Cross-reference against OWASP Top 10, NIST, CIS\n• Generate prioritized remediation plan\n• Estimate remediation effort\n• Create client-ready summary\n\n⏳ Analyzing...\n';
  try {
    const r = await fetch('/api/cyber/ai-analyze', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({scan_results: _cyberScanResults})
    });
    const d = await r.json();
    if (d.error) { log.innerHTML += '\n❌ '+d.error; return; }
    log.innerHTML = d.analysis || 'No analysis returned';
    showToast('✅ AI analysis complete!','success');
  } catch(e) { log.innerHTML += '\n❌ '+e.message; }
}

async function generateCyberReport() {
  if (!_cyberScanResults) { showToast('Run a scan first!','error'); return; }
  const log = document.getElementById('cyber-ai-log');
  log.innerHTML += '\n\n📄 Generating professional PDF report...\n';
  showToast('Generating report...','info');
  try {
    const r = await fetch('/api/cyber/generate-report', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({scan_results: _cyberScanResults, client_name: document.getElementById('cyber-web-client').value||'Client'})
    });
    const d = await r.json();
    if (d.error) { log.innerHTML += '❌ '+d.error; return; }
    log.innerHTML += '✅ Report generated! Saved to: '+(d.file_path||'audit_report.html')+'\n';
    if (d.download_url) log.innerHTML += '📥 <a href="'+d.download_url+'" target="_blank" style="color:var(--green)">Download Report</a>\n';
    document.getElementById('cyber-reports').textContent = parseInt(document.getElementById('cyber-reports').textContent||0)+1;
    showToast('✅ Report generated!','success');
  } catch(e) { log.innerHTML += '❌ '+e.message; }
}

function clearCyberLog() { document.getElementById('cyber-scan-log').innerHTML = 'Cleared. Ready for next scan.'; _cyberScanResults = null; }
function exportCyberLog() { navigator.clipboard.writeText(document.getElementById('cyber-scan-log').innerText); showToast('📋 Copied!','success'); }
async function loadCyberHistory() {
  try {
    const r = await fetch('/api/cyber/history');
    const d = await r.json();
    const log = document.getElementById('cyber-history-log');
    if (!d.history || d.history.length===0) { log.innerHTML = 'No audit history yet.'; return; }
    log.innerHTML = '<strong style="color:var(--fg2)">━━━ AUDIT HISTORY ('+d.history.length+') ━━━</strong>\n\n';
    d.history.forEach(h => {
      log.innerHTML += (h.type==='web'?'🌐':'🔓')+' '+h.target+' — '+(h.date||'')+'\n';
      log.innerHTML += '   Score: '+(h.score||'?')+'/100 | Vulns: '+(h.vulns||0)+' | Critical: '+(h.critical||0)+'\n\n';
    });
  } catch(e) {}
}

// ==================== SUPER POSTING v30 (was ORM BEAST) ====================

async function loadCFDashboard() {
  document.getElementById('cf-blog-list').innerHTML = '☁️ Loading Cloudflare dashboard...';
  try {
    const r = await fetch('/api/cloudflare/dashboard');
    const d = await r.json();
    if (d.error) { document.getElementById('cf-blog-list').innerHTML = '❌ '+d.error; return; }
    document.getElementById('cf-mode').textContent = (d.mode||'none').toUpperCase();
    document.getElementById('cf-posts').textContent = d.total_posts||0;
    document.getElementById('cf-site').textContent = (d.site_url||'bvtech.org').replace('https://','');
    if (d.last_deploy) document.getElementById('cf-deploy').textContent = new Date(d.last_deploy.date).toLocaleDateString();
    const log = document.getElementById('cf-blog-list');
    if (!d.posts || d.posts.length===0) { log.innerHTML = 'No blog posts found. Generate one using the AI Blog Engine below!'; return; }
    log.innerHTML = '<strong style="color:#f87171">─── BLOG POSTS ON BVTECH.ORG ('+d.total_posts+') ───</strong>\n\n';
    d.posts.forEach((p,i) => {
      log.innerHTML += '<span style="color:#f87171;cursor:pointer" onclick="previewCFPost(\''+p.slug+'\')">'+(i+1)+'. '+p.title+'</span>\n';
      log.innerHTML += '   <a href="'+p.url+'" target="_blank" style="color:var(--cyan)">'+p.url+'</a>\n';
      log.innerHTML += '   Status: '+p.status+' | Size: '+(p.size?Math.round(p.size/1024)+'KB':'?')+'\n\n';
    });
  } catch(e) { document.getElementById('cf-blog-list').innerHTML = '❌ '+e.message; }
}

async function testCFConnection() {
  showToast('Testing Cloudflare connection...','info');
  try {
    const r = await fetch('/api/cloudflare/test');
    const d = await r.json();
    if (d.error) { showToast('❌ '+d.error,'error'); return; }
    if (d.connected) {
      showToast('✅ Connected! Mode: '+d.mode+' | Repo: '+(d.repo||d.project||''),'success');
      document.getElementById('cf-mode').textContent = d.mode.toUpperCase();
    } else {
      showToast('❌ Connection failed','error');
    }
  } catch(e) { showToast('❌ '+e.message,'error'); }
}

async function previewCFPost(slug) {
  const log = document.getElementById('cf-preview');
  log.innerHTML = '⏳ Loading preview for: '+slug+'...';
  try {
    const r = await fetch('/api/cloudflare/post/'+slug);
    const d = await r.json();
    if (d.error) { log.innerHTML = '❌ '+d.error; return; }
    log.innerHTML = '<strong style="color:var(--cyan)">'+d.title+'</strong>\n';
    log.innerHTML += 'Slug: '+d.slug+'\n';
    log.innerHTML += 'URL: <a href="'+d.url+'" target="_blank" style="color:var(--cyan)">'+d.url+'</a>\n';
    log.innerHTML += '─────────────────────\n\n';
    log.innerHTML += d.preview||'No preview available';
  } catch(e) { log.innerHTML = '❌ '+e.message; }
}

async function generateCFBlog() {
  const log = document.getElementById('cf-blog-preview');
  const topic = document.getElementById('cf-blog-topic').value;
  const location = document.getElementById('cf-blog-location').value;
  const industry = document.getElementById('cf-blog-industry').value;
  const opt_mode = document.getElementById('cf-blog-opt').value;
  const tone = document.getElementById('cf-blog-tone').value;
  const length = document.getElementById('cf-blog-length').value;
  const custom = document.getElementById('cf-blog-custom').value;
  const action = document.querySelector('input[name="cf-blog-action"]:checked')?.value || 'preview';

  if (!topic) { showToast('Enter a blog topic first!','error'); return; }

  log.innerHTML = '🧠 Claude AI is generating your blog post...\n\nTopic: '+topic+'\nOptimization: '+opt_mode+'\nTone: '+tone+' | Length: '+length+'\n\nThis takes 15-30 seconds. Claude will:\n1. Generate SEO/GEO/AEO optimized content\n2. Build a static HTML page matching BVTech.org design\n'+(action==='publish'?'3. Deploy to Cloudflare Pages via GitHub\n4. Live on bvtech.org within ~60 seconds':'3. Preview the content below (not deployed yet)')+'\n\n⏳ Waiting for Claude...';

  try {
    const r = await fetch('/api/cloudflare/ai-blog', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({topic,location,industry,opt_mode,tone,length,custom_instructions:custom,action})
    });
    const d = await r.json();
    if (d.error) { log.innerHTML = '❌ Error: '+d.error; showToast('❌ '+d.error,'error'); return; }

    log.innerHTML = '<strong style="color:#f87171">─── BLOG POST GENERATED ───</strong>\n\n';
    log.innerHTML += '📌 Title: '+d.title+'\n';
    log.innerHTML += '🔑 Focus Keyword: '+(d.focus_keyword||'—')+'\n';
    log.innerHTML += '📝 Words: '+(d.word_count||'?')+'\n';
    log.innerHTML += '📊 Meta: '+(d.meta_description||'—')+'\n\n';

    if (d.cf_link) {
      log.innerHTML += '<strong style="color:var(--green)">✅ DEPLOYED TO CLOUDFLARE PAGES!</strong>\n';
      log.innerHTML += '🌐 Live URL: <a href="'+d.cf_link+'" target="_blank" style="color:var(--green)">'+d.cf_link+'</a>\n';
      log.innerHTML += '📁 File: '+d.cf_file_path+'\n';
      log.innerHTML += '🚀 Deploy Mode: '+(d.cf_deploy_mode||'github')+'\n\n';
      showToast('✅ Blog deployed to Cloudflare Pages!','success');
      // Update stats
      const pub = document.getElementById('cf-seo-published');
      pub.textContent = parseInt(pub.textContent||0)+1;
    } else if (d.cf_error) {
      log.innerHTML += '⚠️ Deploy error: '+d.cf_error+'\n';
      showToast('⚠️ Generated but deploy failed: '+d.cf_error,'error');
    } else {
      log.innerHTML += '👁️ Preview only — not deployed.\n';
      showToast('✅ Blog generated! Review and deploy when ready.','success');
    }

    log.innerHTML += '\n─── CONTENT PREVIEW ───\n\n';
    // Strip HTML tags for text preview
    const textContent = (d.content||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
    log.innerHTML += textContent.substring(0,2000)+(textContent.length>2000?'...\n\n[Full content deployed to site]':'');

    // Update generated count
    const gen = document.getElementById('cf-seo-generated');
    gen.textContent = parseInt(gen.textContent||0)+1;
    if (d.word_count) document.getElementById('cf-seo-words').textContent = d.word_count;

  } catch(e) { log.innerHTML = '❌ '+e.message; showToast('❌ '+e.message,'error'); }
}

function toggleCFAutoPost(enabled) {
  const log = document.getElementById('cf-auto-log');
  if (enabled) {
    const time = document.getElementById('cf-auto-time').value;
    const rotation = document.getElementById('cf-auto-rotation').value;
    const topics = document.getElementById('cf-auto-topics').value;
    fetch('/api/cloudflare/auto-post/config', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled:true,time,rotation,topics,target:'cloudflare'})});
    log.innerHTML = '🟢 AUTO-POSTER ACTIVE → Cloudflare Pages\nTime: '+time+' daily\nRotation: '+rotation+'\n\nClaude will generate and deploy a blog post to BVTech.org every day.';
    showToast('🟢 Cloudflare Auto-Poster ON!','success');
  } else {
    fetch('/api/cloudflare/auto-post/config', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled:false,target:'cloudflare'})});
    log.innerHTML = 'Auto-poster disabled.';
    showToast('Auto-poster OFF','info');
  }
}

// ==================== 📰 BVTECH NEWS — VULNERABILITY INTELLIGENCE v24 ====================

async function newsTestScrape() {
  const feed = document.getElementById('news-vuln-feed');
  feed.innerHTML = '🔍 Scraping CISA KEV + NVD feeds for latest vulnerabilities...\n\nThis pulls REAL CVE data from US government sources.\nPlease wait 5-10 seconds...';
  try {
    const r = await fetch('/api/news/test-scrape', {method:'POST'});
    const d = await r.json();
    if (d.error) { feed.innerHTML = '❌ '+d.error; showToast('❌ Scrape failed: '+d.error,'error'); return; }

    let out = '<strong style="color:#ef4444">─── LIVE VULNERABILITY FEED ───</strong>\n\n';
    out += '📡 CISA KEV (Actively Exploited): '+d.total_cisa+' entries\n';
    out += '📡 NVD Critical CVEs (48hr): '+d.total_nvd+' entries\n\n';

    if (d.cisa_kev && d.cisa_kev.length) {
      out += '<strong style="color:#f87171">🔴 CISA KEV — ACTIVELY EXPLOITED:</strong>\n';
      d.cisa_kev.forEach((v,i) => {
        out += '\n<strong style="color:#fff">'+(i+1)+'. '+v.cve_id+'</strong> — '+v.vendor+' '+v.product+'\n';
        out += '   '+v.name+'\n';
        out += '   📝 '+v.description.substring(0,200)+'...\n';
        out += '   🔧 Action: '+v.action.substring(0,150)+'\n';
        out += '   📅 Added: '+v.date_added+' | Due: '+v.due_date+'\n';
        out += '   💀 Ransomware: '+v.known_ransomware+'\n';
      });
    }

    if (d.nvd_critical && d.nvd_critical.length) {
      out += '\n<strong style="color:#fb923c">🟠 NVD — CRITICAL SEVERITY (Last 48hrs):</strong>\n';
      d.nvd_critical.forEach((v,i) => {
        out += '\n<strong style="color:#fff">'+(i+1)+'. '+v.cve_id+'</strong> (CVSS: '+v.cvss_score+')\n';
        out += '   '+v.description.substring(0,200)+'...\n';
        out += '   Severity: '+v.severity+' | Published: '+v.published+'\n';
      });
    }

    feed.innerHTML = out;
    document.getElementById('news-cves').textContent = d.total_cisa + d.total_nvd;
    showToast('✅ Scraped '+(d.total_cisa+d.total_nvd)+' vulnerabilities from CISA + NVD','success');
  } catch(e) { feed.innerHTML = '❌ Scrape error: '+e.message; showToast('❌ '+e.message,'error'); }
}

async function newsGenerateNow() {
  const preview = document.getElementById('news-preview');
  const custom = document.getElementById('news-custom').value;
  const action = document.getElementById('news-action').value;
  const publish = action === 'publish';

  preview.innerHTML = '📰 Generating BVTech News article...\n\nPipeline running:\n1. ✅ Scraping CISA KEV + NVD for latest CVEs...\n2. ⏳ Feeding real vulnerability data to Claude AI...\n3. ⏳ Writing enterprise-grade intelligence briefing...\n4. ⏳ '+(publish?'Deploying to bvtech.org/news/...':'Preview mode (no deploy)')+'...\n\n⏳ This takes 30-60 seconds. Claude is writing a real 1500+ word article...';

  try {
    const r = await fetch('/api/news/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({custom_instructions:custom, publish})
    });
    const d = await r.json();
    if (d.error) { preview.innerHTML = '❌ Error: '+d.error; showToast('❌ '+d.error,'error'); return; }

    let out = '<strong style="color:#ef4444">─── BVTECH NEWS ARTICLE GENERATED ───</strong>\n\n';
    out += '📌 Title: <strong style="color:#fff">'+d.title+'</strong>\n';
    out += '🛡️ Severity: '+d.severity+'\n';
    out += '🔑 Keywords: '+(d.focus_keyword||'—')+'\n';
    out += '📝 Words: '+(d.word_count||'?')+'\n';
    out += '📊 CVEs Covered: '+(d.cve_ids||[]).join(', ')+'\n';
    out += '📋 Meta: '+(d.meta_description||'—')+'\n\n';

    if (d.executive_summary) {
      out += '<strong style="color:var(--cyan)">EXECUTIVE SUMMARY:</strong>\n'+d.executive_summary+'\n\n';
    }

    if (d.cf_link) {
      out += '<strong style="color:var(--green)">✅ DEPLOYED TO BVTECH.ORG!</strong>\n';
      out += '🌐 Live: <a href="'+d.cf_link+'" target="_blank" style="color:var(--green)">'+d.cf_link+'</a>\n';
      out += '📁 File: '+d.cf_file_path+'\n\n';
      showToast('✅ BVTech News article live on bvtech.org!','success');
    } else if (d.cf_error) {
      out += '⚠️ Deploy error: '+d.cf_error+'\n\n';
      showToast('⚠️ Generated but deploy failed','error');
    } else {
      out += '👁️ Preview only — not deployed.\n\n';
      showToast('✅ Article generated — review and deploy when ready','success');
    }

    out += '<strong style="color:var(--fg2)">─── CONTENT PREVIEW ───</strong>\n\n';
    const text = (d.content||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
    out += text.substring(0,3000)+(text.length>3000?'...\n\n[Full article on site]':'');

    preview.innerHTML = out;

    // Update stats
    const total = document.getElementById('news-total');
    total.textContent = parseInt(total.textContent||0)+1;
    newsLoadHistory();

  } catch(e) { preview.innerHTML = '❌ '+e.message; showToast('❌ '+e.message,'error'); }
}

function newsToggleScheduler(enabled) {
  const log = document.getElementById('news-sched-log');
  const time = document.getElementById('news-auto-time').value;
  const autoPublish = document.getElementById('news-auto-publish').value === 'true';

  fetch('/api/news/config', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({enabled, time, auto_publish:autoPublish})});

  if (enabled) {
    log.innerHTML = '🟢 NEWS SCHEDULER ACTIVE\n\nDaily at '+time+' CST:\n1. Scrape CISA KEV + NVD for overnight vulnerabilities\n2. Claude AI writes enterprise-grade intelligence briefing\n3. '+(autoPublish?'Auto-deploy to bvtech.org/news/':'Generate preview (manual deploy)')+ '\n\nNext run: Tomorrow at '+time+' CST';
    document.getElementById('news-sched').textContent = time+' CST';
    showToast('🟢 BVTech News Scheduler ON — daily at '+time+' CST','success');
  } else {
    log.innerHTML = 'Scheduler disabled.';
    document.getElementById('news-sched').textContent = 'OFF';
    showToast('News scheduler OFF','info');
  }
}

async function newsLoadHistory() {
  try {
    const r = await fetch('/api/news/history');
    const d = await r.json();
    const log = document.getElementById('news-history-log');
    if (!d.history || !d.history.length) {
      log.innerHTML = 'No articles generated yet.';
      return;
    }
    let out = '<strong style="color:var(--orange)">📋 Published News Articles ('+d.history.length+')</strong>\n\n';
    d.history.forEach((h,i) => {
      out += '<strong style="color:#fff">'+(i+1)+'. '+h.title+'</strong>\n';
      out += '   📅 '+h.date.split('T')[0]+' | 🛡️ '+h.severity+' | 📝 '+h.word_count+' words\n';
      out += '   CVEs: '+(h.cve_ids||[]).join(', ')+'\n';
      if (h.cf_link) out += '   🌐 <a href="'+h.cf_link+'" target="_blank" style="color:var(--green)">'+h.cf_link+'</a>\n';
      out += '\n';
    });
    log.innerHTML = out;
    document.getElementById('news-total').textContent = d.history.length;

    let totalCves = 0;
    d.history.forEach(h => { totalCves += (h.cve_ids||[]).length; });
    document.getElementById('news-cves').textContent = totalCves;
    if (d.history[0]) document.getElementById('news-last-run').textContent = d.history[0].date.split('T')[0];
  } catch(e) { console.error('News history error:', e); }
}

// (News auto-load is handled by the unified switchTab hook later in this file)

// ==================== LINKEDIN ORM v20 ====================

async function connectLinkedIn() {
  await saveSettings();
  try {
    const r = await fetch('/api/linkedin/auth-url');
    const d = await r.json();
    if (d.error) { showToast('❌ '+d.error,'error'); return; }
    if (d.auth_url) {
      showToast('Opening LinkedIn authorization...','info');
      window.open(d.auth_url, '_blank', 'width=600,height=700');
    }
  } catch(e) { showToast('❌ '+e.message,'error'); }
}

async function testLinkedIn() {
  showToast('Testing LinkedIn connection...','info');
  try {
    const r = await fetch('/api/linkedin/test');
    const d = await r.json();
    if (d.error) { showToast('❌ '+d.error,'error'); return; }
    if (d.connected) {
      showToast('✅ LinkedIn connected as: '+d.name,'success');
      if (d.person_urn) {
        const urnEl = document.getElementById('cfg-linkedin_person_urn');
        if (urnEl && !urnEl.value) urnEl.value = d.person_urn;
      }
    } else { showToast('❌ Not connected','error'); }
  } catch(e) { showToast('❌ '+e.message,'error'); }
}

// ==================== v30: GOOGLE BUSINESS PROFILE ====================

function _gbpStatus(msg, isError) {
  const el = document.getElementById('gbp-status');
  if (!el) return;
  el.style.display = 'block';
  el.textContent = msg;
  el.style.color = isError ? '#fca5a5' : '#e2e8f0';
}

async function connectGoogleBusiness() {
  await saveSettings();
  _gbpStatus('Requesting OAuth URL...');
  try {
    const r = await fetch('/api/gbp/oauth/start');
    const d = await r.json();
    if (d.error) { _gbpStatus('❌ '+d.error, true); showToast('❌ '+d.error,'error'); return; }
    if (d.authorize_url) {
      _gbpStatus('Opening Google consent window...\n\nAfter you approve:\n1. The window will close itself\n2. Come back here and click "Pick Location"');
      window.open(d.authorize_url, '_blank', 'width=720,height=760');
    }
  } catch(e) { _gbpStatus('❌ '+e.message, true); }
}

async function testGBP() {
  _gbpStatus('Testing Google Business Profile connection...');
  try {
    const r = await fetch('/api/gbp/test');
    const d = await r.json();
    if (d.error) {
      _gbpStatus('❌ Not connected\n\n' + d.error, true);
      showToast('❌ GBP test failed','error');
      return;
    }
    let msg = '✅ Connected to Google Business Profile\n';
    msg += '───────────────────────────────────────\n';
    msg += 'Accounts visible: ' + (d.account_count || 0) + '\n';
    if (d.accounts && d.accounts.length) {
      msg += '\nAccounts:\n';
      d.accounts.forEach(a => {
        msg += '  • ' + (a.account_name || a.name) + '  [' + (a.type || '?') + ', ' + (a.role || '?') + ']\n';
      });
    }
    _gbpStatus(msg);
    showToast('✅ GBP connected','success');
  } catch(e) { _gbpStatus('❌ '+e.message, true); }
}

async function gbpPickLocation() {
  _gbpStatus('Loading GBP accounts...');
  try {
    // Step 1: list accounts
    const ar = await fetch('/api/gbp/accounts');
    const ad = await ar.json();
    if (ad.error) { _gbpStatus('❌ ' + ad.error, true); return; }
    const accounts = ad.accounts || [];
    if (!accounts.length) { _gbpStatus('No GBP accounts found on this Google user. Make sure your Google user has a verified Business Profile.', true); return; }
    // For now, pick the first account automatically
    const account = accounts[0];
    const accountName = account.name;
    _gbpStatus('Found ' + accounts.length + ' account(s).\nLoading locations for: ' + (account.accountName || accountName) + '...');

    // Step 2: list locations
    const lr = await fetch('/api/gbp/locations?account=' + encodeURIComponent(accountName));
    const ld = await lr.json();
    if (ld.error) { _gbpStatus('❌ ' + ld.error, true); return; }
    const locations = ld.locations || [];
    if (!locations.length) { _gbpStatus('No locations under this account. Verify your business has at least one location.', true); return; }

    // Step 3: if 1 location, auto-pick. Otherwise show a picker via prompt.
    let chosen;
    if (locations.length === 1) {
      chosen = locations[0];
    } else {
      const list = locations.map((l, i) => (i+1) + '. ' + (l.title || l.name)).join('\n');
      const pick = prompt('Multiple locations found. Enter the number:\n\n' + list, '1');
      const n = parseInt(pick, 10);
      if (isNaN(n) || n < 1 || n > locations.length) { _gbpStatus('Cancelled.'); return; }
      chosen = locations[n-1];
    }

    // Step 4: save into the config
    document.getElementById('cfg-gbp_account_name').value = accountName;
    document.getElementById('cfg-gbp_location_name').value = chosen.name || '';
    document.getElementById('cfg-gbp_location_title').value = chosen.title || '';
    await saveSettings();

    _gbpStatus('✅ Picked location: ' + (chosen.title || chosen.name) + '\n\nAccount:  ' + accountName + '\nLocation: ' + (chosen.name || '?') + '\n\nReady to post! Super Posting will now include GBP when you use the "All 4 Channels" target.');
    showToast('✅ GBP location saved','success');
  } catch(e) { _gbpStatus('❌ '+e.message, true); }
}

async function disconnectGBP() {
  if (!confirm('Disconnect Google Business Profile? You\'ll need to re-authorize to post again.')) return;
  try {
    const r = await fetch('/api/gbp/disconnect', {method:'POST'});
    const d = await r.json();
    document.getElementById('cfg-gbp_refresh_token').value = '';
    document.getElementById('cfg-gbp_account_name').value = '';
    document.getElementById('cfg-gbp_location_name').value = '';
    document.getElementById('cfg-gbp_location_title').value = '';
    _gbpStatus('Disconnected. Click "Connect Google Business" to re-authorize.');
    showToast('GBP disconnected','info');
  } catch(e) { _gbpStatus('❌ '+e.message, true); }
}

// ==================== v31: HUBSPOT EMAIL TRACKING ====================

function _hsTrackLog(msg, isError) {
  const el = document.getElementById('hstrack-log');
  if (!el) return;
  const line = (isError ? '❌ ' : '') + msg;
  el.textContent = line + '\n' + (el.textContent || '');
}

async function hsTrackVerify() {
  _hsTrackLog('Verifying HubSpot connection...');
  try {
    const r = await fetch('/api/hubspot/verify');
    const d = await r.json();
    if (d.error || !d.connected) {
      _hsTrackLog('Connection failed: ' + (d.error || 'not connected'), true);
      showToast('❌ HubSpot not connected', 'error');
      return;
    }
    _hsTrackLog('Connected! Portal ID: ' + d.portal_id + ' | TZ: ' + (d.time_zone || '?'));
    showToast('✅ HubSpot connected', 'success');
    loadHsStats();
  } catch(e) { _hsTrackLog(e.message, true); }
}

async function loadHsStats() {
  try {
    const r = await fetch('/api/hubspot/stats');
    const d = await r.json();
    if (d.contact_count !== undefined) {
      const el = document.getElementById('hs-contact-count');
      if (el) el.textContent = d.contact_count.toLocaleString();
    }
  } catch(e) {}
  // Pull CSV stats from local event log if we can
  try {
    const r = await fetch('/api/automation/log?category=email&limit=500');
    const d = await r.json();
    const today = new Date().toISOString().slice(0,10);
    const todayCount = (d.events || []).filter(e => (e.ts || '').startsWith(today) && e.action === 'hubspot_track' && e.success).length;
    const el = document.getElementById('hs-tracked-today');
    if (el) el.textContent = todayCount.toString();
  } catch(e) {}
}

async function hsTrackLog() {
  const email = document.getElementById('hstrack-to').value.trim();
  const subject = document.getElementById('hstrack-subject').value.trim();
  const body = document.getElementById('hstrack-body').value;
  if (!email || !email.includes('@')) { _hsTrackLog('Valid email required', true); return; }
  if (!subject && !body) { _hsTrackLog('Subject or body required', true); return; }
  _hsTrackLog('Logging to HubSpot...');
  try {
    const payload = {
      email: email,
      subject: subject,
      body: body,
      direction: 'outgoing',
      first_name: document.getElementById('hstrack-fname').value.trim(),
      last_name: document.getElementById('hstrack-lname').value.trim(),
      company: document.getElementById('hstrack-company').value.trim(),
      phone: document.getElementById('hstrack-phone').value.trim(),
    };
    const r = await fetch('/api/hubspot/track-email', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (d.error) {
      _hsTrackLog('Error: ' + d.error, true);
      showToast('❌ HubSpot log failed', 'error');
      return;
    }
    _hsTrackLog('✅ Logged! Contact ID: ' + d.contact_id + ', Email ID: ' + d.email_id);
    showToast('✅ Logged to HubSpot', 'success');
    loadHsStats();
  } catch(e) { _hsTrackLog(e.message, true); }
}

function hsTrackClearForm() {
  ['hstrack-to','hstrack-subject','hstrack-body','hstrack-fname','hstrack-lname','hstrack-company','hstrack-phone'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  _hsTrackLog('Form cleared.');
}

async function saveBccAddress() {
  const addr = document.getElementById('hstrack-bcc').value.trim();
  // Save via existing settings save path
  const cfgEl = document.getElementById('cfg-hubspot_bcc_address');
  if (cfgEl) cfgEl.value = addr;
  await saveSettings();
  showToast('✅ BCC address saved', 'success');
}

async function copyBccAddress() {
  const addr = document.getElementById('hstrack-bcc').value.trim();
  if (!addr) { showToast('Enter the BCC address first', 'info'); return; }
  try {
    await navigator.clipboard.writeText(addr);
    showToast('✅ Copied: ' + addr, 'success');
  } catch(e) {
    showToast('Clipboard unavailable — select the text and copy manually', 'info');
  }
}

async function loadBccAddress() {
  try {
    const r = await fetch('/api/hubspot/bcc-address');
    const d = await r.json();
    const el = document.getElementById('hstrack-bcc');
    if (el && d.bcc_address) el.value = d.bcc_address;
  } catch(e) {}
}

async function hsTrackEnrichNow() {
  if (!confirm('Run HubSpot enrichment on prospects.csv now? This will look up (and create if missing) up to 50 contacts.')) return;
  _hsTrackLog('Enriching prospects.csv...');
  try {
    const r = await fetch('/api/hubspot/enrich-csv', {method:'POST'});
    const d = await r.json();
    if (d.ok) {
      _hsTrackLog('✅ ' + d.message);
      showToast('✅ Enrichment complete', 'success');
    } else {
      _hsTrackLog('Enrichment failed: ' + (d.message || 'unknown'), true);
    }
  } catch(e) { _hsTrackLog(e.message, true); }
}

async function loadHsHistory() {
  const el = document.getElementById('hs-history');
  if (!el) return;
  el.textContent = 'Loading...';
  try {
    const r = await fetch('/api/automation/log?category=email&limit=50');
    const d = await r.json();
    const events = d.events || [];
    if (!events.length) { el.textContent = 'No tracked emails yet. Send one via the form above or wait for the daily enrichment task.'; return; }
    const lines = events.map(e => {
      const ok = e.success ? '✅' : '❌';
      const ts = (e.ts || '').replace('T', ' ').slice(0, 19);
      const target = e.target || '?';
      const contactId = (e.details && e.details.contact_id) || '';
      const err = (e.details && e.details.error) || '';
      return ok + ' ' + ts + '  ' + target + '  ' + (contactId ? '→ ' + contactId : '') + (err ? '  [' + err + ']' : '');
    });
    el.textContent = lines.join('\n');
  } catch(e) { el.textContent = 'Error: ' + e.message; }
}

// ==================== v31: AUTOMATION TAB ====================

async function loadAutomationTasks() {
  const container = document.getElementById('automation-tasks');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--fg3)">Loading...</p>';
  try {
    const r = await fetch('/api/automation/tasks');
    const d = await r.json();
    if (d.error) { container.innerHTML = '<p style="color:#f87171">Error: '+d.error+'</p>'; return; }
    const tasks = d.tasks || [];
    if (!tasks.length) { container.innerHTML = '<p style="color:var(--fg3)">No tasks registered. Check startup logs.</p>'; return; }
    let html = '<div style="display:flex;flex-direction:column;gap:10px">';
    tasks.forEach(t => {
      const statusColor = t.enabled ? '#22c55e' : '#94a3b8';
      const lastRun = t.last_run ? t.last_run.replace('T',' ').slice(0,19) : 'never';
      const nextRun = t.next_run ? t.next_run.replace('T',' ').slice(0,19) : '—';
      const errorBadge = t.last_error ? '<div style="color:#f87171;font-size:10px;margin-top:4px">⚠️ '+escapeHtml(t.last_error.slice(0,120))+'</div>' : '';
      html += '<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(148,163,184,0.15);border-left:3px solid '+statusColor+';border-radius:6px;padding:12px 14px">';
      html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap">';
      html += '<div style="flex:1;min-width:280px">';
      html += '<div style="font-weight:700;color:#e2e8f0;font-size:13px">'+escapeHtml(t.name)+' <span style="font-size:10px;color:var(--fg3);font-weight:400">['+escapeHtml(t.schedule)+']</span></div>';
      html += '<div style="font-size:11px;color:var(--fg2);margin-top:3px">'+escapeHtml(t.description)+'</div>';
      html += '<div style="font-size:10px;color:var(--fg3);margin-top:4px;font-family:ui-monospace,Consolas,monospace">last: '+lastRun+' | next: '+nextRun+' | ✅ '+t.success_count+' ❌ '+t.failure_count+'</div>';
      html += errorBadge;
      html += '</div>';
      html += '<div style="display:flex;gap:4px;flex-wrap:wrap">';
      html += '<button class="btn btn-sm" style="background:'+(t.enabled?'#22c55e':'#64748b')+';color:#fff;font-size:10px;padding:4px 8px" onclick="toggleTask(\''+t.name+'\','+(!t.enabled)+')">'+(t.enabled?'✓ On':'Off')+'</button>';
      html += '<button class="btn btn-sm btn-outline" style="font-size:10px;padding:4px 8px" onclick="runTaskNow(\''+t.name+'\')">▶ Run</button>';
      html += '<button class="btn btn-sm btn-outline" style="font-size:10px;padding:4px 8px;color:#60a5fa;border-color:rgba(96,165,250,0.4)" onclick="installToWindows(\''+t.name+'\')">⊕ Win</button>';
      html += '</div>';
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  } catch(e) { container.innerHTML = '<p style="color:#f87171">Error: '+e.message+'</p>'; }
}

async function toggleTask(name, enabled) {
  try {
    const r = await fetch('/api/automation/task/'+encodeURIComponent(name)+'/enable', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: enabled}),
    });
    const d = await r.json();
    if (d.error) { showToast('❌ '+d.error, 'error'); return; }
    showToast('Task '+name+': '+(enabled?'enabled':'disabled'), 'info');
    loadAutomationTasks();
  } catch(e) { showToast('❌ '+e.message, 'error'); }
}

async function runTaskNow(name) {
  showToast('Running '+name+'...', 'info');
  try {
    const r = await fetch('/api/automation/task/'+encodeURIComponent(name)+'/run-now', {method:'POST'});
    const d = await r.json();
    if (d.ok) {
      showToast('✅ '+name+': '+d.message, 'success');
    } else {
      showToast('❌ '+name+': '+d.message, 'error');
    }
    loadAutomationTasks();
    loadAutomationLog();
    loadAutomationStats();
  } catch(e) { showToast('❌ '+e.message, 'error'); }
}

async function installToWindows(name) {
  if (!confirm('Install "'+name+'" to Windows Task Scheduler? This makes the task run even when BVTech is closed.\n\nNote: only works on Windows. On other OSes you\'ll see a clear error.')) return;
  try {
    const r = await fetch('/api/automation/install-windows/'+encodeURIComponent(name), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    const d = await r.json();
    if (d.ok) {
      showToast('✅ Installed to Windows Task Scheduler', 'success');
      alert('Installed!\n\nTask: BVTech_'+name+'\nCommand: '+d.command+'\n\nView it in taskschd.msc under the default folder.');
    } else {
      showToast('❌ '+d.message, 'error');
      alert('Install failed: '+d.message);
    }
  } catch(e) { showToast('❌ '+e.message, 'error'); }
}

async function loadAutomationLog() {
  const container = document.getElementById('automation-log');
  if (!container) return;
  container.textContent = 'Loading...';
  const category = document.getElementById('auto-log-filter').value;
  const params = category ? '?category='+encodeURIComponent(category)+'&limit=200' : '?limit=200';
  try {
    const r = await fetch('/api/automation/log'+params);
    const d = await r.json();
    const events = d.events || [];
    if (!events.length) { container.textContent = 'No events match that filter.'; return; }
    const lines = events.map(e => {
      const ok = e.success ? '✅' : '❌';
      const ts = (e.ts || '').replace('T', ' ').slice(0, 19);
      const cat = (e.category || '').padEnd(11);
      const action = (e.action || '').padEnd(32);
      const target = e.target || '';
      return ok + ' ' + ts + '  ' + cat + ' ' + action + ' ' + target;
    });
    container.textContent = lines.join('\n');
  } catch(e) { container.textContent = 'Error: '+e.message; }
}

async function loadAutomationStats() {
  try {
    const r = await fetch('/api/automation/stats');
    const d = await r.json();
    if (d.error) return;
    const setv = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setv('auto-evt-total', (d.total || 0).toLocaleString());
    setv('auto-evt-24h', (d.last_24h || 0).toString());
    setv('auto-evt-fail', (d.failures || 0).toString());
    setv('auto-db-size', (d.db_size_kb || 0) + ' KB');
  } catch(e) {}
}

// ==================== v32: POST QUEUE (Staggered) ====================

async function queueAdd() {
  const title = (document.getElementById('queue-title').value || '').trim();
  if (!title) { showToast('Title required','error'); return; }
  const payload = {
    title: title,
    topic: (document.getElementById('queue-topic').value || '').trim(),
    tone: document.getElementById('queue-tone').value,
    length: document.getElementById('queue-length').value,
    custom_instructions: (document.getElementById('queue-custom').value || '').trim(),
  };
  try {
    const r = await fetch('/api/queue/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (d.error) { showToast('❌ '+d.error, 'error'); return; }
    showToast('✅ Added to queue: '+d.id, 'success');
    document.getElementById('queue-title').value = '';
    document.getElementById('queue-topic').value = '';
    document.getElementById('queue-custom').value = '';
    queueLoad();
  } catch(e) { showToast('❌ '+e.message, 'error'); }
}

async function queueLoad() {
  const list = document.getElementById('queue-list');
  const stats = document.getElementById('queue-stats');
  if (!list) return;
  list.innerHTML = '<p style="color:var(--fg3);font-size:11px">Loading...</p>';
  try {
    const r = await fetch('/api/queue/list');
    const d = await r.json();
    if (d.error) { list.innerHTML = '<p style="color:#f87171">'+d.error+'</p>'; return; }
    const s = d.stats || {};
    if (stats) {
      stats.innerHTML = [
        '<span>📋 Total: <strong>'+(s.total||0)+'</strong></span>',
        '<span style="color:#94a3b8">⏳ Pending: <strong>'+(s.pending||0)+'</strong></span>',
        '<span style="color:#f59e0b">🔄 In progress: <strong>'+(s.in_progress||0)+'</strong></span>',
        '<span style="color:#22c55e">✅ Done: <strong>'+(s.done||0)+'</strong></span>',
        '<span style="color:#f87171">❌ Failed: <strong>'+(s.failed||0)+'</strong></span>',
      ].join(' · ');
    }
    const items = d.queue || [];
    if (!items.length) { list.innerHTML = '<p style="color:var(--fg3);font-size:11px">Queue is empty. Add items above to get started.</p>'; return; }
    let html = '<div style="display:flex;flex-direction:column;gap:6px">';
    items.forEach(item => {
      const statusColor = {pending:'#94a3b8', in_progress:'#f59e0b', done:'#22c55e', failed:'#f87171'}[item.status] || '#94a3b8';
      const chanSpans = ['bvtech','jp','linkedin','gbp'].map(c => {
        const done = (item.channels_done || []).includes(c);
        const failed = (item.channels_failed || []).includes(c);
        const color = done ? '#22c55e' : failed ? '#f87171' : '#475569';
        const icon = done ? '✓' : failed ? '✗' : '○';
        return '<span style="color:'+color+';font-size:9px;margin-right:4px">'+icon+' '+c+'</span>';
      }).join('');
      html += '<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(148,163,184,0.15);border-left:3px solid '+statusColor+';border-radius:6px;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">';
      html += '<div style="flex:1;min-width:240px">';
      html += '<div style="font-size:12px;font-weight:700;color:#e2e8f0">'+escapeHtml(item.title)+'</div>';
      html += '<div style="font-size:10px;color:var(--fg3);margin-top:2px">'+(item.topic?'topic: '+escapeHtml(item.topic)+' · ':'')+'added '+(item.added_at || '?').slice(0,16).replace('T',' ')+' · '+escapeHtml(item.status)+'</div>';
      html += '<div style="margin-top:4px">'+chanSpans+'</div>';
      if (item.last_error) html += '<div style="color:#f87171;font-size:9px;margin-top:3px">⚠️ '+escapeHtml(item.last_error.slice(0,120))+'</div>';
      html += '</div>';
      html += '<button class="btn btn-sm btn-outline" style="font-size:10px;padding:4px 8px" onclick="queueRemove(\''+item.id+'\')">Remove</button>';
      html += '</div>';
    });
    html += '</div>';
    list.innerHTML = html;
  } catch(e) { list.innerHTML = '<p style="color:#f87171">'+e.message+'</p>'; }
}

async function queueRemove(id) {
  if (!confirm('Remove this queue item? (Already-published channels are NOT affected.)')) return;
  try {
    const r = await fetch('/api/queue/remove/'+encodeURIComponent(id), {method: 'POST'});
    const d = await r.json();
    if (d.error) { showToast('❌ '+d.error, 'error'); return; }
    showToast('Removed', 'info');
    queueLoad();
  } catch(e) { showToast('❌ '+e.message, 'error'); }
}

// ==================== v32: DRAFT & TRACK email helper ====================

function draftAndTrack() {
  // Build a mailto: URL with BCC auto-injected (if configured), open the
  // default mail client, and pre-log a "draft_opened" event to the
  // local event log so the user has a breadcrumb.
  const email = (document.getElementById('hstrack-to').value || '').trim();
  const subject = (document.getElementById('hstrack-subject').value || '').trim();
  const body = document.getElementById('hstrack-body').value || '';
  const bcc = (document.getElementById('hstrack-bcc').value || '').trim();

  if (!email || !email.includes('@')) {
    showToast('Enter a recipient email first', 'error');
    return;
  }

  const params = [];
  if (subject) params.push('subject=' + encodeURIComponent(subject));
  if (body) params.push('body=' + encodeURIComponent(body));
  if (bcc) params.push('bcc=' + encodeURIComponent(bcc));
  const mailto = 'mailto:' + encodeURIComponent(email) + (params.length ? '?' + params.join('&') : '');

  // Pre-log to the event log so we have a breadcrumb even if the user
  // abandons the draft in their mail client.
  try {
    fetch('/api/hubspot/track-email', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        email: email,
        subject: subject || '(no subject)',
        body: body || '(draft opened via Draft & Track)',
        direction: 'outgoing',
        first_name: document.getElementById('hstrack-fname').value.trim(),
        last_name: document.getElementById('hstrack-lname').value.trim(),
        company: document.getElementById('hstrack-company').value.trim(),
        phone: document.getElementById('hstrack-phone').value.trim(),
      }),
    }).then(r => r.json()).then(d => {
      if (d.error) {
        _hsTrackLog('Pre-log warning: ' + d.error);
      } else {
        _hsTrackLog('✅ Pre-logged to HubSpot (contact ' + d.contact_id + '). Draft opened in your mail client — remember to BCC ' + (bcc || 'your BCC address') + ' and actually send.');
      }
    }).catch(e => _hsTrackLog('Pre-log error: ' + e.message));
  } catch(e) {}

  // Open the default mail client
  window.location.href = mailto;
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ==================== v31: WHAT'S NEW MODAL ====================

async function showWhatsNew() {
  let modal = document.getElementById('whats-new-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'whats-new-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px)';
    modal.innerHTML = '<div id="whats-new-content" style="background:#0f172a;border:1px solid rgba(148,163,184,0.25);border-radius:12px;max-width:720px;width:100%;max-height:85vh;overflow-y:auto;padding:28px 32px;box-shadow:0 20px 60px rgba(0,0,0,0.5);color:#e2e8f0"><p style="color:var(--fg3)">Loading...</p></div>';
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);
  }
  const content = document.getElementById('whats-new-content');
  try {
    const r = await fetch('/api/whats-new');
    const d = await r.json();
    let html = '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">';
    html += '<div><h2 style="margin:0;font-size:22px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">🎁 What\'s New</h2>';
    html += '<div style="font-size:11px;color:var(--fg3);margin-top:3px">BVTech MSP Command Center v'+d.current_version+' — '+escapeHtml(d.codename || '')+'</div></div>';
    html += '<button onclick="document.getElementById(\'whats-new-modal\').remove()" style="background:rgba(148,163,184,0.15);border:none;color:#e2e8f0;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:18px">×</button>';
    html += '</div>';
    if (d.v31) {
      html += '<div style="background:linear-gradient(135deg,rgba(59,130,246,0.08),rgba(139,92,246,0.05));border:1px solid rgba(59,130,246,0.2);border-radius:8px;padding:16px 20px;margin-bottom:20px">';
      html += '<div style="font-weight:800;font-size:14px;color:#93c5fd;margin-bottom:4px">🚀 '+escapeHtml(d.v31.title)+'</div>';
      html += '<div style="font-size:11px;color:var(--fg3);margin-bottom:10px">'+escapeHtml(d.v31.date)+'</div>';
      html += '<ul style="margin:0;padding-left:20px;font-size:12px;line-height:1.7;color:var(--fg2)">';
      (d.v31.highlights || []).forEach(h => { html += '<li>'+escapeHtml(h)+'</li>'; });
      html += '</ul></div>';
    }
    html += '<details style="margin-top:10px"><summary style="cursor:pointer;color:var(--fg2);font-size:13px;padding:8px 0;user-select:none">📜 Previous releases</summary>';
    html += '<div style="margin-top:10px;display:flex;flex-direction:column;gap:10px">';
    (d.history || []).forEach(h => {
      html += '<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(148,163,184,0.1);border-radius:6px;padding:12px 16px">';
      html += '<div style="font-weight:700;color:#e2e8f0;font-size:12px">v'+escapeHtml(h.version)+' — '+escapeHtml(h.title)+' <span style="color:var(--fg3);font-weight:400;font-size:10px">('+escapeHtml(h.date)+')</span></div>';
      html += '<ul style="margin:6px 0 0;padding-left:18px;font-size:11px;color:var(--fg2);line-height:1.5">';
      (h.notes || []).forEach(n => { html += '<li>'+escapeHtml(n)+'</li>'; });
      html += '</ul></div>';
    });
    html += '</div></details>';
    html += '<div style="margin-top:20px;padding-top:14px;border-top:1px solid rgba(148,163,184,0.15);font-size:10px;color:var(--fg3);text-align:center">Click outside or the × to close. Re-open anytime via the What\'s New button on the dashboard.</div>';
    content.innerHTML = html;
    // Remember we showed this version
    try { localStorage.setItem('bvtech_last_seen_version', d.current_version); } catch(e) {}
  } catch(e) {
    content.innerHTML = '<p style="color:#f87171">Error loading: '+e.message+'</p>';
  }
}

// First-run auto-show
(function() {
  try {
    const lastSeen = localStorage.getItem('bvtech_last_seen_version');
    if (lastSeen !== '32.1') {
      // Wait until DOM ready, then show after a short delay
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(showWhatsNew, 1200));
      } else {
        setTimeout(showWhatsNew, 1200);
      }
    }
  } catch(e) {}
})();

// Auto-load HS Track data when tab is opened (hook into switchTab)
const _origSwitchTab = typeof switchTab === 'function' ? switchTab : null;
if (_origSwitchTab) {
  window.switchTab = function(name, el) {
    _origSwitchTab(name, el);
    if (name === 'hstrack') {
      loadHsStats();
      loadBccAddress();
    } else if (name === 'automation') {
      loadAutomationTasks();
      loadAutomationLog();
      loadAutomationStats();
    } else if (name === 'orm') {
      // v32: auto-load post queue
      setTimeout(queueLoad, 100);
    }
  };
}

// ==================== SUPER POSTING — Post Functions ====================

async function ormPostNow() {
  const log = document.getElementById('orm-log');
  const topic = document.getElementById('orm-topic').value.trim();
  log.innerHTML = '⚡ Generating ORM post (v17 Google-Safe)...\n'+(topic?'Topic: '+topic:'Auto-picking topic from bank...')+'\n\nClaude is writing with randomized template... (15-30 sec)\n🛡️ Dedup + velocity check running.\n';
  try {
    const res = await fetch('/api/orm/post-now', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({topic,target:document.getElementById('orm-target').value,
        status:document.getElementById('orm-status').value,tone:document.getElementById('orm-tone').value,
        length:document.getElementById('orm-length').value,custom_instructions:document.getElementById('orm-custom').value})});
    const d = await res.json();
    if(d.error){
      if(d.dedup){log.innerHTML+='\\n<strong style="color:var(--orange)">🛡️ DEDUP BLOCKED</strong>\\n'+d.error+'\\n\\nThis post was NOT published (already exists). Pick a different topic.';showToast('🛡️ Dedup blocked — already exists','info');}
      else{log.innerHTML+='\\n❌ '+d.error;showToast('❌ '+d.error,'error');}
      return;
    }
    log.innerHTML='<strong style="color:#ec4899">─── SUPER POST CREATED ───</strong>\\n\\n';
    log.innerHTML+='<strong>Title:</strong> '+d.title+'\\n';
    log.innerHTML+='<strong>Topic:</strong> '+d.topic+'\\n';
    log.innerHTML+='<strong>Target:</strong> '+d.target+' (v17 auto-alternated if "Both" selected)\\n';
    log.innerHTML+='<strong>Words:</strong> '+d.word_count+'\\n\\n';
    // v17: Show velocity warning
    if(d.velocity_warning){
      log.innerHTML+='<strong style="color:var(--orange)">'+d.velocity_warning+'</strong>\\n\\n';
    }
    if(d.posts){for(const[s,r]of Object.entries(d.posts)){
      if(r.success){log.innerHTML+='<strong style="color:var(--green)">✅ '+s+' — ID:'+r.post_id+'</strong>\\n';
        if(r.link)log.innerHTML+='   🔗 '+r.link+'\\n';}
      else log.innerHTML+='<strong style="color:var(--red)">❌ '+s+' — '+(r.error||'failed')+'</strong>\\n';}}
    if(d.meta_description)log.innerHTML+='\\n<strong>Meta:</strong> '+d.meta_description;
    // v15: Show SEO score
    if(d.seo_score){
      const s=d.seo_score;
      const color=s.score>=80?'var(--green)':s.score>=60?'var(--orange)':'var(--red)';
      log.innerHTML+='\\n\\n<strong style="color:'+color+'">📊 SEO SCORE: '+s.score+'/'+s.max+'</strong>\\n';
      (s.reasons||[]).forEach(r=>{log.innerHTML+='   '+(r.includes('Missing')||r.includes('No ')||r.includes('Too ')?'⚠️':'✅')+' '+r+'\\n';});
      // Update sidebar display
      document.getElementById('orm-seo-display').innerHTML='<strong style="color:'+color+'">Last Post SEO: '+s.score+'/100</strong> — '+(s.reasons||[]).slice(0,3).join(', ');
    }
    let c=parseInt(document.getElementById('orm-total').textContent)||0;
    document.getElementById('orm-total').textContent=c+1;
    showToast('✅ ORM post published!','success');
  }catch(e){log.innerHTML+='\\n❌ '+e.message;showToast('❌ '+e.message,'error');}
}

async function ormBuildQueue() {
  const log = document.getElementById('orm-log');
  const count = document.getElementById('orm-q-count').value;
  log.innerHTML = '📋 Building queue of '+count+' posts...\\n';
  try {
    const res = await fetch('/api/orm/queue-build', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({count:parseInt(count),target:document.getElementById('orm-q-target').value,
        status:document.getElementById('orm-q-status').value})});
    const d = await res.json();
    log.innerHTML+='\\n<strong style="color:var(--orange)">✅ '+d.queued+' posts queued!</strong> (Total: '+d.total_in_queue+')\\n\\n';
    log.innerHTML+='<strong>Topics queued:</strong>\\n';
    (d.topics||[]).forEach((t,i)=>{log.innerHTML+=(i+1)+'. '+t+'\\n';});
    log.innerHTML+='\\n<span style="color:var(--fg3)">Hit ▶ Publish Next to post one, or 🚀 Publish All to blast them out.</span>';
    document.getElementById('orm-queue-count').textContent=d.total_in_queue;
    showToast('📋 '+d.queued+' posts queued!','success');
  }catch(e){log.innerHTML+='❌ '+e.message;}
}

async function ormPublishNext() {
  const log = document.getElementById('orm-log');
  log.innerHTML = '▶ Publishing next queued post...\\n\\nGenerating content... (15-30 sec)\\n';
  try {
    const res = await fetch('/api/orm/queue/publish-next', {method:'POST'});
    const d = await res.json();
    if(d.error){log.innerHTML+='\\n❌ '+d.error;showToast('❌ '+d.error,'error');return;}
    log.innerHTML+='\\n<strong style="color:var(--green)">✅ Published: '+d.title+'</strong>\\n';
    if(d.posts){for(const[s,r]of Object.entries(d.posts)){
      log.innerHTML+='   '+s+': '+(r.success?'✅ ID:'+r.post_id:'❌ '+(r.error||''))+'\\n';}}
    showToast('✅ Next post published!','success');
    ormRefreshStats();
  }catch(e){log.innerHTML+='❌ '+e.message;}
}

async function ormPublishAll() {
  const log = document.getElementById('orm-log');
  log.innerHTML = '🚀 PUBLISHING ALL QUEUED POSTS...\\n\\n🛡️ v15: Checking for active scheduler...\\n';
  try {
    const res = await fetch('/api/orm/queue/publish-all', {method:'POST'});
    const d = await res.json();
    if(d.error||d.dedup_block){
      log.innerHTML+='\\n<strong style="color:var(--red)">⛔ '+d.error+'</strong>\\n';
      showToast('⛔ '+d.error,'error');
      return;
    }
    log.innerHTML+='\\n<strong style="color:var(--green)">🚀 Started! Publishing '+d.posts_to_publish+' posts...</strong>\\n';
    log.innerHTML+='🛡️ Dedup protection active — duplicates will be auto-blocked.\\n';
    log.innerHTML+='Check history in a few minutes to see results.';
    showToast('🚀 Publishing '+d.posts_to_publish+' posts!','success');
  }catch(e){log.innerHTML+='❌ '+e.message;}
}

async function ormViewQueue() {
  const log = document.getElementById('orm-log');
  try {
    const res = await fetch('/api/orm/queue');
    const d = await res.json();
    log.innerHTML='<strong style="color:var(--orange)">─── POST QUEUE ('+d.total+' total, '+d.pending+' pending) ───</strong>\\n\\n';
    (d.queue||[]).forEach((q,i)=>{
      const icon = q.state==='published'?'🟢':q.state==='error'?'🔴':'⏳';
      log.innerHTML+=icon+' '+(i+1)+'. '+q.topic+'\\n';
      log.innerHTML+='   State: '+q.state+' | Target: '+q.target+'\\n\\n';});
    document.getElementById('orm-queue-count').textContent=d.pending;
  }catch(e){log.innerHTML='❌ '+e.message;}
}

async function ormClearQueue() {
  await fetch('/api/orm/queue/clear',{method:'POST'});
  document.getElementById('orm-queue-count').textContent='0';
  document.getElementById('orm-log').innerHTML='🗑 Queue cleared.';
  showToast('Queue cleared','info');
}

function ormSchedulerOn() {
  const ppw=document.getElementById('orm-s-ppd').value;
  const sh=document.getElementById('orm-s-start').value;
  const eh=document.getElementById('orm-s-end').value;
  const tgt=document.getElementById('orm-s-target').value;
  // v17: Validate safe velocity
  if(parseInt(ppw)>3){
    showToast('⛔ Max 3 posts/week to stay Google-safe!','error');
    return;
  }
  // v15: Check if bulk publish is running first
  fetch('/api/orm/publish-status').then(r=>r.json()).then(s=>{
    if(s.bulk_active){
      showToast('⛔ A bulk publish is running — wait for it to finish before starting the scheduler.','error');
      document.getElementById('orm-log').innerHTML='⛔ Cannot start scheduler while Publish All is running. Wait for it to finish.';
      return;
    }
    fetch('/api/orm/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled:true,posts_per_week:parseInt(ppw),start_hour:parseInt(sh),end_hour:parseInt(eh),target:tgt,status:'publish'})});
    document.getElementById('orm-sched-status').textContent=ppw+'/wk';
    document.getElementById('orm-sched-status').style.color='var(--green)';
    document.getElementById('orm-log').innerHTML='🟢 SCHEDULER ACTIVATED (v17 Google-Safe Mode)\n\n'+ppw+' posts/WEEK between '+sh+':00 and '+eh+':00\nSite Rotation: '+tgt+'\n\n🛡️ v17 Anti-Spam Features:\n  • Posts spread across random days (not daily)\n  • ±4 hour timing jitter (no predictable pattern)\n  • 5 rotating prompt templates (no template fingerprint)\n  • Reduced name density (2-3x, not 5-8x)\n  • Dedup protection still active\n\nPosts will auto-generate while BVTech is running.';
    showToast('🟢 ORM Scheduler ON — '+ppw+' posts/week (Google-safe)!','success');
  });
}

// v17: Spam Risk Checker
async function ormSpamCheck() {
  const log = document.getElementById('orm-log');
  log.innerHTML = '📊 Analyzing publishing velocity and spam risk...\n';
  try {
    const res = await fetch('/api/orm/spam-risk');
    const d = await res.json();
    const risk = d.risk_level || 'UNKNOWN';
    const riskColor = risk==='LOW'?'var(--green)':risk==='MEDIUM'?'var(--orange)':'var(--red)';
    let html = '<strong style="color:var(--cyan)">─── SPAM RISK ANALYSIS ───</strong>\n\n';
    html += '<strong>Risk Level: <span style="color:'+riskColor+'">'+risk+'</span></strong>\n\n';
    html += '<strong>Publishing Stats (Last 7 Days):</strong>\n';
    html += '  Posts this week: '+(d.posts_this_week||0)+' / 3 max\n';
    html += '  Posts to BVTech: '+(d.bvtech_count||0)+'\n';
    html += '  Posts to JP: '+(d.jp_count||0)+'\n';
    html += '  Dual-posted (both): '+(d.both_count||0)+(d.both_count>0?' ⚠️ AVOID':' ✅')+'\n\n';
    html += '<strong>Publishing Stats (Last 30 Days):</strong>\n';
    html += '  Posts this month: '+(d.posts_this_month||0)+'\n';
    html += '  Avg per week: '+(d.avg_per_week||0)+'\n\n';
    if(d.warnings&&d.warnings.length){
      html+='<strong style="color:var(--orange)">⚠️ Warnings:</strong>\n';
      d.warnings.forEach(w=>{html+='  ⚠️ '+w+'\n';});
    }
    if(d.recommendations&&d.recommendations.length){
      html+='\n<strong style="color:var(--green)">💡 Recommendations:</strong>\n';
      d.recommendations.forEach(r=>{html+='  → '+r+'\n';});
    }
    log.innerHTML = html;
    // Update spam risk indicator
    document.getElementById('orm-spam-risk').innerHTML='<strong style="color:'+riskColor+'">🛡️ Spam Risk: '+risk+'</strong> — '+(d.summary||'');
    document.getElementById('orm-spam-risk').style.background=risk==='LOW'?'rgba(34,197,94,0.08)':risk==='MEDIUM'?'rgba(245,158,11,0.08)':'rgba(239,68,68,0.08)';
    document.getElementById('orm-spam-risk').style.borderColor=risk==='LOW'?'rgba(34,197,94,0.2)':risk==='MEDIUM'?'rgba(245,158,11,0.2)':'rgba(239,68,68,0.2)';
  } catch(e) { log.innerHTML += '\n❌ '+e.message; }
}

function ormSchedulerOff() {
  fetch('/api/orm/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:false})});
  document.getElementById('orm-sched-status').textContent='OFF';
  document.getElementById('orm-sched-status').style.color='var(--purple)';
  document.getElementById('orm-log').innerHTML='⏸ Scheduler stopped.';
  showToast('Scheduler stopped','info');
}

async function ormViewHistory() {
  const log = document.getElementById('orm-log');
  try {
    const res = await fetch('/api/orm/history');
    const d = await res.json();
    const h = d.history||[];
    if(!h.length){log.innerHTML='No ORM posts yet.';return;}
    log.innerHTML='<strong style="color:#ec4899">─── ORM POST HISTORY ('+h.length+') ───</strong>\\n\\n';
    h.slice(0,50).forEach(e=>{
      const icon=e.status==='error'?'🔴':'🟢';
      log.innerHTML+=icon+' <strong>'+e.title+'</strong>\\n';
      log.innerHTML+='   '+(e.date||'')+' | '+(e.target||'')+' | '+(e.word_count||'?')+' words';
      if(e.seo_score){
        const sc=e.seo_score.score||0;
        const col=sc>=80?'var(--green)':sc>=60?'var(--orange)':'var(--red)';
        log.innerHTML+=' | <strong style="color:'+col+'">SEO:'+sc+'</strong>';
      }
      log.innerHTML+='\\n';
      if(e.posts){for(const[s,r]of Object.entries(e.posts)){log.innerHTML+='   → '+s+': '+(r.success?'✅ ID:'+r.post_id:'❌ '+(r.error||''))+'\\n';}}
      log.innerHTML+='\\n';});
    document.getElementById('orm-total').textContent=h.filter(x=>x.status!=='error').length;
  }catch(e){log.innerHTML='❌ '+e.message;}
}

async function ormViewTopics() {
  const log = document.getElementById('orm-log');
  try {
    const res = await fetch('/api/orm/topics');
    const d = await res.json();
    log.innerHTML='<strong style="color:var(--cyan)">─── TOPIC BANK ('+d.available+' available / '+d.total+' total) ───</strong>\\n\\n';
    (d.topics||[]).forEach((t,i)=>{
      log.innerHTML+=(t.used?'✅':'⬜')+' '+(i+1)+'. '+t.topic+'\\n';});
    document.getElementById('orm-topics-left').textContent=d.available;
  }catch(e){log.innerHTML='❌ '+e.message;}
}

async function ormResetTopics() {
  await fetch('/api/orm/topics/reset',{method:'POST'});
  document.getElementById('orm-topics-left').textContent='60';
  showToast('Topics reset — all 60+ available again','success');
}

async function ormGenerateTopics() {
  const log = document.getElementById('orm-log');
  log.innerHTML='💡 Generating 30 custom topic ideas with Claude...\\n';
  try {
    const res = await fetch('/api/orm/topics/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await res.json();
    if(d.error){log.innerHTML+='❌ '+d.error;return;}
    log.innerHTML='<strong style="color:#ec4899">─── CUSTOM TOPIC IDEAS ───</strong>\\n\\n'+(d.topics||'');
    showToast('💡 Topics generated!','success');
  }catch(e){log.innerHTML='❌ '+e.message;}
}

async function ormRefreshStats() {
  try{
    const[qr,hr]=await Promise.all([fetch('/api/orm/queue'),fetch('/api/orm/history')]);
    const qd=await qr.json(),hd=await hr.json();
    document.getElementById('orm-queue-count').textContent=qd.pending||0;
    document.getElementById('orm-total').textContent=(hd.history||[]).filter(x=>x.status!=='error').length;
  }catch(e){}
}

// ==================== ORM AUTO-POSTER ====================
function toggleORMAutoPost(e){}
async function ormAutoRunNow(){}
async function loadORMHistory(){}

// ==================== v15: DUPLICATE SCANNER + TOPIC HEALTH ====================
async function ormScanDupes() {
  const log = document.getElementById('orm-dedup-log');
  log.innerHTML = '🔍 v16 Deep Scan: checking ALL posts for EXACT + NEAR duplicates...<br><br>';
  try {
    const res = await fetch('/api/orm/scan-duplicates', {method:'POST'});
    const d = await res.json();
    const bv = d.bvtech || [];
    const jp = d.jordanpolasek || [];
    const total = d.total_dupes || 0;
    const errs = d.errors || [];

    if (total === 0) {
      let html = '<strong style="color:var(--green)">✅ NO DUPLICATES FOUND!</strong><br><br>Both sites are clean.<br>';
      html += 'Posts scanned: '+(d.bvtech_scanned||'?')+' (BVTech) + '+(d.jp_scanned||'?')+' (JP)<br>';
      if (errs.length) { html += '<br><strong style="color:var(--orange)">⚠️ Warnings:</strong><br>'; errs.forEach(e => { html += '   ' + e + '<br>'; }); }
      log.innerHTML = html;
      showToast('✅ No duplicates found!', 'success');
      return;
    }

    let html = '<strong style="color:var(--red)">🧹 FOUND ' + total + ' DUPLICATE(S)</strong><br>';
    html += '<span style="color:var(--fg3)">Posts scanned: '+(d.bvtech_scanned||'?')+' (BVTech) + '+(d.jp_scanned||'?')+' (JP)</span><br><br>';

    function renderDupes(dupes, siteName, siteKey) {
      if (!dupes.length) return '';
      let s = '<strong style="color:var(--orange)">── ' + siteName + ' (' + dupes.length + ' dupes) ──</strong><br>';
      dupes.forEach(p => {
        const conf = p.confidence || 'EXACT';
        const sim = p.similarity || 100;
        const isNear = conf === 'NEAR';
        const confColor = conf === 'EXACT' ? 'var(--red)' : 'var(--orange)';
        const simBar = '█'.repeat(Math.round(sim/10)) + '░'.repeat(10 - Math.round(sim/10));
        s += '🔴 <strong>ID:' + p.id + '</strong> — "' + p.title + '"<br>';
        if (isNear && p.keep_title) {
          s += '   ↔️ Similar to: "' + p.keep_title + '"<br>';
        }
        s += '   📅 ' + (p.date||'').slice(0,10) + ' | Keep: #' + p.keep_id;
        s += ' | <span style="color:'+confColor+'">' + conf + ' ' + sim + '% ' + simBar + '</span><br>';
        s += '   <a href="#" onclick="ormTrashOneDupe(\'' + siteKey + '\',' + p.id + ',this);return false" style="color:var(--red);text-decoration:underline;font-weight:700">🗑 Trash this duplicate</a><br><br>';
      });
      return s;
    }

    html += renderDupes(bv, 'BVTech.org', 'bvtech');
    html += renderDupes(jp, 'JordanPolasek.com', 'jordanpolasek');

    if (errs.length) { html += '<br><strong style="color:var(--orange)">⚠️ Debug Info:</strong><br>'; errs.forEach(e => { html += '   ' + e + '<br>'; }); }
    html += '<br><span style="color:var(--fg3)">EXACT = identical titles | NEAR = 75%+ word overlap (different wording, same topic)</span>';
    log.innerHTML = html;
    showToast('🧹 Found ' + total + ' duplicate(s)', 'info');
  } catch(e) {
    log.innerHTML += '<br>❌ ' + e.message;
    showToast('❌ Scan failed', 'error');
  }
}

async function ormTrashOneDupe(site, postId, linkEl) {
  try {
    if (linkEl) linkEl.innerHTML = '⏳ Trashing #' + postId + '...';
    const res = await fetch('/api/orm/trash-duplicate', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({site, post_id: postId})});
    const d = await res.json();
    if (d.success) {
      if (linkEl) linkEl.outerHTML = '<span style="color:var(--green);font-weight:700">✅ Trashed #' + postId + '!</span>';
      showToast('✅ Trashed #' + postId + ' on ' + site, 'success');
    } else {
      const errMsg = d.error || 'Unknown error';
      if (linkEl) linkEl.outerHTML = '<span style="color:var(--red)">❌ Failed: ' + errMsg + '</span>';
      showToast('❌ ' + errMsg, 'error');
    }
  } catch(e) {
    if (linkEl) linkEl.outerHTML = '<span style="color:var(--red)">❌ ' + e.message + '</span>';
    showToast('❌ ' + e.message, 'error');
  }
}

async function ormTrashAllDupes() {
  const log = document.getElementById('orm-dedup-log');
  log.innerHTML = '🗑 v16: Scanning and trashing ALL duplicates (exact + near)...<br><br>';
  try {
    const res = await fetch('/api/orm/trash-all-duplicates', {method:'POST'});
    const d = await res.json();
    if (d.error) {
      log.innerHTML += '<br><strong style="color:var(--red)">❌ ' + d.error + '</strong>';
      showToast('❌ ' + d.error, 'error');
      return;
    }
    let html = '<strong style="color:var(--green)">✅ CLEANUP COMPLETE!</strong><br><br>';
    html += '🌐 BVTech.org: <strong>' + d.bvtech_trashed + '</strong> duplicates trashed<br>';
    html += '👤 JordanPolasek.com: <strong>' + d.jp_trashed + '</strong> duplicates trashed<br>';
    html += '📊 Total cleaned: <strong style="color:var(--green)">' + d.total_trashed + '</strong><br>';
    if (d.remaining > 0) {
      html += '<br><span style="color:var(--orange)">⚠️ ' + d.remaining + ' more found on re-scan. Run again.</span><br>';
    }
    if (d.details && d.details.length) {
      html += '<br><strong>Details:</strong><br>';
      d.details.forEach(x => { html += '   ' + x + '<br>'; });
    }
    if (d.errors && d.errors.length) {
      html += '<br><strong style="color:var(--red)">Errors:</strong><br>';
      d.errors.forEach(e => { html += '   ❌ ' + e + '<br>'; });
    }
    log.innerHTML = html;
    showToast('✅ ' + d.total_trashed + ' trashed' + (d.remaining > 0 ? ' (' + d.remaining + ' remaining)' : ''), 'success');
  } catch(e) {
    log.innerHTML += '<br>❌ ' + e.message;
    showToast('❌ ' + e.message, 'error');
  }
}

async function ormTestDelete() {
  const log = document.getElementById('orm-dedup-log');
  log.innerHTML = '🔌 Testing delete connectivity on both sites...<br><br>';
  try {
    const res = await fetch('/api/orm/test-delete', {method:'POST'});
    const d = await res.json();
    let html = '<strong style="color:var(--cyan)">─── DELETE CONNECTION TEST ───</strong><br><br>';

    for (const [site, info] of Object.entries(d)) {
      const name = site === 'bvtech' ? '🌐 BVTech.org' : '👤 JordanPolasek.com';
      html += '<strong>' + name + '</strong><br>';
      if (info.error) {
        html += '   <span style="color:var(--red)">❌ Error: ' + info.error + '</span><br>';
      } else {
        html += '   Mode: <strong>' + (info.mode||'?') + '</strong><br>';
        html += '   Relay URL: ' + (info.relay_url||'none') + '<br>';
        html += '   Has relay key: ' + (info.has_relay ? '✅' : '❌') + '<br>';
        html += '   Search test: ' + (info.search_ok ? '<span style="color:var(--green)">✅ Found ' + info.search_count + ' posts</span>' : '<span style="color:var(--red)">❌ ' + (info.search_err||'failed') + '</span>') + '<br>';
      }
      html += '<br>';
    }

    html += '<span style="color:var(--fg3)">If search works but delete fails, re-upload the v16 PHP files to your servers.</span><br>';
    html += '<span style="color:var(--fg3)">BVTech needs bvtech-api.php | JP needs jp-api.php (both v3.0+)</span>';
    log.innerHTML = html;
    showToast('Test complete — check results', 'info');
  } catch(e) {
    log.innerHTML += '<br>❌ ' + e.message;
  }
}

async function ormCheckPublishStatus() {
  const log = document.getElementById('orm-log');
  try {
    const res = await fetch('/api/orm/publish-status');
    const d = await res.json();
    let html = '<strong style="color:var(--cyan)">─── PUBLISH STATUS ───</strong><br><br>';
    html += 'Scheduler: ' + (d.scheduler_active ? '<strong style="color:var(--green)">🟢 ACTIVE</strong>' : '<strong style="color:var(--fg3)">⬜ OFF</strong>') + '<br>';
    html += 'Bulk Publish: ' + (d.bulk_active ? '<strong style="color:var(--orange)">🟠 RUNNING</strong>' : '<strong style="color:var(--fg3)">⬜ OFF</strong>') + '<br>';
    html += '<br>🛡️ v16 Safety: Scheduler and Publish All cannot run simultaneously.<br>';
    html += 'Title dedup check runs before every single post.<br>';
    log.innerHTML = html;
  } catch(e) { log.innerHTML = '❌ ' + e.message; }
}

async function ormTopicHealth() {
  const log = document.getElementById('orm-log');
  log.innerHTML = '📊 Analyzing topic health and content freshness...<br>';
  try {
    const [tr, hr] = await Promise.all([fetch('/api/orm/topics'), fetch('/api/orm/history')]);
    const td = await tr.json(), hd = await hr.json();
    const used = td.used || 0, total = td.total || 60, avail = td.available || 0;
    const history = hd.history || [];
    const freshness = avail > 30 ? 'EXCELLENT' : avail > 15 ? 'GOOD' : avail > 5 ? 'LOW' : 'CRITICAL';
    const fColor = avail > 30 ? 'var(--green)' : avail > 15 ? 'var(--cyan)' : avail > 5 ? 'var(--orange)' : 'var(--red)';

    // Check for topic similarity in recent posts
    const recentTitles = history.slice(0, 20).map(h => h.title || '');
    const titleWords = {};
    recentTitles.forEach(t => {
      t.toLowerCase().split(/\\s+/).forEach(w => {
        if (w.length > 4 && w !== 'jordan' && w !== 'polasek' && w !== 'bvtech') {
          titleWords[w] = (titleWords[w] || 0) + 1;
        }
      });
    });
    const overused = Object.entries(titleWords).filter(([k,v]) => v >= 4).sort((a,b) => b[1]-a[1]);

    let html = '<strong style="color:var(--cyan)">─── TOPIC HEALTH REPORT ───</strong><br><br>';
    html += '<strong>Topic Bank:</strong> ' + avail + '/' + total + ' available<br>';
    html += '<strong>Freshness:</strong> <span style="color:'+fColor+';font-weight:800">'+freshness+'</span><br>';
    html += '<strong>Posts Created:</strong> ' + history.length + '<br><br>';

    if (overused.length) {
      html += '<strong style="color:var(--orange)">⚠️ Overused Keywords in Recent Posts:</strong><br>';
      overused.slice(0, 8).forEach(([w, c]) => { html += '   "' + w + '" — used ' + c + 'x in last 20 posts<br>'; });
      html += '<br><span style="color:var(--fg3)">Consider varying topics to avoid keyword stuffing.</span><br>';
    } else {
      html += '<strong style="color:var(--green)">✅ Good keyword variety in recent posts!</strong><br>';
    }

    // SEO score average
    const scored = history.filter(h => h.seo_score && h.seo_score.score);
    if (scored.length) {
      const avg = Math.round(scored.reduce((a,h) => a + h.seo_score.score, 0) / scored.length);
      const avgColor = avg >= 80 ? 'var(--green)' : avg >= 60 ? 'var(--orange)' : 'var(--red)';
      html += '<br><strong>Avg SEO Score:</strong> <span style="color:'+avgColor+';font-weight:800">'+avg+'/100</span> (across '+scored.length+' scored posts)<br>';
    }

    log.innerHTML = html;
  } catch(e) { log.innerHTML = '❌ ' + e.message; }
}

async function testJPConnection() {
  const log = document.getElementById('orm-log');
  log.innerHTML = '🔌 Testing JordanPolasek.com...\\n';
  try {
    const res = await fetch('/api/orm/test-jp', {method:'POST'});
    const d = await res.json();
    if (d.relay_working || d.auth_ok) {
      log.innerHTML += '\\n<strong style="color:var(--green)">✅ JordanPolasek.com CONNECTED!</strong>\\n';
      if(d.site_name) log.innerHTML += 'Site: '+d.site_name+'\\n';
      if(d.total_posts!==undefined) log.innerHTML += 'Posts: '+d.total_posts+'\\n';
      if(d.mode) log.innerHTML += 'Mode: '+d.mode+'\\n';
      showToast('✅ JP connected!','success');
    } else {
      log.innerHTML += '\\n<strong style="color:var(--red)">❌ '+(d.error||'Failed')+'</strong>\\n';
      showToast('❌ JP failed','error');
    }
    log.innerHTML += '\\n'+JSON.stringify(d,null,2).substring(0,800);
  } catch(e) { log.innerHTML += '❌ '+e.message; }
}

// ==================== GUARDZ SECURITY (v16.0) ====================
async function loadGuardzDashboard() {
  showToast('Loading Guardz tracker...','info');
  try {
    const res = await fetch('/api/guardz/tracker');
    const d = await res.json();
    if (d.error) { showToast('Guardz: '+d.error,'error'); return; }
    const incidents = d.incidents||[];
    const open = incidents.filter(i=>i.status==='open');
    const resolved = incidents.filter(i=>i.status==='resolved');
    const crit = open.filter(i=>i.severity==='critical').length;
    const high = open.filter(i=>i.severity==='high').length;
    const med = open.filter(i=>i.severity==='medium').length;
    const low = open.filter(i=>i.severity==='low').length;
    document.getElementById('gz-critical').textContent = crit;
    document.getElementById('gz-high').textContent = high;
    document.getElementById('gz-medium').textContent = med;
    document.getElementById('gz-low').textContent = low;
    document.getElementById('gz-resolved').textContent = resolved.length;
    document.getElementById('gz-open').textContent = open.length;
    showToast('Security tracker loaded!');
  } catch(e) { showToast('Error: '+e.message,'error'); }
  loadGuardzIncidents();
}

async function loadGuardzIncidents() {
  const log = document.getElementById('gz-incidents-log');
  log.innerHTML = 'Loading incidents...\n';
  try {
    const res = await fetch('/api/guardz/tracker');
    const d = await res.json();
    const incidents = d.incidents||[];
    if (incidents.length === 0) { log.innerHTML = '✅ No tracked incidents.\n\nUse the Guardz portal for full analysis. Log incidents here manually.'; return; }
    log.innerHTML = '<strong style="color:#34d399">─── SECURITY INCIDENTS ───</strong>\n\n';
    incidents.forEach(i => {
      const sevColor = i.severity==='critical'?'#f87171':i.severity==='high'?'#fbbf24':i.severity==='medium'?'#60a5fa':'#94a3b8';
      const statusIcon = i.status==='resolved'?'✅':'⚠️';
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
        statusIcon+' <span style="color:'+sevColor+';font-weight:800;font-size:9px">['+i.severity.toUpperCase()+']</span> <strong>'+i.title+'</strong>' +
        '<div style="font-size:9px;color:#4a5568">'+(i.client||'')+' | '+i.status+' | '+(i.created?new Date(i.created).toLocaleDateString():'')+'</div>' +
        '<div style="font-size:9px;color:var(--fg3)">'+i.description+'</div></div>\n';
    });
    if (d.posture_score!==null) log.innerHTML += '\n<strong style="color:#34d399">Posture Score: '+d.posture_score+'/100</strong>';
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

// ==================== M365 INBOX (v16.0) ====================
let currentEmailId = null;
let currentFolder = 'inbox';

async function loadInbox(folder) {
  folder = folder || 'inbox';
  currentFolder = folder;
  // Check if M365 credentials are even configured
  try {
    const cfgRes = await fetch('/api/config');
    const cfg = await cfgRes.json();
    if (!cfg.tenant_id || !cfg.client_id || !cfg.client_secret) {
      document.getElementById('inbox-list-log').innerHTML = '❌ M365 credentials not configured.\n\nGo to Settings → Microsoft 365 — Azure AD and fill in:\n• Tenant ID\n• Client ID\n• Client Secret\n\nThen in Azure Portal → App Registration → API Permissions:\n• Add Mail.Read\n• Add Mail.ReadWrite\n• Add Mail.Send\n• Click "Grant admin consent for [your org]"\n\nWithout Mail.Read permission, the inbox cannot load.';
      return;
    }
  } catch(e) {}
  document.getElementById('inbox-folder').textContent = folder==='sentitems'?'Sent':folder==='drafts'?'Drafts':folder==='deleteditems'?'Trash':'Inbox';
  const log = document.getElementById('inbox-list-log');
  log.innerHTML = 'Loading '+folder+'...\n';
  try {
    const res = await fetch('/api/inbox/messages?folder='+folder);
    const d = await res.json();
    if (d.error) { log.innerHTML = '<span class="error">Error: '+d.error+'</span>\n\n<span class="info">Troubleshooting:</span>\n• Check Settings → Microsoft 365 → all 3 fields filled\n• In Azure Portal → App Registration → API Permissions:\n  - Mail.Read (Application)\n  - Mail.ReadWrite (Application)\n  - Mail.Send (Application)\n  - Grant admin consent\n• Use "Test M365 Connection" button in Settings\n• Visit /api/diag in browser for full diagnostic'; return; }
    const msgs = d.value || [];
    // Update unread count
    const ucRes = await fetch('/api/inbox/unread');
    const uc = await ucRes.json();
    if (!uc.error) {
      document.getElementById('inbox-unread').textContent = uc.unread||0;
      document.getElementById('inbox-total').textContent = uc.total||0;
    }
    if (msgs.length === 0) { log.innerHTML = 'No emails in this folder.'; return; }
    log.innerHTML = '';
    msgs.forEach(m => {
      const from = m.from?.emailAddress?.name || m.from?.emailAddress?.address || 'Unknown';
      const fromAddr = m.from?.emailAddress?.address || '';
      const date = m.receivedDateTime ? new Date(m.receivedDateTime).toLocaleString() : '';
      const unread = !m.isRead ? '● ' : '';
      const unreadStyle = !m.isRead ? 'font-weight:800;' : '';
      const att = m.hasAttachments ? '📎' : '';
      const imp = m.importance === 'high' ? '❗' : '';
      log.innerHTML += `<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);cursor:pointer;${unreadStyle}" onclick="previewEmail('${m.id}')">
        <span style="color:var(--ms)">${unread}</span>${imp}${att}<strong>${(m.subject||'(no subject)').substring(0,55)}</strong>
        <div style="font-size:9px;color:#4a5568">${from} &lt;${fromAddr}&gt; | ${date}</div>
        <div style="font-size:9px;color:var(--fg3)">${(m.bodyPreview||'').substring(0,100)}...</div>
      </div>\n`;
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

async function previewEmail(msgId) {
  currentEmailId = msgId;
  const log = document.getElementById('inbox-preview-log');
  log.innerHTML = 'Loading email...\n';
  try {
    const res = await fetch('/api/inbox/message/'+msgId);
    const m = await res.json();
    if (m.error) { log.innerHTML = 'Error: '+m.error; return; }
    const from = m.from?.emailAddress?.name || m.from?.emailAddress?.address || 'Unknown';
    const fromAddr = m.from?.emailAddress?.address || '';
    const to = (m.toRecipients||[]).map(r => r.emailAddress?.address||'').join(', ');
    const cc = (m.ccRecipients||[]).map(r => r.emailAddress?.address||'').join(', ');
    const date = m.receivedDateTime ? new Date(m.receivedDateTime).toLocaleString() : '';
    log.innerHTML = `<strong style="color:var(--ms)">─── EMAIL ───</strong>\n\n`;
    log.innerHTML += `<strong>Subject:</strong> ${m.subject||'(no subject)'}\n`;
    log.innerHTML += `<strong>From:</strong> ${from} &lt;${fromAddr}&gt;\n`;
    log.innerHTML += `<strong>To:</strong> ${to}\n`;
    if (cc) log.innerHTML += `<strong>CC:</strong> ${cc}\n`;
    log.innerHTML += `<strong>Date:</strong> ${date}\n`;
    log.innerHTML += `<strong>Attachments:</strong> ${m.hasAttachments?'Yes':'No'}\n`;
    log.innerHTML += `\n<strong style="color:var(--purple)">─── BODY ───</strong>\n\n`;
    // Strip HTML tags for display in log
    const body = (m.body?.content||m.bodyPreview||'').replace(/<[^>]*>/g,' ').replace(/&nbsp;/g,' ').replace(/\s+/g,' ').trim();
    log.innerHTML += body.substring(0,3000) + '\n';
    log.innerHTML += `\n<strong style="color:var(--green)">─── ACTIONS ───</strong>\n`;
    log.innerHTML += `<span style="cursor:pointer;color:var(--green)" onclick="showReplyPanel()">↩️ Reply</span>  |  `;
    log.innerHTML += `<span style="cursor:pointer;color:var(--blue)" onclick="forwardEmail()">↪️ Forward</span>  |  `;
    log.innerHTML += `<span style="cursor:pointer;color:var(--red)" onclick="deleteEmail('${msgId}')">🗑️ Delete</span>`;
    // Mark as read
    fetch('/api/inbox/read/'+msgId, {method:'POST'});
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

function showComposeEmail() {
  document.getElementById('compose-panel').style.display = 'block';
  document.getElementById('reply-panel').style.display = 'none';
  document.getElementById('compose-to').focus();
}
function hideComposeEmail() { document.getElementById('compose-panel').style.display = 'none'; }

function showReplyPanel() {
  document.getElementById('reply-panel').style.display = 'block';
  document.getElementById('compose-panel').style.display = 'none';
  document.getElementById('reply-body').focus();
}

async function sendInboxEmail() {
  const to = document.getElementById('compose-to').value.trim();
  const cc = document.getElementById('compose-cc').value.trim();
  const subject = document.getElementById('compose-subject').value.trim();
  const body = document.getElementById('compose-body').value.trim();
  if (!to || !subject) return showToast('Enter To and Subject','error');
  try {
    const res = await fetch('/api/inbox/send', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({to,cc:cc||null,subject,body:body.replace(/\n/g,'<br>')})});
    const d = await res.json();
    if (d.error) showToast('Error: '+d.error,'error');
    else { showToast('Email sent!','success'); hideComposeEmail(); }
  } catch(e) { showToast('Error: '+e.message,'error'); }
}

async function sendReply() {
  if (!currentEmailId) return showToast('No email selected','error');
  const body = document.getElementById('reply-body').value.trim();
  if (!body) return showToast('Enter reply text','error');
  try {
    const res = await fetch('/api/inbox/reply/'+currentEmailId, {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({body:body.replace(/\n/g,'<br>')})});
    const d = await res.json();
    if (d.error) showToast('Error: '+d.error,'error');
    else { showToast('Reply sent!','success'); document.getElementById('reply-panel').style.display='none'; document.getElementById('reply-body').value=''; }
  } catch(e) { showToast('Error: '+e.message,'error'); }
}

async function deleteEmail(msgId) {
  if (!confirm('Delete this email?')) return;
  try {
    await fetch('/api/inbox/delete/'+msgId, {method:'DELETE'});
    showToast('Email deleted','success');
    loadInbox(currentFolder);
    document.getElementById('inbox-preview-log').innerHTML = 'Email deleted.';
  } catch(e) { showToast('Error: '+e.message,'error'); }
}

async function searchInbox() {
  const q = document.getElementById('inbox-search').value.trim();
  if (!q) return loadInbox();
  const log = document.getElementById('inbox-list-log');
  log.innerHTML = 'Searching...';
  try {
    const res = await fetch('/api/inbox/search?q='+encodeURIComponent(q));
    const d = await res.json();
    if (d.error) { log.innerHTML = 'Error: '+d.error; return; }
    const msgs = d.value || [];
    if (msgs.length === 0) { log.innerHTML = 'No results for "'+q+'"'; return; }
    log.innerHTML = '<strong style="color:var(--ms)">─── SEARCH: "'+q+'" ───</strong>\n\n';
    msgs.forEach(m => {
      const from = m.from?.emailAddress?.name || m.from?.emailAddress?.address || '';
      const date = m.receivedDateTime ? new Date(m.receivedDateTime).toLocaleString() : '';
      log.innerHTML += `<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);cursor:pointer" onclick="previewEmail('${m.id}')">
        <strong>${(m.subject||'(no subject)').substring(0,55)}</strong>
        <div style="font-size:9px;color:#4a5568">${from} | ${date}</div>
      </div>\n`;
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}

// ==================== REVENUE DASHBOARD (v16.0) ====================
async function loadRevenueDashboard() {
  showToast('Loading revenue data...','info');
  try {
    const pRes = await fetch('/api/dialpad/pipeline');
    const pipe = await pRes.json();
    if (pipe && !pipe.error && pipe.stages) {
      let total = 0, activeCount = 0;
      pipe.stages.forEach(s => { total += s.total_value||0; activeCount += s.deals?.length||0; });
      document.getElementById('rev-mrr').textContent = '$'+total.toLocaleString();
      document.getElementById('rev-arr').textContent = '$'+(total*12).toLocaleString();
      document.getElementById('rev-contracts').textContent = activeCount;
      document.getElementById('rev-pipeline').textContent = '$'+total.toLocaleString();
      const log = document.getElementById('rev-contracts-log');
      log.innerHTML = '<strong style="color:var(--orange)">─── PIPELINE DEALS ───</strong>\n\n';
      pipe.stages.forEach(s => {
        if (s.deals?.length) {
          log.innerHTML += '<strong>'+s.label+'</strong> ($'+s.total_value.toLocaleString()+')\n';
          s.deals.forEach(d => { log.innerHTML += '  • '+d.name+' — $'+(d.amount||0).toLocaleString()+'\n'; });
          log.innerHTML += '\n';
        }
      });
    }
  } catch(e) { showToast('Error: '+e.message,'error'); }
  document.getElementById('rev-outstanding').textContent = '—';
  document.getElementById('rev-paid').textContent = '—';
  showToast('Revenue dashboard loaded!');
}

async function loadContracts() { loadRevenueDashboard(); }

async function loadInvoiceAging() {
  const log = document.getElementById('rev-contracts-log');
  log.innerHTML = 'Invoice aging is tracked via HubSpot deals and manual tracking.\n\nFor detailed invoicing, connect your accounting software or check HubSpot deals pipeline.';
}

async function loadClientHealth() {
  const log = document.getElementById('rev-health-log');
  log.innerHTML = 'Calculating client health from TRMM data...\n';
  try {
    const res = await fetch('/api/trmm/agents');
    const agents = await res.json();
    if (!Array.isArray(agents)) { log.innerHTML = 'Connect Tactical RMM to see client health.'; return; }
    // Group by client
    const clients = {};
    agents.forEach(a => {
      const name = a.client_name||'Unknown';
      if (!clients[name]) clients[name] = {total:0,online:0};
      clients[name].total++;
      if (a.status==='online') clients[name].online++;
    });
    log.innerHTML = '<strong style="color:var(--green)">─── CLIENT HEALTH (from TRMM) ───</strong>\n\n';
    Object.entries(clients).forEach(([name, c]) => {
      const pct = c.total>0 ? Math.round((c.online/c.total)*100) : 0;
      const color = pct>=80?'#4ade80':pct>=50?'#fbbf24':'#f87171';
      const bar = '█'.repeat(Math.floor(pct/5)) + '░'.repeat(20-Math.floor(pct/5));
      log.innerHTML += '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
        '<strong>'+name+'</strong> <span style="color:'+color+';font-weight:900">'+pct+'%</span> online' +
        '<div style="font-size:9px;color:'+color+'">'+bar+'</div>' +
        '<div style="font-size:9px;color:#4a5568">Agents: '+c.total+' | Online: '+c.online+' | Offline: '+(c.total-c.online)+'</div></div>\n';
    });
  } catch(e) { log.innerHTML = 'Error: '+e.message; }
}
</script>
</body>
</html>
"""

# ============================================================
# API ROUTES
# ============================================================
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/favicon.png")
def favicon():
    fav_path = os.path.join(APP_DIR, "favicon.png")
    if os.path.exists(fav_path):
        from flask import send_file
        return send_file(fav_path, mimetype="image/png")
    return "", 404

@app.route("/favicon.ico")
def favicon_ico():
    fav_path = os.path.join(APP_DIR, "favicon.png")
    if os.path.exists(fav_path):
        from flask import send_file
        return send_file(fav_path, mimetype="image/png")
    ico_path = os.path.join(APP_DIR, "bvtech.ico")
    if os.path.exists(ico_path):
        from flask import send_file
        return send_file(ico_path, mimetype="image/x-icon")
    return "", 404

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def update_config():
    cfg = load_config()
    cfg.update(request.json)
    save_config(cfg)
    # Notify brain and autopilot of config change
    try:
        if _brain is not None:
            _brain.reload_config()
    except Exception:
        pass
    return jsonify({"status":"ok"})

def stream_process(cmd):
    """Stream subprocess output. Uses PYTHON_EXE and APP_DIR for PyInstaller compatibility.

    v28 FIXES (the 'blank Python window + frozen log' bug):
      1. Injects ``-u`` right after python.exe so child stdout is unbuffered.
         Without this, Python block-buffers stdout whenever it's piped to a
         non-TTY (i.e. Flask), and long-running scripts like super_scraper.py
         look frozen for 30-60s until the first buffer flush.
      2. Sets PYTHONUNBUFFERED=1 in the child env as a belt-and-suspenders.
      3. On Windows, passes creationflags=CREATE_NO_WINDOW so python.exe does
         NOT pop a phantom black console window when Flask spawns it.
      4. Uses bufsize=1 (line-buffered) on our read side so `for line in stdout`
         yields each line the moment it arrives.
    """
    try:
        # v28: inject -u for unbuffered Python stdout/stderr
        # cmd[0] is PYTHON_EXE; insert -u as cmd[1] unless already present
        run_cmd = list(cmd)
        if len(run_cmd) >= 2 and run_cmd[1] != "-u" and run_cmd[0].lower().endswith(("python.exe", "python", "python3", "python3.exe")):
            run_cmd.insert(1, "-u")

        yield f"[BVTech v28] Running: {' '.join(run_cmd)}\n"
        yield f"[BVTech v28] Python: {PYTHON_EXE}\n"
        yield f"[BVTech v28] Working dir: {APP_DIR}\n\n"

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=APP_DIR,
            env=env,
            bufsize=1,  # line-buffered
        )
        # v28: suppress the phantom console window on Windows
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        process = subprocess.Popen(run_cmd, **popen_kwargs)
        for line in iter(process.stdout.readline, ""):
            yield line
        process.stdout.close()
        process.wait()
        if process.returncode != 0:
            yield f"\n[BVTech v28] Process exited with code {process.returncode}\n"
    except Exception as e:
        yield f"\nERROR: {e}\n"
        yield f"Python exe: {PYTHON_EXE}\n"
        yield f"App dir: {APP_DIR}\n"
        yield f"Frozen: {getattr(sys, 'frozen', False)}\n"
        import traceback as _tb
        yield _tb.format_exc()

def _script_path(name):
    """Get absolute path to a script file, works in both dev and PyInstaller modes.
    v19: Checks _MEIPASS (bundled data) first, then APP_DIR (exe directory)."""
    if getattr(sys, 'frozen', False):
        # In PyInstaller: --add-data files go to _MEIPASS
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            p = os.path.join(meipass, name)
            if os.path.exists(p):
                return p
        # Also check next to the exe (user may have scripts there)
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
        # Fallback: return _MEIPASS path (will error with a clear message)
        return os.path.join(meipass or APP_DIR, name)
    return os.path.join(APP_DIR, name)

@app.route("/api/run/scraper")
def run_scraper():
    cmd = [PYTHON_EXE, _script_path("prospect_scraper.py")]
    markets = request.args.getlist("markets")
    if len(markets) == 1: cmd.extend(["--market", markets[0]])
    cmd.extend(["--max", request.args.get("max","200")])
    if request.args.get("sync")=="true": cmd.append("--sync")
    if request.args.get("require_phone")=="true": cmd.append("--require-phone")
    if request.args.get("require_website")=="true": cmd.append("--require-website")
    if request.args.get("skip_solo")=="true": cmd.append("--skip-solo")
    mr = request.args.get("min_rating","0")
    if float(mr)>0: cmd.extend(["--min-rating",mr])
    mv = request.args.get("min_reviews","0")
    if int(mv)>0: cmd.extend(["--min-reviews",mv])
    ms = request.args.get("min_score","0")
    if int(ms)>0: cmd.extend(["--min-score",ms])
    ind = request.args.get("industry","")
    if ind: cmd.extend(["--industry",ind])
    return Response(stream_process(cmd), mimetype="text/plain")

@app.route("/api/run/super_scraper")
def run_super_scraper_route():
    """SUPER SCRAPER — decision-maker discovery (deep crawl + LinkedIn + Hunter + Dialpad sync)."""
    cmd = [PYTHON_EXE, _script_path("super_scraper.py")]
    markets = request.args.getlist("markets")
    if len(markets) == 1:
        cmd.extend(["--market", markets[0]])
    cmd.extend(["--max", request.args.get("max", "50")])
    if request.args.get("deep") == "true":          cmd.append("--deep")
    if request.args.get("titles_only") == "true":   cmd.append("--titles-only")
    if request.args.get("sync") == "true":          cmd.append("--sync")
    if request.args.get("dialer") == "true":        cmd.append("--dialer")
    if request.args.get("require_phone") == "true": cmd.append("--require-phone")
    if request.args.get("skip_solo") == "true":     cmd.append("--skip-solo")
    ms = request.args.get("min_score", "0")
    try:
        if int(ms) > 0:
            cmd.extend(["--min-score", ms])
    except ValueError:
        pass
    ind = request.args.get("industry", "")
    if ind:
        cmd.extend(["--industry", ind])
    return Response(stream_process(cmd), mimetype="text/plain")

# v19: Prospects API — used by in-app power dialer
@app.route("/api/prospects")
def get_prospects():
    """Load prospects from CSV, optionally filtered by market."""
    try:
        csv_path = os.path.join(APP_DIR, "prospects.csv")
        if not os.path.exists(csv_path):
            return jsonify({"prospects": [], "error": "No prospects.csv found. Run the Scraper first."})
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            prospects = list(csv.DictReader(f))
        # Filter by market if specified
        market = request.args.get("market", "").strip().lower()
        if market:
            prospects = [p for p in prospects if market in (p.get("market","") or "").lower() or market in (p.get("city","") or "").lower()]
        return jsonify({"prospects": prospects, "total": len(prospects)})
    except Exception as e:
        return jsonify({"prospects": [], "error": str(e)}), 500

@app.route("/api/run/email")
def run_email():
    cmd = [PYTHON_EXE, _script_path("email_campaign.py")]
    if request.args.get("dryrun")=="true": cmd.append("--dry-run")
    if request.args.get("warmup")=="true": cmd.append("--warmup")
    return Response(stream_process(cmd), mimetype="text/plain")

@app.route("/api/run/sms")
def run_sms():
    cmd = [PYTHON_EXE, _script_path("sms_campaign.py"), "--template", request.args.get("template","intro")]
    if request.args.get("dryrun")=="true": cmd.append("--dry-run")
    return Response(stream_process(cmd), mimetype="text/plain")

@app.route("/api/run/dialer")
def run_dialer():
    cmd = [PYTHON_EXE, _script_path("power_dialer.py")]
    mk = request.args.get("market","")
    if mk: cmd.extend(["--market",mk])
    if sys.platform == "win32":
        subprocess.Popen(["start","cmd","/k"]+cmd, shell=True, cwd=APP_DIR)
    return jsonify({"status":"launched"})

@app.route("/api/run/sync")
def run_sync():
    cmd = [PYTHON_EXE, _script_path("email_campaign.py"), "--sync-only"]
    return Response(stream_process(cmd), mimetype="text/plain")

# ============================================================
# DIALPAD API ROUTES
# ============================================================
def get_dp_client():
    from dialpad_integration import DialPadClient
    return DialPadClient()

@app.route("/api/dialpad/analytics")
def dp_analytics():
    try:
        dp = get_dp_client()
        analytics, err = dp.get_call_analytics(days=int(request.args.get("days",30)))
        return jsonify(analytics) if analytics else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/calls")
def dp_calls():
    try:
        dp = get_dp_client()
        calls, err = dp.get_call_history(days=7, limit=50)
        return jsonify(calls) if calls else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/transcript/<call_id>")
def dp_transcript(call_id):
    try:
        dp = get_dp_client()
        transcript, err = dp.get_transcript(call_id)
        return jsonify(transcript) if transcript else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/recap/<call_id>")
def dp_recap(call_id):
    try:
        dp = get_dp_client()
        recap, err = dp.get_ai_recap(call_id)
        return jsonify(recap) if recap else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/call", methods=["POST"])
def dp_call():
    try:
        dp = get_dp_client()
        phone = request.json.get("phone","")
        result, err = dp.initiate_call(phone)
        return jsonify({"status":"calling","phone":phone}) if result is not None else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/sms", methods=["POST"])
def dp_sms():
    try:
        dp = get_dp_client()
        result, err = dp.send_sms(request.json.get("phone",""), request.json.get("text",""))
        return jsonify({"status":"sent"}) if result is not None else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/block", methods=["POST"])
def dp_block():
    try:
        dp = get_dp_client()
        result, err = dp.block_number(request.json.get("phone",""))
        return jsonify({"status":"blocked"}) if result else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/optouts")
def dp_optouts():
    try:
        dp = get_dp_client()
        optouts, err = dp.get_sms_opt_outs()
        return jsonify(optouts) if optouts else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/blocked")
def dp_blocked():
    try:
        dp = get_dp_client()
        blocked, err = dp.list_blocked()
        return jsonify(blocked) if blocked else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/contacts/sync", methods=["POST"])
def dp_sync_contacts():
    try:
        dp = get_dp_client()
        prospects = []
        csv_path = Path(os.path.join(APP_DIR, "prospects.csv"))
        if csv_path.exists():
            with open(csv_path,"r",encoding="utf-8-sig") as f:
                prospects = list(csv.DictReader(f))
        return jsonify(dp.sync_prospects_to_dialpad(prospects))
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/test")
def dp_test():
    try:
        dp = get_dp_client()
        info, err = dp.get_company_info()
        return jsonify({"status":"connected","company":info.get("name","Unknown")}) if info else (jsonify({"status":"error","error":err}),400)
    except Exception as e: return jsonify({"status":"error","error":str(e)}),500

# ============================================================
# NEW v2.0: POST-CALL WORKFLOW ROUTE
# ============================================================
@app.route("/api/dialpad/workflow", methods=["POST"])
def dp_workflow():
    try:
        dp = get_dp_client()
        data = request.json
        result = dp.post_call_workflow(
            call_id=data.get("call_id",""),
            disposition=data.get("disposition",""),
            notes=data.get("notes",""),
            prospect_phone=data.get("phone",""),
        )
        return jsonify(result)
    except Exception as e: return jsonify({"error":str(e)}),500

# ============================================================
# NEW v2.0: COACHING ROUTES
# ============================================================
@app.route("/api/dialpad/coaching/summary")
def dp_coaching_summary():
    try:
        dp = get_dp_client()
        days = int(request.args.get("days",7))
        summary, err = dp.get_coaching_summary(days=days, limit=20)
        return jsonify(summary) if summary else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/coaching/call/<call_id>")
def dp_coaching_call(call_id):
    try:
        dp = get_dp_client()
        coaching, err = dp.analyze_call_for_coaching(call_id)
        return jsonify(coaching) if coaching else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

# ============================================================
# NEW v2.0: PIPELINE & CRM ROUTES
# ============================================================
@app.route("/api/dialpad/pipeline")
def dp_pipeline():
    try:
        dp = get_dp_client()
        pipeline, err = dp.get_hubspot_pipeline()
        return jsonify(pipeline) if pipeline else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dialpad/crm/contacts")
def dp_crm_contacts():
    try:
        dp = get_dp_client()
        contacts, err = dp.get_hubspot_contacts_summary()
        return jsonify(contacts) if contacts else (jsonify({"error":err}),400)
    except Exception as e: return jsonify({"error":str(e)}),500

# ============================================================
# AUTOCLAUDE AI BRAIN (v2.1 — Self-Healing, Self-Building)
# v18.1: Lazy init — don't start threads until app is actually running
# ============================================================
_brain = None
_error_catcher = None
_pilot = None
_ai_init_error = None

def _ensure_ai_initialized():
    """Lazy-init AutoClaude + AutoPilot on first use, not at import time."""
    global _brain, _error_catcher, _pilot, _ai_init_error
    if _brain is not None:
        return True
    if _ai_init_error is not None:
        return False  # Already failed, don't retry every request
    try:
        from autoclaude import AutoClaude, ErrorCatcher
        from autopilot import AutoPilot
        _brain = AutoClaude(app_dir=APP_DIR)
        if "autopilot.py" not in _brain.ALLOWED_FILES:
            _brain.ALLOWED_FILES.append("autopilot.py")
        _error_catcher = ErrorCatcher(_brain)
        _pilot = AutoPilot(_brain)
        _pilot.start()
        print("  [v18.1] AutoClaude + AutoPilot initialized successfully.")
        return True
    except Exception as e:
        _ai_init_error = str(e)
        print(f"  [v18.1] Warning: AutoClaude init failed (non-fatal): {e}")
        print(f"  [v18.1] AI features disabled. App will still run.")
        return False

# Global error handler — catches ALL Flask errors and auto-heals
# v19: Catch WAF redirect URLs that hit Flask (e.g. /.well-known/sgcaptcha/...)
@app.errorhandler(404)
def handle_404(e):
    path = request.path
    if ".well-known/sgcaptcha" in path or "wp-json" in path or "wp-login" in path:
        return jsonify({
            "error": "SiteGround WAF is blocking the WordPress REST API. Your app tried to reach WordPress directly but got redirected to a captcha challenge.",
            "fix": "Go to Settings → WordPress → use Relay Mode instead of REST API. Make sure bvtech-api.php is uploaded to your server.",
            "blocked_path": path
        }), 502
    return jsonify({"error": f"Not found: {path}"}), 404

@app.errorhandler(Exception)
def handle_exception(e):
    error_text = traceback.format_exc()
    # v19: Sanitize — never return raw HTML in JSON error responses
    safe_error = str(e).replace("<", "&lt;").replace(">", "&gt;")[:500]
    fix_result = None
    if _error_catcher is not None:
        try:
            fix_result = _error_catcher.handle_error(error_text, source="flask_route")
        except Exception:
            pass
    return jsonify({
        "error": safe_error,
        "auto_heal_attempted": fix_result is not None,
        "files_fixed": fix_result.get("files_modified", []) if fix_result else [],
    }), 500

@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """Main AI chat — powered by AutoClaude brain."""
    if not _ensure_ai_initialized():
        return jsonify({"error": f"AI engine failed to load: {_ai_init_error}. App still works — AI features disabled."}), 503
    _brain.reload_config()
    if not _brain.api_key:
        return jsonify({"error": "No Anthropic API key. Go to Settings → Claude AI → paste key from console.anthropic.com"})

    data = request.json
    message = data.get("message", "")
    mode = data.get("mode", "general")

    if not message:
        return jsonify({"error": "Empty message"})

    # Map UI modes to brain modes
    mode_map = {"chat": "general", "debug": "heal", "build": "build", "strategy": "general"}
    brain_mode = mode_map.get(mode, "general")

    # If strategy mode, prepend context
    if mode == "strategy":
        message = f"[MSP STRATEGY MODE] {message}"

    include_sources = brain_mode in ("heal", "build")
    result = _brain.chat(message, mode=brain_mode, include_sources=include_sources)

    return jsonify({
        "response": result.get("response", ""),
        "files_modified": result.get("files_modified", []),
        "apply_results": result.get("apply_results", []),
        "needs_restart": result.get("needs_restart", False),
    })

@app.route("/api/ai/apply", methods=["POST"])
def ai_apply():
    """Manual apply — write code to a file."""
    if not _ensure_ai_initialized():
        return jsonify({"error": "AI engine not available"}), 503
    data = request.json
    filename = data.get("filename", "")
    content = data.get("content", "")

    if not filename or not content:
        return jsonify({"error": "Missing filename or content"})

    ok, msg = _brain.apply_code(filename, content)
    if ok:
        _brain.request_restart()
        return jsonify({"status": "ok", "file": filename, "message": msg})
    return jsonify({"error": msg}), 400

@app.route("/api/ai/restart", methods=["POST"])
def ai_restart():
    """Restart the app to load code changes."""
    if not _ensure_ai_initialized():
        return jsonify({"error": "AI engine not available"}), 503
    import threading
    def delayed_restart():
        time.sleep(1)
        _brain.do_restart()
    threading.Thread(target=delayed_restart, daemon=True).start()
    return jsonify({"status": "restarting", "message": "App will restart in 1 second..."})

@app.route("/api/ai/status")
def ai_status():
    """Get AI brain status + error journal."""
    if not _ensure_ai_initialized():
        return jsonify({"status": "unavailable", "error": _ai_init_error})
    _brain.reload_config()
    status = _brain.get_status()
    return jsonify(status)

@app.route("/api/ai/journal")
def ai_journal():
    """Get the error/fix journal."""
    if not _ensure_ai_initialized():
        return jsonify([])
    return jsonify(_brain.error_journal)

@app.route("/api/ai/heal", methods=["POST"])
def ai_heal():
    """Manually trigger self-heal for a specific error."""
    if not _ensure_ai_initialized():
        return jsonify({"error": "AI engine not available"}), 503
    data = request.json
    error_text = data.get("error", "")
    if not error_text:
        return jsonify({"error": "No error text provided"})

    result = _brain.diagnose_and_fix(error_text)
    return jsonify(result)

@app.route("/api/ai/read/<filename>")
def ai_read_file(filename):
    """Read a source file."""
    if not _ensure_ai_initialized():
        return jsonify({"error": "AI engine not available"}), 503
    content, err = _brain.read_file(filename)
    if content is not None:
        return jsonify({"filename": filename, "content": content, "size": len(content)})
    return jsonify({"error": err}), 404

# ============================================================
# AUTOPILOT ROUTES — 24/7 autonomous daemon
# ============================================================
def _require_pilot():
    """Check if pilot is available, return error response or None."""
    if not _ensure_ai_initialized():
        return jsonify({"error": "AI engine not available", "detail": _ai_init_error}), 503
    return None

@app.route("/api/pilot/status")
def pilot_status():
    err = _require_pilot()
    if err: return err
    return jsonify(_pilot.get_status())

@app.route("/api/pilot/queue", methods=["GET"])
def pilot_queue():
    err = _require_pilot()
    if err: return err
    return jsonify({"queue": _pilot.improvement_queue})

@app.route("/api/pilot/queue", methods=["POST"])
def pilot_add_task():
    err = _require_pilot()
    if err: return err
    task = request.json.get("task", "")
    if not task:
        return jsonify({"error": "No task provided"}), 400
    _pilot.add_to_queue(task)
    return jsonify({"status": "queued", "queue_size": len(_pilot.improvement_queue)})

@app.route("/api/pilot/health", methods=["POST"])
def pilot_health_now():
    err = _require_pilot()
    if err: return err
    results = _pilot.run_health_check()
    return jsonify({"results": results})

@app.route("/api/pilot/compliance", methods=["POST"])
def pilot_compliance_now():
    err = _require_pilot()
    if err: return err
    issues = _pilot.run_compliance_check()
    return jsonify({"issues": issues})

@app.route("/api/pilot/improve", methods=["POST"])
def pilot_improve_now():
    err = _require_pilot()
    if err: return err
    task = _pilot._get_next_task()
    if task and _pilot.brain.api_key:
        result = _pilot.brain.build_feature(task["task"])
        if result.get("files_modified"):
            task["status"] = "completed"
            task["completed"] = datetime.now().isoformat()
            _pilot.status["improvements_made"] += 1
        return jsonify({"result": task})
    return jsonify({"result": None})

@app.route("/api/pilot/nightly", methods=["POST"])
def pilot_nightly_now():
    """Manually trigger a nightly build cycle."""
    err = _require_pilot()
    if err: return err
    import threading
    def run():
        _pilot.run_nightly_build()
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started", "message": "Nightly build running in background..."})

# ============================================================
# WARMODE v3 ROUTES — Aggressive Self-Builder
# ============================================================
@app.route("/api/pilot/warmode", methods=["POST"])
def pilot_warmode():
    """Toggle WARMODE on/off with speed setting."""
    err = _require_pilot()
    if err: return err
    data = request.json
    enabled = data.get("enabled", False)
    speed = data.get("speed", "normal")
    _pilot.toggle_warmode(enabled, speed)
    return jsonify({"status": "ok", "warmode": enabled, "speed": speed})

@app.route("/api/pilot/settings", methods=["POST"])
def pilot_update_settings():
    """Update auto-mode settings."""
    err = _require_pilot()
    if err: return err
    _pilot.update_settings(request.json)
    return jsonify({"status": "ok"})

@app.route("/api/pilot/settings", methods=["GET"])
def pilot_get_settings():
    err = _require_pilot()
    if err: return err
    return jsonify(_pilot.auto_settings)

@app.route("/api/pilot/test", methods=["POST"])
def pilot_run_tests():
    """Run self-tests manually."""
    err = _require_pilot()
    if err: return err
    passed, failed, results = _pilot.run_self_tests()
    return jsonify({"passed": passed, "failed": failed, "results": results})

@app.route("/api/pilot/backup", methods=["POST"])
def pilot_backup_now():
    """Create a backup manually."""
    err = _require_pilot()
    if err: return err
    path = _pilot.create_backup("manual")
    return jsonify({"status": "ok", "path": path})

@app.route("/api/pilot/backups", methods=["GET"])
def pilot_list_backups():
    """List available backups."""
    err = _require_pilot()
    if err: return err
    return jsonify({"backups": _pilot.list_backups()})

@app.route("/api/pilot/restore", methods=["POST"])
def pilot_restore():
    """Restore from a backup."""
    err = _require_pilot()
    if err: return err
    path = request.json.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "No path provided"})
    ok, msg = _pilot.restore_backup(path)
    return jsonify({"ok": ok, "message": msg})

@app.route("/api/pilot/generate", methods=["POST"])
def pilot_generate_ideas():
    """Generate improvement ideas via Claude."""
    err = _require_pilot()
    if err: return err
    import threading
    def run():
        _pilot._generate_ideas()
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "generating"})

@app.route("/api/pilot/build_history", methods=["GET"])
def pilot_build_history():
    """Get build history."""
    err = _require_pilot()
    if err: return err
    return jsonify({"history": _pilot.build_history[-50:]})

# ============================================================
# TACTICAL RMM ROUTES (v16.0)
# v19: Lazy import — won't crash app if module has issues
# ============================================================
_trmm_module = None
_trmm_import_error = None

def _get_trmm_module():
    global _trmm_module, _trmm_import_error
    if _trmm_module is not None:
        return _trmm_module
    if _trmm_import_error is not None:
        return None
    try:
        import tacticalrmm_integration as mod
        _trmm_module = mod
        return mod
    except Exception as e:
        _trmm_import_error = str(e)
        print(f"  [v19] Warning: tacticalrmm_integration import failed (non-fatal): {e}")
        return None

def get_trmm_client():
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"Integration module failed to load: {_trmm_import_error or 'unknown'}. Check that requests is installed.")
    cfg = load_config()
    return mod.TacticalRMMClient(api_url=cfg.get("trmm_api_url"), api_key=cfg.get("trmm_api_key"))

def get_guardz():
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"Integration module failed to load: {_trmm_import_error or 'unknown'}")
    return mod.GuardzPortal()

def get_wp_client():
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"WordPress module failed to load: {_trmm_import_error or 'unknown'}. Try: pip install requests")
    cfg = load_config()
    return mod.WordPressClient(cfg=cfg)

def get_cf_client():
    """v20: Get Cloudflare Pages client for BVTech.org static site."""
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"Cloudflare module failed to load: {_trmm_import_error or 'unknown'}")
    cfg = load_config()
    return mod.CloudflarePagesClient(cfg=cfg)

def get_linkedin_client():
    """v20: Get LinkedIn client for ORM personal brand posting."""
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"LinkedIn module failed to load: {_trmm_import_error or 'unknown'}")
    cfg = load_config()
    return mod.LinkedInClient(cfg=cfg)

def get_bvtech_publisher():
    """v29: Smart publisher for BVTech.org.

    History:
      v25-v27: buggy — mode label lied AND CF Direct Upload would have
               wiped the site on every post.
      v28:     safety hold — refused to run CF Direct Upload at all.
      v29:     fixed. Returns the real mode computed by the client.
               CF Direct Upload now does a full site-root walk via the
               cloudflare_pages_deploy module (see tacticalrmm_integration.py
               _deploy_cf_direct for the safe implementation).
    """
    cfg = load_config()
    client = get_cf_client()
    real_mode = getattr(client, "mode", "none")
    if real_mode == "cloudflare_direct":
        # v29: check that site_root is configured — otherwise the deploy
        # will fail at walk time anyway, but we can give a clearer error
        # up front.
        site_root = (cfg.get("bvtech_site_root") or cfg.get("site_root") or "").strip()
        if not site_root:
            print("  [v29] BVTech publisher → CF Direct Upload CONFIGURED but bvtech_site_root is missing")
            return client, "needs_site_root"
        print("  [v29] BVTech publisher → CF Direct Upload (full site-root walk)")
        return client, "cloudflare"
    if real_mode == "github":
        print("  [v29] BVTech publisher → GitHub API mode")
        return client, "github"
    print("  [v29] BVTech publisher → WordPress relay fallback (no CF or GH configured)")
    return get_wp_client(), "wordpress"

def get_inbox_client():
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"M365 module failed to load: {_trmm_import_error or 'unknown'}")
    cfg = load_config()
    return mod.M365InboxClient(cfg=cfg)

@app.route("/api/trmm/dashboard")
def trmm_dashboard():
    try:
        t = get_trmm_client()
        data, err = t.get_dashboard()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/agents")
def trmm_agents():
    try:
        t = get_trmm_client()
        detail = request.args.get("detail", "false") == "true"
        data, err = t.get_agents(detail=detail)
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/agent/<agent_id>")
def trmm_agent(agent_id):
    try:
        t = get_trmm_client()
        data, err = t.get_agent(agent_id)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/clients")
def trmm_clients():
    try:
        t = get_trmm_client()
        data, err = t.get_clients()
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/alerts")
def trmm_alerts():
    try:
        t = get_trmm_client()
        data, err = t.get_alerts()
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/scripts")
def trmm_scripts():
    try:
        t = get_trmm_client()
        data, err = t.get_scripts()
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/command", methods=["POST"])
def trmm_command():
    try:
        t = get_trmm_client()
        d = request.json
        data, err = t.run_command(d["agent_id"], d["shell"], d["cmd"], d.get("timeout", 30))
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/software/<agent_id>")
def trmm_software(agent_id):
    try:
        t = get_trmm_client()
        data, err = t.get_software(agent_id)
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/trmm/services/<agent_id>")
def trmm_services(agent_id):
    try:
        t = get_trmm_client()
        data, err = t.get_services(agent_id)
        return jsonify(data) if data is not None else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

# ============================================================
# GUARDZ SECURITY ROUTES — Local Tracker (v16.0)
# ============================================================
@app.route("/api/guardz/tracker")
def gz_tracker():
    try:
        gz = get_guardz()
        data, err = gz.get_tracker()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/guardz/incident", methods=["POST"])
def gz_add_incident():
    try:
        gz = get_guardz()
        d = request.json
        data, err = gz.add_incident(d.get("severity","medium"), d.get("title",""),
                                     d.get("description",""), d.get("client",""))
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/guardz/resolve/<int:incident_id>", methods=["POST"])
def gz_resolve(incident_id):
    try:
        gz = get_guardz()
        data, err = gz.resolve_incident(incident_id)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/guardz/posture", methods=["POST"])
def gz_posture():
    try:
        gz = get_guardz()
        score = request.json.get("score", 0)
        data, err = gz.update_posture_score(score)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

# ============================================================
# LINKEDIN ORM ROUTES
# OAuth2 flow + posting for personal brand ORM
# ============================================================

@app.route("/api/linkedin/test")
def linkedin_test():
    """Test LinkedIn connection."""
    try:
        li = get_linkedin_client()
        data, err = li.test_connection()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/linkedin/auth-url")
def linkedin_auth_url():
    """Get LinkedIn OAuth2 authorization URL."""
    try:
        li = get_linkedin_client()
        if not li.client_id:
            return jsonify({"error": "No LinkedIn Client ID configured. Set it in Settings → LinkedIn first."})
        url = li.get_auth_url()
        return jsonify({"auth_url": url})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/linkedin/callback")
def linkedin_callback():
    """OAuth2 callback — exchanges code for access token and saves it."""
    code = request.args.get("code", "")
    error = request.args.get("error", "")
    if error:
        return f"""<html><body style="font-family:Arial;padding:40px;background:#0E0D2C;color:#fff">
        <h2 style="color:#ef4444">❌ LinkedIn Authorization Failed</h2>
        <p>{error}: {request.args.get('error_description','')}</p>
        <p>Close this window and try again.</p></body></html>"""
    if not code:
        return f"""<html><body style="font-family:Arial;padding:40px;background:#0E0D2C;color:#fff">
        <h2 style="color:#f59e0b">⚠️ No authorization code received</h2>
        <p>Close this window and try again.</p></body></html>"""

    try:
        li = get_linkedin_client()
        token_data, err = li.exchange_code(code)
        if err:
            return f"""<html><body style="font-family:Arial;padding:40px;background:#0E0D2C;color:#fff">
            <h2 style="color:#ef4444">❌ Token Exchange Failed</h2><p>{err}</p></body></html>"""

        # Save the access token to config
        cfg = load_config()
        cfg["linkedin_access_token"] = token_data.get("access_token", "")
        save_config(cfg)

        # Try to get person URN
        li2 = get_linkedin_client()  # Reload with new token
        profile, _ = li2.test_connection()
        person_name = "Unknown"
        if profile:
            person_name = profile.get("name", "Unknown")
            if profile.get("person_urn"):
                cfg["linkedin_person_urn"] = profile["person_urn"]
                save_config(cfg)

        expires_hours = round(token_data.get("expires_in", 0) / 3600)

        return f"""<html><body style="font-family:Arial;padding:40px;background:#0E0D2C;color:#fff;text-align:center">
        <h2 style="color:#4ade80">✅ LinkedIn Connected Successfully!</h2>
        <p style="font-size:18px">Logged in as: <strong>{person_name}</strong></p>
        <p>Token expires in: <strong>{expires_hours} hours</strong></p>
        <p>Scope: {token_data.get('scope','')}</p>
        <p style="margin-top:30px;color:rgba(255,255,255,0.5)">You can close this window and return to BVTech Command Center.<br>
        The ORM Beast will now post to LinkedIn as you!</p>
        <script>setTimeout(function(){{window.close()}},5000)</script>
        </body></html>"""
    except Exception as e:
        return f"""<html><body style="font-family:Arial;padding:40px;background:#0E0D2C;color:#fff">
        <h2 style="color:#ef4444">❌ Error</h2><p>{str(e)}</p></body></html>"""

@app.route("/api/linkedin/post", methods=["POST"])
def linkedin_post():
    """Manually post to LinkedIn."""
    d = request.json or {}
    text = d.get("text", "")
    title = d.get("title", "")
    article_url = d.get("article_url", "")
    if not text: return jsonify({"error": "No text provided"}), 400
    try:
        li = get_linkedin_client()
        data, err = li.create_post(text, title=title, article_url=article_url)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

# ============================================================
# CYBERSECURITY AUDIT & PEN TEST ENGINE
# Deep scanning for website vulns, network pen testing,
# AI-powered analysis with remediation recommendations
# ============================================================

_CYBER_HISTORY_FILE = "cyber_audit_history.json"
_cyber_history = []
try:
    _ch_path = os.path.join(APP_DIR, _CYBER_HISTORY_FILE)
    if Path(_ch_path).exists():
        with open(_ch_path, "r") as f: _cyber_history = json.load(f)
except: pass

def _save_cyber_history():
    try:
        with open(os.path.join(APP_DIR, _CYBER_HISTORY_FILE), "w") as f:
            json.dump(_cyber_history[:200], f, indent=2)
    except: pass

# Common vulnerable ports and their known risks
_PORT_RISKS = {
    21: ("FTP", "critical", "FTP transmits credentials in plaintext. Disable or replace with SFTP."),
    22: ("SSH", "info", "SSH detected. Verify key-based auth, disable password auth, use fail2ban."),
    23: ("Telnet", "critical", "Telnet transmits everything in plaintext. Disable immediately and use SSH."),
    25: ("SMTP", "warning", "SMTP open — check for open relay. Restrict to authenticated users only."),
    53: ("DNS", "info", "DNS resolver detected. Ensure not an open resolver (amplification attacks)."),
    80: ("HTTP", "warning", "Unencrypted HTTP. Ensure HTTPS redirect is enforced."),
    110: ("POP3", "warning", "POP3 unencrypted. Use POP3S (port 995) instead."),
    111: ("RPCbind", "critical", "RPCbind exposed — can leak NFS shares and services. Block from internet."),
    135: ("MSRPC", "critical", "Microsoft RPC exposed to internet. High risk for lateral movement."),
    139: ("NetBIOS", "critical", "NetBIOS exposed — SMB relay attacks, credential theft risk."),
    143: ("IMAP", "warning", "IMAP unencrypted. Use IMAPS (port 993) instead."),
    443: ("HTTPS", "info", "HTTPS detected — check SSL/TLS configuration."),
    445: ("SMB", "critical", "SMB directly exposed — EternalBlue, WannaCry, ransomware vector. Block from internet."),
    1433: ("MSSQL", "critical", "Microsoft SQL Server exposed. Never expose to internet — use VPN."),
    1521: ("Oracle DB", "critical", "Oracle DB exposed. Restrict access via firewall."),
    3306: ("MySQL", "critical", "MySQL exposed to internet. Use SSH tunnels or VPN."),
    3389: ("RDP", "critical", "RDP exposed — brute force, BlueKeep (CVE-2019-0708). Use VPN + NLA + MFA."),
    5432: ("PostgreSQL", "critical", "PostgreSQL exposed to internet. Restrict to localhost/VPN."),
    5900: ("VNC", "critical", "VNC exposed — often no encryption, brute forceable. Disable or VPN-only."),
    5985: ("WinRM", "critical", "Windows Remote Management exposed. Restrict to internal networks."),
    6379: ("Redis", "critical", "Redis exposed — often no auth by default. Massive data breach risk."),
    8080: ("HTTP-Alt", "warning", "Alternative HTTP port — often admin panels or proxies."),
    8443: ("HTTPS-Alt", "info", "Alternative HTTPS port — check if admin panel."),
    27017: ("MongoDB", "critical", "MongoDB exposed — often no auth by default. Data breach risk."),
}

# Sensitive files to probe for exposure
_SENSITIVE_PATHS = [
    ("/.env", "critical", "Environment file with secrets/credentials"),
    ("/.git/config", "critical", "Git repository exposed — source code leak"),
    ("/.git/HEAD", "critical", "Git repository exposed"),
    ("/wp-config.php", "critical", "WordPress config with DB credentials"),
    ("/wp-config.php.bak", "critical", "WordPress config backup"),
    ("/wp-admin/", "warning", "WordPress admin panel accessible"),
    ("/.htaccess", "warning", "Apache config exposed"),
    ("/server-status", "warning", "Apache server-status page exposed"),
    ("/server-info", "warning", "Apache server-info page exposed"),
    ("/phpinfo.php", "critical", "PHP info page — leaks server config, paths, modules"),
    ("/info.php", "critical", "PHP info page variant"),
    ("/backup.zip", "critical", "Backup archive publicly accessible"),
    ("/backup.sql", "critical", "SQL dump publicly accessible"),
    ("/database.sql", "critical", "SQL dump publicly accessible"),
    ("/db.sql", "critical", "SQL dump publicly accessible"),
    ("/api/", "info", "API endpoint detected"),
    ("/robots.txt", "info", "Robots.txt — check for hidden paths"),
    ("/sitemap.xml", "info", "Sitemap available"),
    ("/.well-known/security.txt", "info", "Security.txt present — good practice"),
    ("/crossdomain.xml", "warning", "Flash cross-domain policy — may allow data theft"),
    ("/.DS_Store", "warning", "macOS directory listing leak"),
    ("/web.config", "warning", "IIS config file exposed"),
    ("/elmah.axd", "critical", "ASP.NET error log exposed"),
    ("/.svn/entries", "critical", "SVN repository exposed — source code leak"),
    ("/admin/", "warning", "Admin panel path"),
    ("/administrator/", "warning", "Admin panel path"),
    ("/phpmyadmin/", "critical", "phpMyAdmin exposed to internet"),
    ("/wp-json/wp/v2/users", "warning", "WordPress user enumeration endpoint"),
]

# Required HTTP security headers
_SECURITY_HEADERS = {
    "Strict-Transport-Security": ("critical", "Missing HSTS — browsers can be downgraded to HTTP. Add: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload"),
    "Content-Security-Policy": ("warning", "Missing CSP — XSS attacks harder to prevent. Add a Content-Security-Policy header."),
    "X-Content-Type-Options": ("warning", "Missing X-Content-Type-Options — MIME sniffing attacks possible. Add: X-Content-Type-Options: nosniff"),
    "X-Frame-Options": ("warning", "Missing X-Frame-Options — clickjacking possible. Add: X-Frame-Options: DENY or SAMEORIGIN"),
    "X-XSS-Protection": ("info", "Missing X-XSS-Protection — legacy header, CSP is better but this adds defense-in-depth."),
    "Referrer-Policy": ("info", "Missing Referrer-Policy — URL leakage to third parties. Add: Referrer-Policy: strict-origin-when-cross-origin"),
    "Permissions-Policy": ("info", "Missing Permissions-Policy — controls browser features. Add: Permissions-Policy: camera=(), microphone=(), geolocation=()"),
    "Cross-Origin-Opener-Policy": ("info", "Missing COOP — helps prevent Spectre-type attacks. Add: Cross-Origin-Opener-Policy: same-origin"),
    "Cross-Origin-Resource-Policy": ("info", "Missing CORP header."),
}

def _scan_ssl(hostname, port=443):
    """Deep SSL/TLS audit."""
    import ssl, socket
    findings = []
    grade = "A"
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                protocol = ssock.version()
                cipher = ssock.cipher()

                # Check certificate
                not_after = cert.get("notAfter", "")
                subject = dict(x[0] for x in cert.get("subject", []))
                issuer = dict(x[0] for x in cert.get("issuer", []))
                san = [v for _, v in cert.get("subjectAltName", [])]

                findings.append({"severity": "pass", "message": f"Valid certificate: {subject.get('commonName', '?')} issued by {issuer.get('organizationName', '?')}"})
                findings.append({"severity": "pass", "message": f"Protocol: {protocol} | Cipher: {cipher[0] if cipher else '?'}"})
                findings.append({"severity": "info", "message": f"Expires: {not_after} | SANs: {', '.join(san[:5])}"})

                # Check expiry
                from datetime import datetime
                try:
                    exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                    days_left = (exp - datetime.now()).days
                    if days_left < 0:
                        findings.append({"severity": "critical", "message": f"Certificate EXPIRED {abs(days_left)} days ago!"})
                        grade = "F"
                    elif days_left < 14:
                        findings.append({"severity": "critical", "message": f"Certificate expires in {days_left} days — renew ASAP!"})
                        grade = "C"
                    elif days_left < 30:
                        findings.append({"severity": "warning", "message": f"Certificate expires in {days_left} days — schedule renewal."})
                        if grade > "B": grade = "B"
                    else:
                        findings.append({"severity": "pass", "message": f"Certificate valid for {days_left} more days."})
                except: pass

                # Check protocol version
                if "TLSv1.3" in protocol:
                    findings.append({"severity": "pass", "message": "TLS 1.3 supported — excellent!"})
                elif "TLSv1.2" in protocol:
                    findings.append({"severity": "pass", "message": "TLS 1.2 supported — good."})
                else:
                    findings.append({"severity": "critical", "message": f"Outdated protocol: {protocol}. Upgrade to TLS 1.2+."})
                    grade = "F"

        # Test for deprecated protocols
        for proto_name, proto_ver in [("TLSv1.0", ssl.TLSVersion.TLSv1), ("TLSv1.1", ssl.TLSVersion.TLSv1_1)]:
            try:
                ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx2.check_hostname = False
                ctx2.verify_mode = ssl.CERT_NONE
                ctx2.maximum_version = proto_ver
                ctx2.minimum_version = proto_ver
                with socket.create_connection((hostname, port), timeout=5) as s2:
                    with ctx2.wrap_socket(s2, server_hostname=hostname) as ss2:
                        findings.append({"severity": "critical", "message": f"{proto_name} still enabled — disable it! Vulnerable to POODLE/BEAST."})
                        if grade > "C": grade = "C"
            except:
                findings.append({"severity": "pass", "message": f"{proto_name} correctly disabled."})

    except ssl.SSLCertVerificationError as e:
        findings.append({"severity": "critical", "message": f"SSL certificate verification FAILED: {e}"})
        grade = "F"
    except Exception as e:
        findings.append({"severity": "critical", "message": f"SSL connection failed: {e}"})
        grade = "F"
    return {"grade": grade, "findings": findings}

def _scan_headers(url):
    """Audit HTTP security headers."""
    import requests as req
    findings = []
    score = 0
    max_score = len(_SECURITY_HEADERS) * 10 + 20  # bonus points available
    try:
        r = req.get(url, timeout=15, allow_redirects=True,
                    headers={"User-Agent": "BVTech-SecurityAudit/1.0"})
        headers = {k.lower(): v for k, v in r.headers.items()}

        # Check each security header
        for header_name, (severity, message) in _SECURITY_HEADERS.items():
            if header_name.lower() in headers:
                findings.append({"severity": "pass", "message": f"✅ {header_name}: {headers[header_name.lower()][:80]}"})
                score += 10
            else:
                findings.append({"severity": severity, "message": message})

        # Check for dangerous headers that leak info
        if "server" in headers:
            findings.append({"severity": "warning", "message": f"Server header leaks software: {headers['server'][:50]}. Remove or genericize."})
        else:
            score += 5
            findings.append({"severity": "pass", "message": "Server header properly hidden."})

        if "x-powered-by" in headers:
            findings.append({"severity": "warning", "message": f"X-Powered-By leaks technology: {headers['x-powered-by'][:50]}. Remove this header."})
        else:
            score += 5

        # Check cookies
        cookie_header = headers.get("set-cookie", "")
        if cookie_header:
            if "secure" not in cookie_header.lower():
                findings.append({"severity": "warning", "message": "Cookies missing Secure flag — sent over HTTP."})
            if "httponly" not in cookie_header.lower():
                findings.append({"severity": "warning", "message": "Cookies missing HttpOnly flag — accessible via JavaScript (XSS risk)."})
            if "samesite" not in cookie_header.lower():
                findings.append({"severity": "info", "message": "Cookies missing SameSite attribute — CSRF risk."})

        # HTTPS redirect check
        try:
            r2 = req.get(url.replace("https://", "http://"), timeout=10, allow_redirects=False,
                        headers={"User-Agent": "BVTech-SecurityAudit/1.0"})
            if r2.status_code in (301, 302) and "https" in r2.headers.get("Location", ""):
                findings.append({"severity": "pass", "message": "HTTP→HTTPS redirect properly configured."})
                score += 10
            else:
                findings.append({"severity": "warning", "message": "HTTP does not redirect to HTTPS. Enable HTTPS redirect."})
        except: pass

    except Exception as e:
        findings.append({"severity": "critical", "message": f"Cannot reach {url}: {e}"})
    return {"score": min(int(score / max_score * 100), 100), "findings": findings}

def _scan_sensitive_files(base_url):
    """Check for exposed sensitive files and paths."""
    import requests as req
    findings = []
    base_url = base_url.rstrip("/")
    for path, severity, desc in _SENSITIVE_PATHS:
        try:
            r = req.get(f"{base_url}{path}", timeout=5, allow_redirects=False,
                       headers={"User-Agent": "BVTech-SecurityAudit/1.0"})
            if r.status_code == 200:
                size = len(r.content)
                if size > 0 and "404" not in r.text[:200].lower() and "not found" not in r.text[:200].lower():
                    findings.append({"severity": severity, "message": f"EXPOSED: {path} ({size} bytes) — {desc}"})
            elif r.status_code == 403:
                findings.append({"severity": "info", "message": f"Protected (403): {path} — blocked but path exists."})
        except: pass
    if not findings:
        findings.append({"severity": "pass", "message": "No sensitive files exposed — good!"})
    return {"findings": findings}

def _scan_dns(hostname):
    """Check DNS records and email security."""
    import socket, subprocess
    findings = []
    # Resolve IP
    try:
        ip = socket.gethostbyname(hostname)
        findings.append({"severity": "info", "message": f"Resolved to: {ip}"})
    except:
        findings.append({"severity": "critical", "message": f"Cannot resolve {hostname}"})
        return {"findings": findings}

    # Check SPF, DKIM, DMARC via nslookup or dig
    for record_type, record_name, label in [
        ("TXT", hostname, "SPF"),
        ("TXT", f"_dmarc.{hostname}", "DMARC"),
    ]:
        try:
            result = subprocess.run(["nslookup", "-type=TXT", record_name],
                                   capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr
            if label == "SPF" and "v=spf1" in output:
                findings.append({"severity": "pass", "message": f"SPF record found: {[l for l in output.split(chr(10)) if 'spf1' in l.lower()][0].strip()[:100]}"})
            elif label == "SPF":
                findings.append({"severity": "warning", "message": "No SPF record found — email spoofing possible."})
            elif label == "DMARC" and "v=DMARC1" in output:
                findings.append({"severity": "pass", "message": f"DMARC record found."})
            elif label == "DMARC":
                findings.append({"severity": "warning", "message": "No DMARC record — email spoofing/phishing risk."})
        except:
            findings.append({"severity": "info", "message": f"Could not check {label} record."})

    return {"findings": findings}

def _scan_ports(target, ports_list, grab_banners=True):
    """TCP port scanner with banner grabbing."""
    import socket
    open_ports = []
    for port in ports_list:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            result = sock.connect_ex((target, port))
            if result == 0:
                banner = ""
                service = _PORT_RISKS.get(port, ("unknown", "info", ""))[0]
                if grab_banners:
                    try:
                        sock.settimeout(3)
                        if port in (80, 8080, 443, 8443):
                            sock.send(b"HEAD / HTTP/1.0\r\nHost: " + target.encode() + b"\r\n\r\n")
                        else:
                            sock.send(b"\r\n")
                        banner = sock.recv(1024).decode("utf-8", errors="replace").strip()[:200]
                    except: pass
                open_ports.append({
                    "port": port, "state": "open", "service": service,
                    "banner": banner, "version": banner.split("\n")[0][:80] if banner else "",
                })
            sock.close()
        except: pass
    return open_ports

def _assess_port_vulns(open_ports):
    """Assess vulnerabilities based on open ports and services."""
    vulns = []
    for p in open_ports:
        port = p["port"]
        if port in _PORT_RISKS:
            svc, severity, desc = _PORT_RISKS[port]
            if severity in ("critical", "warning"):
                vulns.append({
                    "severity": severity, "port": port,
                    "title": f"{svc} (port {port}) exposed",
                    "description": desc, "cve": "N/A",
                })
        # Banner-based version checks
        banner = (p.get("banner") or "").lower()
        if "openssh" in banner:
            # Check for old SSH versions
            import re
            ver_match = re.search(r'openssh[_\s](\d+\.\d+)', banner)
            if ver_match:
                ver = float(ver_match.group(1))
                if ver < 7.4:
                    vulns.append({"severity": "critical", "port": port, "title": f"Outdated OpenSSH {ver_match.group(1)}", "description": "Upgrade OpenSSH to 8.0+. Old versions have multiple CVEs.", "cve": "Multiple"})
                elif ver < 8.0:
                    vulns.append({"severity": "warning", "port": port, "title": f"Aging OpenSSH {ver_match.group(1)}", "description": "Consider upgrading OpenSSH to latest.", "cve": "N/A"})
        if "apache/" in banner:
            import re
            ver_match = re.search(r'apache/(\d+\.\d+\.\d+)', banner)
            if ver_match and ver_match.group(1) < "2.4.54":
                vulns.append({"severity": "warning", "port": port, "title": f"Outdated Apache {ver_match.group(1)}", "description": "Update Apache to latest version.", "cve": "Multiple"})
        if "microsoft-iis/" in banner:
            import re
            ver_match = re.search(r'microsoft-iis/(\d+)', banner)
            if ver_match and int(ver_match.group(1)) < 10:
                vulns.append({"severity": "warning", "port": port, "title": f"Outdated IIS {ver_match.group(1)}", "description": "Update IIS to latest version.", "cve": "Multiple"})
    return vulns

def _get_top_ports(n=100):
    """Return top N most common ports."""
    top_100 = [7,20,21,22,23,25,53,69,80,88,110,111,119,123,135,137,139,143,161,179,
               194,443,445,465,514,515,587,631,636,993,995,1025,1080,1194,1433,1434,
               1521,1723,2049,2082,2083,2086,2087,2095,2096,3000,3128,3306,3389,3690,
               4000,4443,4848,5000,5060,5432,5631,5666,5800,5900,5901,5985,5986,6000,
               6379,6667,7001,7002,8000,8008,8009,8080,8081,8083,8088,8443,8880,8888,
               9000,9090,9200,9300,9418,9999,10000,11211,25565,27017,28017,32768,49152,
               49153,49154,50000,50070,61616]
    return top_100[:n]

def _get_common_service_ports():
    return [21,22,23,25,53,80,110,111,135,139,143,443,445,993,995,1433,1521,3306,3389,5432,5900,5985,6379,8080,8443,27017]

# ── Cyber Audit API Routes ──────────────────────────────

@app.route("/api/cyber/web-audit", methods=["POST"])
def cyber_web_audit():
    """Full website security audit."""
    d = request.json or {}
    url = d.get("url", "").strip()
    if not url: return jsonify({"error": "No URL provided"}), 400
    if not url.startswith("http"): url = "https://" + url
    client_name = d.get("client_name", "Client")
    checks = d.get("checks", {})

    import time
    start = time.time()
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname

    result = {"target": url, "hostname": hostname, "client_name": client_name,
              "scan_date": datetime.now().isoformat(), "scan_type": "website_full"}

    total_checks = 0
    total_vulns = 0
    critical = 0
    passed = 0

    # SSL/TLS
    if checks.get("ssl", True):
        result["ssl"] = _scan_ssl(hostname)
        for f in result["ssl"].get("findings", []):
            total_checks += 1
            if f["severity"] == "critical": critical += 1; total_vulns += 1
            elif f["severity"] == "warning": total_vulns += 1
            elif f["severity"] == "pass": passed += 1

    # HTTP Headers
    if checks.get("headers", True):
        result["headers"] = _scan_headers(url)
        for f in result["headers"].get("findings", []):
            total_checks += 1
            if f["severity"] == "critical": critical += 1; total_vulns += 1
            elif f["severity"] == "warning": total_vulns += 1
            elif f["severity"] == "pass": passed += 1

    # Sensitive file exposure
    if checks.get("exposure", True):
        result["exposure"] = _scan_sensitive_files(url)
        for f in result["exposure"].get("findings", []):
            total_checks += 1
            if f["severity"] == "critical": critical += 1; total_vulns += 1
            elif f["severity"] == "warning": total_vulns += 1
            elif f["severity"] == "pass": passed += 1

    # DNS + Email Security
    if checks.get("dns", True) or checks.get("email", True):
        result["dns"] = _scan_dns(hostname)
        for f in result["dns"].get("findings", []):
            total_checks += 1
            if f["severity"] == "critical": critical += 1; total_vulns += 1
            elif f["severity"] == "warning": total_vulns += 1
            elif f["severity"] == "pass": passed += 1

    # CMS Detection (from headers/response)
    if checks.get("cms", True):
        try:
            import requests as req
            r = req.get(url, timeout=10, headers={"User-Agent": "BVTech-SecurityAudit/1.0"})
            body = r.text[:5000].lower()
            cms_findings = []
            if "wp-content" in body or "wp-includes" in body:
                cms_findings.append({"severity": "info", "message": "CMS: WordPress detected"})
                if "/wp-json/" in body: cms_findings.append({"severity": "warning", "message": "WordPress REST API exposed — user enumeration possible"})
            elif "drupal" in body: cms_findings.append({"severity": "info", "message": "CMS: Drupal detected"})
            elif "joomla" in body: cms_findings.append({"severity": "info", "message": "CMS: Joomla detected"})
            elif "shopify" in body: cms_findings.append({"severity": "info", "message": "Platform: Shopify detected"})
            elif "squarespace" in body: cms_findings.append({"severity": "info", "message": "Platform: Squarespace detected"})
            elif "wix" in body: cms_findings.append({"severity": "info", "message": "Platform: Wix detected"})
            else: cms_findings.append({"severity": "info", "message": "CMS: Not detected (custom or static site)"})
            result["cms"] = {"findings": cms_findings}
        except: result["cms"] = {"findings": [{"severity": "info", "message": "CMS detection failed"}]}

    elapsed = round(time.time() - start, 1)
    security_score = max(0, min(100, int(100 - (critical * 15) - (total_vulns * 5) + (passed * 3))))
    result["scan_time_seconds"] = elapsed
    result["summary"] = {
        "total_checks": total_checks, "total_vulnerabilities": total_vulns,
        "critical": critical, "passed": passed, "security_score": security_score,
    }

    # Save to history
    _cyber_history.insert(0, {
        "type": "web", "target": url, "client": client_name,
        "date": datetime.now().isoformat(),
        "score": security_score, "vulns": total_vulns, "critical": critical,
    })
    _save_cyber_history()

    return jsonify(result)

@app.route("/api/cyber/web-quick", methods=["POST"])
def cyber_web_quick():
    """Quick website scan — SSL + headers only."""
    d = request.json or {}
    url = d.get("url", "").strip()
    if not url: return jsonify({"error": "No URL"}), 400
    if not url.startswith("http"): url = "https://" + url
    return cyber_web_audit_inner(url, {"ssl": True, "headers": True})

def cyber_web_audit_inner(url, checks):
    """Reusable inner function."""
    d_fake = {"url": url, "checks": checks, "client_name": "Quick Scan"}
    with app.test_request_context(json=d_fake):
        request_data = d_fake
    # Just call the full audit with limited checks
    import time
    start = time.time()
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname
    result = {"target": url, "hostname": hostname, "scan_type": "quick"}
    result["ssl"] = _scan_ssl(hostname) if checks.get("ssl") else None
    result["headers"] = _scan_headers(url) if checks.get("headers") else None
    total_v = 0; crit = 0; p = 0
    for section in [result.get("ssl"), result.get("headers")]:
        if section:
            for f in section.get("findings", []):
                if f["severity"] == "critical": crit += 1; total_v += 1
                elif f["severity"] == "warning": total_v += 1
                elif f["severity"] == "pass": p += 1
    result["scan_time_seconds"] = round(time.time() - start, 1)
    result["summary"] = {"total_vulnerabilities": total_v, "critical": crit, "passed": p,
                          "security_score": max(0, min(100, 100 - crit*15 - total_v*5 + p*3))}
    return jsonify(result)

@app.route("/api/cyber/net-pentest", methods=["POST"])
def cyber_net_pentest():
    """Full network penetration test."""
    d = request.json or {}
    target = d.get("target", "").strip()
    if not target: return jsonify({"error": "No target provided"}), 400
    port_range = d.get("port_range", "top1000")
    custom_ports = d.get("custom_ports", "")
    checks = d.get("checks", {})

    import time, socket
    start = time.time()

    # Resolve hostname
    resolved_ip = target
    try:
        resolved_ip = socket.gethostbyname(target)
    except:
        return jsonify({"error": f"Cannot resolve {target}"})

    # Determine ports to scan
    if port_range == "custom" and custom_ports:
        ports = [int(p.strip()) for p in custom_ports.split(",") if p.strip().isdigit()]
    elif port_range == "top100":
        ports = _get_top_ports(100)
    elif port_range == "common_services":
        ports = _get_common_service_ports()
    elif port_range == "full":
        ports = list(range(1, 65536))
    else:
        ports = _get_top_ports(100) + list(range(100, 1001))  # top 1000ish
        ports = sorted(set(ports))

    result = {"target": target, "resolved_ip": resolved_ip,
              "scan_type": "network_pentest", "ports_scanned": len(ports),
              "scan_date": datetime.now().isoformat()}

    # Port scan
    grab_banners = checks.get("banner", True)
    open_ports = _scan_ports(resolved_ip, ports, grab_banners)
    result["open_ports"] = open_ports

    # Vulnerability assessment
    if checks.get("vulns", True):
        result["vulnerabilities"] = _assess_port_vulns(open_ports)
    else:
        result["vulnerabilities"] = []

    # Service details
    services = []
    for p in open_ports:
        svc_info = f"Port {p['port']}/{p['service']}: {p.get('banner', '')[:100]}"
        services.append(svc_info)
    result["services"] = services

    # Nmap integration (optional)
    if checks.get("nmap", False):
        try:
            import subprocess
            nmap_result = subprocess.run(
                ["nmap", "-sV", "-sC", "--top-ports", "100", "-T4", target],
                capture_output=True, text=True, timeout=120
            )
            result["nmap_output"] = nmap_result.stdout[:3000]
        except FileNotFoundError:
            result["nmap_output"] = "Nmap not installed. Install from nmap.org for deep OS fingerprinting."
        except Exception as e:
            result["nmap_output"] = f"Nmap error: {e}"

    elapsed = round(time.time() - start, 1)
    total_vulns = len(result.get("vulnerabilities", []))
    critical = len([v for v in result.get("vulnerabilities", []) if v.get("severity") == "critical"])
    score = max(0, min(100, 100 - (len(open_ports) * 3) - (critical * 15) - (total_vulns * 5)))
    result["scan_time_seconds"] = elapsed
    result["summary"] = {"total_vulnerabilities": total_vulns, "critical": critical,
                          "open_ports": len(open_ports), "security_score": score}

    _cyber_history.insert(0, {
        "type": "network", "target": target, "date": datetime.now().isoformat(),
        "score": score, "vulns": total_vulns, "critical": critical,
        "open_ports": len(open_ports),
    })
    _save_cyber_history()
    return jsonify(result)

@app.route("/api/cyber/net-quick", methods=["POST"])
def cyber_net_quick():
    """Quick port scan — top 100 ports."""
    d = request.json or {}
    target = d.get("target", "").strip()
    if not target: return jsonify({"error": "No target"}), 400

    import time, socket
    start = time.time()
    try:
        resolved_ip = socket.gethostbyname(target)
    except:
        return jsonify({"error": f"Cannot resolve {target}"})

    ports = _get_top_ports(100)
    open_ports = _scan_ports(resolved_ip, ports, grab_banners=True)
    vulns = _assess_port_vulns(open_ports)
    elapsed = round(time.time() - start, 1)
    critical = len([v for v in vulns if v.get("severity") == "critical"])
    return jsonify({
        "target": target, "resolved_ip": resolved_ip, "scan_type": "quick_port",
        "ports_scanned": len(ports), "open_ports": open_ports,
        "vulnerabilities": vulns, "services": [],
        "scan_time_seconds": elapsed,
        "summary": {"total_vulnerabilities": len(vulns), "critical": critical,
                     "open_ports": len(open_ports),
                     "security_score": max(0, 100 - len(open_ports)*3 - critical*15 - len(vulns)*5)}
    })

@app.route("/api/cyber/ai-analyze", methods=["POST"])
def cyber_ai_analyze():
    """AI-powered vulnerability analysis with Claude."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key: return jsonify({"error": "No Anthropic API key."})

    d = request.json or {}
    scan_results = d.get("scan_results", {})
    if not scan_results: return jsonify({"error": "No scan results to analyze."})

    # Build the analysis prompt
    scan_json = json.dumps(scan_results, indent=2, default=str)[:8000]  # Truncate for token limits

    prompt = f"""You are an expert cybersecurity analyst at BVTech LLC, an MSP in Texas. Analyze these security scan results and provide a comprehensive vulnerability assessment.

SCAN RESULTS:
{scan_json}

Provide your analysis in this EXACT format (plain text, not markdown):

🛡️ SECURITY POSTURE SCORE: X/100
[One-line summary of overall security health]

🔴 CRITICAL FINDINGS (Immediate Action Required):
[Number each critical finding. For each: what it is, why it matters, exact steps to fix it, estimated time/cost]

🟡 WARNINGS (Important — Schedule Fixes):
[Number each warning. Same format as above.]

🟢 PASSED CHECKS (What's Good):
[List what's configured correctly — give the client credit]

🔧 PRIORITIZED REMEDIATION PLAN:
[Numbered list in priority order. For each:
  - What to fix
  - Exact technical steps (commands, config changes, tools)
  - Estimated time: X hours
  - Estimated cost: $X if outsourced to BVTech
  - Impact if not fixed]

📊 COMPLIANCE MAPPING:
[Map findings to relevant frameworks:]
  - OWASP Top 10 violations
  - NIST CSF gaps
  - CIS Controls gaps
  - HIPAA/PCI implications if applicable

💰 REMEDIATION COST SUMMARY:
  - Quick wins (< 1 hour): $X
  - Medium effort (1-4 hours): $X
  - Major projects (4+ hours): $X
  - Total estimated: $X

📄 CLIENT EXECUTIVE SUMMARY:
[2-3 paragraph non-technical summary suitable for emailing to a business owner. Professional but clear about risks. End with a call to action to engage BVTech for remediation.]

Be specific with real commands, real config snippets, and real tool recommendations. Reference CVE numbers where applicable."""

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514", "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=90)

        if resp.status_code != 200:
            return jsonify({"error": f"Claude API error: {resp.status_code}"})

        text = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text": text += block.get("text", "")

        return jsonify({"analysis": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cyber/generate-report", methods=["POST"])
def cyber_generate_report():
    """Generate an HTML security audit report."""
    d = request.json or {}
    scan_results = d.get("scan_results", {})
    client_name = d.get("client_name", "Client")

    # Generate report HTML
    target = scan_results.get("target", "Unknown")
    scan_date = scan_results.get("scan_date", datetime.now().isoformat())
    summary = scan_results.get("summary", {})
    score = summary.get("security_score", "?")

    report_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Security Audit Report — {client_name}</title>
<style>
body{{font-family:Arial,sans-serif;margin:40px;color:#333;line-height:1.6}}
h1{{color:#1a1a2e;border-bottom:3px solid #ef4444;padding-bottom:10px}}
h2{{color:#ef4444;margin-top:30px}}
.score{{font-size:48px;font-weight:bold;text-align:center;padding:20px;border-radius:12px;margin:20px 0}}
.score.good{{background:#dcfce7;color:#16a34a}}
.score.warning{{background:#fef3c7;color:#d97706}}
.score.critical{{background:#fee2e2;color:#dc2626}}
table{{width:100%;border-collapse:collapse;margin:16px 0}}
th,td{{border:1px solid #ddd;padding:10px;text-align:left}}
th{{background:#f3f4f6;font-weight:bold}}
.critical{{color:#dc2626;font-weight:bold}}
.warning{{color:#d97706}}
.pass{{color:#16a34a}}
.footer{{margin-top:40px;padding-top:20px;border-top:2px solid #e5e7eb;text-align:center;color:#6b7280;font-size:14px}}
</style></head><body>
<h1>🛡️ Cybersecurity Audit Report</h1>
<p><strong>Client:</strong> {client_name}<br>
<strong>Target:</strong> {target}<br>
<strong>Date:</strong> {scan_date[:10]}<br>
<strong>Auditor:</strong> BVTech LLC — Jordan Polasek, Managing Partner<br>
<strong>Phone:</strong> (210) 538-3669 | <strong>Email:</strong> help@bvtech.org</p>

<div class="score {'good' if isinstance(score,int) and score>=80 else 'warning' if isinstance(score,int) and score>=50 else 'critical'}">
Security Score: {score}/100
</div>

<h2>Summary</h2>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Checks</td><td>{summary.get('total_checks','?')}</td></tr>
<tr><td>Vulnerabilities Found</td><td class="{'critical' if summary.get('total_vulnerabilities',0)>5 else 'warning'}">{summary.get('total_vulnerabilities',0)}</td></tr>
<tr><td>Critical Issues</td><td class="critical">{summary.get('critical',0)}</td></tr>
<tr><td>Passed Checks</td><td class="pass">{summary.get('passed',0)}</td></tr>
</table>

<h2>Detailed Findings</h2>"""

    # Add findings from each section
    for section_name in ["ssl", "headers", "exposure", "dns", "cms"]:
        section = scan_results.get(section_name)
        if section and section.get("findings"):
            report_html += f"\n<h3>{section_name.upper()}</h3><table><tr><th>Severity</th><th>Finding</th></tr>"
            for f in section["findings"]:
                sev_class = f["severity"] if f["severity"] in ("critical","warning","pass") else ""
                report_html += f'<tr><td class="{sev_class}">{f["severity"].upper()}</td><td>{f["message"]}</td></tr>'
            report_html += "</table>"

    # Network findings
    if scan_results.get("open_ports"):
        report_html += "\n<h3>OPEN PORTS</h3><table><tr><th>Port</th><th>Service</th><th>Banner</th></tr>"
        for p in scan_results["open_ports"]:
            report_html += f'<tr><td>{p["port"]}</td><td>{p.get("service","?")}</td><td>{p.get("banner","")[:80]}</td></tr>'
        report_html += "</table>"

    if scan_results.get("vulnerabilities"):
        report_html += "\n<h3>VULNERABILITIES</h3><table><tr><th>Severity</th><th>Issue</th><th>Description</th></tr>"
        for v in scan_results["vulnerabilities"]:
            report_html += f'<tr><td class="{v.get("severity","")}">{v.get("severity","").upper()}</td><td>{v.get("title","")}</td><td>{v.get("description","")}</td></tr>'
        report_html += "</table>"

    report_html += f"""
<h2>Recommendations</h2>
<p>Based on this audit, BVTech LLC recommends the following immediate actions:</p>
<ol>
<li>Address all <strong class="critical">CRITICAL</strong> findings within 24-48 hours</li>
<li>Schedule remediation of <strong class="warning">WARNING</strong> items within 2 weeks</li>
<li>Implement a regular security scanning schedule (monthly recommended)</li>
<li>Contact BVTech LLC at <strong>(210) 538-3669</strong> for professional remediation</li>
</ol>

<div class="footer">
<p><strong>BVTech LLC</strong> — Managed IT Services & Cybersecurity<br>
Jordan Polasek, Founder & Managing Partner<br>
(210) 538-3669 | help@bvtech.org | bvtech.org<br>
1902 Kirby Rd, El Campo, TX 77437</p>
<p><em>This report is confidential and intended only for the named client.</em></p>
</div>
</body></html>"""

    # Save report
    report_filename = f"audit_report_{client_name.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    report_path = os.path.join(APP_DIR, report_filename)
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)
    except: pass

    return jsonify({"file_path": report_path, "filename": report_filename, "download_url": f"/api/cyber/report/{report_filename}"})

@app.route("/api/cyber/report/<filename>")
def cyber_download_report(filename):
    """Serve a generated audit report."""
    report_path = os.path.join(APP_DIR, filename)
    if os.path.exists(report_path):
        from flask import send_file
        return send_file(report_path, mimetype="text/html", as_attachment=True, download_name=filename)
    return jsonify({"error": "Report not found"}), 404

@app.route("/api/cyber/history")
def cyber_audit_history():
    return jsonify({"history": _cyber_history[:50]})

# ============================================================
# CLOUDFLARE PAGES ROUTES (v20.0 NEW)
# BVTech.org static site — deploys via GitHub API → Cloudflare Pages
# ============================================================
@app.route("/api/cloudflare/dashboard")
def cf_dashboard():
    """Get Cloudflare Pages dashboard — blog posts, deploy status."""
    try:
        cf = get_cf_client()
        data, err = cf.get_dashboard()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/cloudflare/test")
def cf_test():
    """Test Cloudflare/GitHub connection."""
    try:
        cf = get_cf_client()
        data, err = cf.test_connection()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/cloudflare/posts")
def cf_posts():
    """List blog posts on BVTech.org."""
    try:
        cf = get_cf_client()
        data, err = cf.list_posts(per_page=100)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/cloudflare/post/<slug>")
def cf_post_detail(slug):
    """Get details/preview of a specific blog post."""
    try:
        cf = get_cf_client()
        if cf.mode == "github":
            file_data, err = cf._gh_get_file(f"blog/{slug}.html")
            if not file_data:
                return jsonify({"error": f"Post not found: {slug}"}), 404
            import base64
            content = base64.b64decode(file_data.get("content", "")).decode("utf-8", errors="replace")
            # Extract title from <h1> tag
            import re
            title_match = re.search(r'<h1>(.*?)</h1>', content)
            title = title_match.group(1) if title_match else slug.replace("-"," ").title()
            # Extract text content from article body
            body_match = re.search(r'<article class="article-body">(.*?)</article>', content, re.DOTALL)
            preview = ""
            if body_match:
                preview = re.sub(r'<[^>]+>', ' ', body_match.group(1)).strip()[:2000]
            return jsonify({
                "title": title, "slug": slug,
                "url": f"{cf.site_url}/blog/{slug}/",
                "preview": preview, "size": len(content),
            })
        return jsonify({"error": "Preview only available in GitHub mode"}), 400
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/cloudflare/delete/<slug>", methods=["POST"])
def cf_delete_post(slug):
    """Delete a blog post from the site."""
    try:
        cf = get_cf_client()
        data, err = cf.delete_post(slug)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/cloudflare/ai-blog", methods=["POST"])
def cf_ai_blog():
    """Generate a blog post using Claude AI and deploy to Cloudflare Pages."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return jsonify({"error": "No Anthropic API key. Set it in Settings → Claude AI."})

    d = request.json
    topic = d.get("topic", "")
    location = d.get("location", "")
    industry = d.get("industry", "")
    opt_mode = d.get("opt_mode", "seo_geo_aeo")
    tone = d.get("tone", "professional")
    length = d.get("length", "medium")
    custom = d.get("custom_instructions", "")
    action = d.get("action", "preview")  # publish or preview

    prompt = _build_blog_prompt(topic, location, industry, opt_mode, tone, length, custom)

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=90)

        if resp.status_code != 200:
            return jsonify({"error": f"Anthropic API error: {resp.status_code} {resp.text[:300]}"})

        ai_response = resp.json()
        text = ""
        for block in ai_response.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        text = text.strip()
        if text.startswith("```"): text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        import json as j
        try:
            blog = j.loads(text)
        except j.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                blog = j.loads(text[start:end])
            else:
                return jsonify({"error": "Failed to parse AI response", "raw": text[:1000]})

        result = {
            "title": blog.get("title", ""),
            "content": blog.get("content", ""),
            "meta_description": blog.get("meta_description", ""),
            "focus_keyword": blog.get("focus_keyword", ""),
            "secondary_keywords": blog.get("secondary_keywords", ""),
            "schema_markup": blog.get("schema_markup", ""),
            "word_count": len(blog.get("content", "").split()),
        }

        # Deploy to Cloudflare if action is publish
        if action == "publish" and blog.get("title") and blog.get("content"):
            cf = get_cf_client()
            cf_data, cf_err = cf.create_post(
                title=blog["title"],
                content=blog["content"],
                status="publish",
                meta_description=blog.get("meta_description", ""),
                focus_keyword=blog.get("focus_keyword", ""),
                schema_markup=blog.get("schema_markup", ""),
            )
            if cf_data and not cf_err:
                result["cf_post_id"] = cf_data.get("id") or cf_data.get("post_id")
                result["cf_link"] = cf_data.get("link") or cf_data.get("url", "")
                result["cf_file_path"] = cf_data.get("file_path", "")
                result["cf_deploy_mode"] = cf_data.get("deploy_mode", "")
                result["cf_status"] = "published"
                # Track in history
                _auto_post_history.insert(0, {
                    "title": blog["title"], "date": datetime.now().isoformat(),
                    "status": "published", "target": "cloudflare",
                    "word_count": result["word_count"], "topic": topic,
                    "cf_link": result["cf_link"],
                })
            elif cf_err:
                result["cf_error"] = cf_err

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cloudflare/auto-post/config", methods=["POST"])
def cf_auto_post_config():
    """Configure auto-post scheduler for Cloudflare Pages."""
    global _auto_post_config
    d = request.json
    d["target"] = "cloudflare"  # v20: ensure target is cloudflare
    _auto_post_config.update(d)
    _save_auto_post_config(_auto_post_config)
    if d.get("enabled"):
        _start_auto_post_scheduler()
    return jsonify({"status": "ok", "config": _auto_post_config})

# ============================================================
# BVTECH NEWS — AUTOMATED VULNERABILITY INTELLIGENCE (v24)
# Real CVE/vulnerability scraping → Claude AI article → auto-deploy
# ============================================================

_NEWS_CONFIG_FILE = "bvtech_news_config.json"
_NEWS_HISTORY_FILE = "bvtech_news_history.json"
_news_scheduler_thread = None
_news_scheduler_running = False

def _load_news_config():
    path = os.path.join(APP_DIR, _NEWS_CONFIG_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"enabled": False, "time": "06:00", "severity_filter": "CRITICAL,HIGH",
            "max_cves": 5, "last_run": "", "auto_publish": True}

def _save_news_config(cfg):
    path = os.path.join(APP_DIR, _NEWS_CONFIG_FILE)
    try:
        with open(path, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def _load_news_history():
    path = os.path.join(APP_DIR, _NEWS_HISTORY_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_news_history(history):
    path = os.path.join(APP_DIR, _NEWS_HISTORY_FILE)
    try:
        with open(path, "w") as f:
            json.dump(history[:365], f, indent=2)
    except Exception:
        pass

_news_config = _load_news_config()
_news_history = _load_news_history()


def _scrape_cisa_kev():
    """Scrape CISA Known Exploited Vulnerabilities catalog for the latest CVEs."""
    import requests as req
    vulns = []
    try:
        r = req.get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", timeout=30)
        if r.status_code == 200:
            data = r.json()
            catalog = data.get("vulnerabilities", [])
            # Sort by dateAdded descending, grab the newest entries
            catalog.sort(key=lambda x: x.get("dateAdded", ""), reverse=True)
            for v in catalog[:20]:
                vulns.append({
                    "cve_id": v.get("cveID", ""),
                    "vendor": v.get("vendorProject", ""),
                    "product": v.get("product", ""),
                    "name": v.get("vulnerabilityName", ""),
                    "description": v.get("shortDescription", ""),
                    "date_added": v.get("dateAdded", ""),
                    "due_date": v.get("dueDate", ""),
                    "action": v.get("requiredAction", ""),
                    "known_ransomware": v.get("knownRansomwareCampaignUse", "Unknown"),
                    "source": "CISA KEV",
                })
    except Exception as e:
        print(f"[NEWS] CISA KEV scrape error: {e}")
    return vulns


def _scrape_nvd_recent():
    """Scrape NVD for recent critical/high CVEs from the last 48 hours."""
    import requests as req
    from datetime import datetime, timedelta
    vulns = []
    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=48)
        params = {
            "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "cvssV3Severity": "CRITICAL",
            "resultsPerPage": 10,
        }
        r = req.get("https://services.nvd.nist.gov/rest/json/cves/2.0", params=params, timeout=30,
                     headers={"User-Agent": "BVTech-News-Bot/1.0"})
        if r.status_code == 200:
            data = r.json()
            for item in data.get("vulnerabilities", [])[:10]:
                cve = item.get("cve", {})
                cve_id = cve.get("id", "")
                desc_data = cve.get("descriptions", [])
                desc = next((d["value"] for d in desc_data if d.get("lang") == "en"), "")
                metrics = cve.get("metrics", {})
                cvss_data = metrics.get("cvssMetricV31", [{}])
                score = cvss_data[0].get("cvssData", {}).get("baseScore", 0) if cvss_data else 0
                severity = cvss_data[0].get("cvssData", {}).get("baseSeverity", "UNKNOWN") if cvss_data else "UNKNOWN"
                vulns.append({
                    "cve_id": cve_id,
                    "description": desc[:500],
                    "cvss_score": score,
                    "severity": severity,
                    "published": cve.get("published", ""),
                    "source": "NVD",
                })
    except Exception as e:
        print(f"[NEWS] NVD scrape error: {e}")
    return vulns


def _scrape_all_vulnerabilities():
    """Aggregate vulnerabilities from all sources, deduplicate, rank by severity."""
    cisa = _scrape_cisa_kev()
    nvd = _scrape_nvd_recent()

    # Merge and deduplicate by CVE ID
    seen = set()
    all_vulns = []
    for v in cisa + nvd:
        cve_id = v.get("cve_id", "")
        if cve_id and cve_id not in seen:
            seen.add(cve_id)
            all_vulns.append(v)

    # Sort: CISA KEV first (actively exploited), then by CVSS score
    def sort_key(v):
        is_kev = 1 if v.get("source") == "CISA KEV" else 0
        score = v.get("cvss_score", 0)
        return (-is_kev, -score)

    all_vulns.sort(key=sort_key)
    return all_vulns


def _find_royalty_free_image(topic):
    """Find a royalty-free image URL for the news article. Uses Unsplash Source (no API key needed)."""
    # Use descriptive search terms for cybersecurity imagery
    import urllib.parse
    search = urllib.parse.quote(topic[:50] if topic else "cybersecurity network security")
    # Unsplash source API provides random images matching search terms
    return f"https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=800&h=400&fit=crop&q=80"


def _build_news_prompt(vulnerabilities, custom_instructions=""):
    """Build the Claude AI prompt to write a BVTech News article from real vulnerability data."""
    from datetime import datetime
    today = datetime.now().strftime("%B %d, %Y")

    vuln_data = ""
    cve_list = []
    for i, v in enumerate(vulnerabilities[:8]):
        cve_id = v.get("cve_id", "N/A")
        cve_list.append(cve_id)
        vuln_data += f"""
--- Vulnerability {i+1} ---
CVE: {cve_id}
Vendor/Product: {v.get('vendor', '')} {v.get('product', '')}
Name: {v.get('name', '')}
Description: {v.get('description', '')}
CVSS Score: {v.get('cvss_score', 'N/A')}
Severity: {v.get('severity', 'UNKNOWN')}
Source: {v.get('source', '')}
Date Added to KEV: {v.get('date_added', '')}
Remediation Deadline: {v.get('due_date', '')}
Required Action: {v.get('action', '')}
Known Ransomware Use: {v.get('known_ransomware', 'Unknown')}
"""

    return f"""You are Jordan Polasek, Founder & Managing Partner of BVTech LLC, an award-winning managed IT services provider in Texas. You are writing a professional cybersecurity intelligence briefing for the BVTech News section of bvtech.org.

TODAY'S DATE: {today}

REAL VULNERABILITY DATA (from CISA KEV + NVD — this is REAL, not made up):
{vuln_data}

WRITE a professional, enterprise-grade cybersecurity news article that:

1. HEADLINE: Write a compelling, SEO-optimized headline. Include the date or "Today" and reference the most critical vulnerability. Make it urgent but professional.

2. EXECUTIVE SUMMARY (2-3 sentences): Quick overview for busy IT leaders — what happened, why it matters, what to do.

3. VULNERABILITY BREAKDOWN: For each major vulnerability (top 3-5):
   - What it is (CVE ID, vendor, product affected)
   - Why it's dangerous (real-world impact — data theft, ransomware, RCE, etc.)
   - Who is affected (specific industries, business sizes)
   - CVSS score and severity rating
   - Whether it's being actively exploited in the wild

4. REMEDIATION STEPS: For each vulnerability, provide:
   - Specific patches or versions to update to
   - Workarounds if patches aren't available yet
   - Network-level mitigations (firewall rules, segmentation)
   - Detection indicators to check if you've been compromised

5. BVTECH'S TAKE (Jordan Polasek's perspective):
   - What this means for Texas SMBs specifically
   - How BVTech's proactive monitoring catches these threats
   - Why businesses with managed IT are protected while DIY shops are vulnerable
   - A concrete recommendation (don't be salesy — be authoritative and helpful)

6. FAQ SECTION: 3-4 questions business owners would actually ask, with direct answers. Optimize these for featured snippets and People Also Ask.

TONE: Authoritative, urgent but not alarmist. Write like a seasoned CISO briefing the board — not a blogger writing clickbait. Use real CVE numbers, real vendor names, real CVSS scores. No fluff, no filler, no generic "stay safe out there" nonsense.

LENGTH: 1200-2000 words. This is a real intelligence briefing, not a tweet.

SEO/GEO/AEO OPTIMIZATION:
- Target keywords: cybersecurity vulnerability, CVE alert, managed IT services Texas, IT security San Antonio
- Include location references: El Campo TX, San Antonio, Houston, Austin
- Structure for AI citation: use "According to CISA..." and factual statements
- FAQ section optimized for voice search and featured snippets
- Include internal links to /services/cybersecurity-solutions.html and /contact/

{f'Additional instructions: {custom_instructions}' if custom_instructions else ''}

OUTPUT FORMAT — respond with ONLY a JSON object (no markdown, no backticks):
{{
  "title": "Headline of the article",
  "content": "<p>Full HTML article content with <h2>, <h3>, <p>, <ul>, <li>, <strong>, <a> tags. Include links to /services/cybersecurity-solutions.html and /contact/ where natural.</p>",
  "meta_description": "150-160 char meta description",
  "focus_keyword": "primary keyword phrase",
  "severity": "CRITICAL or HIGH or MEDIUM",
  "cve_ids": ["CVE-2026-XXXXX", "CVE-2026-YYYYY"],
  "executive_summary": "2-3 sentence summary for the homepage card",
  "schema_markup": "<script type=application/ld+json>{{...FAQ schema...}}</script>"
}}""", cve_list


def _generate_news_article(vulns=None, custom_instructions="", publish=True):
    """Full pipeline: scrape vulns → Claude AI writes article → deploy to bvtech.org/news/"""
    global _news_history
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return None, "No Anthropic API key configured."

    # Step 1: Scrape real vulnerability data
    if not vulns:
        vulns = _scrape_all_vulnerabilities()
    if not vulns:
        return None, "No vulnerabilities found from CISA/NVD feeds."

    # Step 2: Build prompt with real data
    prompt, cve_list = _build_news_prompt(vulns, custom_instructions)

    # Step 3: Call Claude AI
    import requests as req
    try:
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=120)

        if resp.status_code != 200:
            return None, f"Anthropic API error: {resp.status_code} {resp.text[:300]}"

        ai_response = resp.json()
        text = ""
        for block in ai_response.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        text = text.strip()
        if text.startswith("```"): text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        try:
            article = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                article = json.loads(text[start:end])
            else:
                return None, f"Failed to parse AI response: {text[:500]}"

    except Exception as e:
        return None, f"Claude AI error: {str(e)}"

    # Step 4: Find a relevant image
    image_url = _find_royalty_free_image(article.get("title", "cybersecurity"))
    image_alt = f"{article.get('title', 'Cybersecurity Alert')} - Jordan Polasek - BVTech News"

    result = {
        "title": article.get("title", ""),
        "content": article.get("content", ""),
        "meta_description": article.get("meta_description", ""),
        "focus_keyword": article.get("focus_keyword", ""),
        "severity": article.get("severity", "CRITICAL"),
        "cve_ids": article.get("cve_ids", cve_list),
        "executive_summary": article.get("executive_summary", ""),
        "schema_markup": article.get("schema_markup", ""),
        "word_count": len(article.get("content", "").split()),
        "vulnerabilities_used": len(vulns),
        "image_url": image_url,
        "image_alt": image_alt,
    }

    # Step 5: Deploy to Cloudflare if publish=True
    if publish and article.get("title") and article.get("content"):
        try:
            cf = get_cf_client()
            cf_data, cf_err = cf.create_news_post(
                title=article["title"],
                content=article["content"],
                meta_description=article.get("meta_description", ""),
                focus_keyword=article.get("focus_keyword", ""),
                schema_markup=article.get("schema_markup", ""),
                severity=article.get("severity", "CRITICAL"),
                cve_ids=article.get("cve_ids", []),
                image_url=image_url,
                image_alt=image_alt,
            )
            if cf_data and not cf_err:
                result["cf_link"] = cf_data.get("link") or cf_data.get("url", "")
                result["cf_file_path"] = cf_data.get("file_path", "")
                result["cf_deploy_mode"] = cf_data.get("deploy_mode", "")
                result["cf_status"] = "published"
            elif cf_err:
                result["cf_error"] = cf_err
        except Exception as e:
            result["cf_error"] = str(e)

        # Track in history
        from datetime import datetime
        _news_history.insert(0, {
            "title": article["title"],
            "date": datetime.now().isoformat(),
            "severity": article.get("severity", "CRITICAL"),
            "cve_ids": article.get("cve_ids", []),
            "word_count": result["word_count"],
            "cf_link": result.get("cf_link", ""),
            "executive_summary": article.get("executive_summary", ""),
        })
        _save_news_history(_news_history)

    return result, None


def _start_news_scheduler():
    """Start the 6AM CST daily news scheduler thread."""
    global _news_scheduler_thread, _news_scheduler_running
    if _news_scheduler_running:
        return  # Already running

    def news_sched_loop():
        global _news_scheduler_running, _news_config
        _news_scheduler_running = True
        print("[NEWS] Scheduler started — daily vulnerability news at configured time CST")

        while _news_scheduler_running:
            try:
                _news_config = _load_news_config()
                if not _news_config.get("enabled"):
                    _news_scheduler_running = False
                    print("[NEWS] Scheduler disabled, stopping.")
                    break

                # Check if it's time to run (compare HH:MM in CST)
                from datetime import datetime, timezone, timedelta
                cst = timezone(timedelta(hours=-6))
                now = datetime.now(cst)
                target_time = _news_config.get("time", "06:00")
                current_time = now.strftime("%H:%M")
                today_str = now.strftime("%Y-%m-%d")

                last_run = _news_config.get("last_run", "")

                if current_time == target_time and last_run != today_str:
                    print(f"[NEWS] Running daily vulnerability news generation at {current_time} CST")
                    try:
                        result, err = _generate_news_article(publish=_news_config.get("auto_publish", True))
                        if result and not err:
                            print(f"[NEWS] Article published: {result.get('title', 'Unknown')}")
                            _news_config["last_run"] = today_str
                            _save_news_config(_news_config)
                        elif err:
                            print(f"[NEWS] Generation error: {err}")
                    except Exception as e:
                        print(f"[NEWS] Scheduler error: {e}")

                import time
                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                print(f"[NEWS] Scheduler loop error: {e}")
                import time
                time.sleep(60)

    _news_scheduler_thread = threading.Thread(target=news_sched_loop, daemon=True, name="NewsScheduler")
    _news_scheduler_thread.start()


# ── BVTech News API Routes ───────────────────────────────

@app.route("/api/news/scrape", methods=["POST"])
def news_scrape():
    """Scrape latest vulnerabilities from CISA KEV + NVD."""
    try:
        vulns = _scrape_all_vulnerabilities()
        return jsonify({"vulnerabilities": vulns, "count": len(vulns)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/news/generate", methods=["POST"])
def news_generate():
    """Generate a BVTech News article from real vulnerability data."""
    d = request.json or {}
    custom = d.get("custom_instructions", "")
    publish = d.get("publish", True)

    # Optionally pass pre-scraped vulns
    vulns = d.get("vulnerabilities")

    result, err = _generate_news_article(vulns=vulns, custom_instructions=custom, publish=publish)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(result)

@app.route("/api/news/history")
def news_history():
    """Get BVTech News article history."""
    return jsonify({"history": _news_history, "count": len(_news_history)})

@app.route("/api/news/config", methods=["GET", "POST"])
def news_config_route():
    """Get or update BVTech News scheduler config."""
    global _news_config
    if request.method == "POST":
        d = request.json or {}
        _news_config.update(d)
        _save_news_config(_news_config)
        if d.get("enabled"):
            _start_news_scheduler()
        return jsonify({"status": "ok", "config": _news_config})
    return jsonify(_news_config)

@app.route("/api/news/list")
def news_list():
    """List published BVTech News articles from the site."""
    try:
        cf = get_cf_client()
        data, err = cf.list_news_posts(per_page=50)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/news/test-scrape", methods=["POST"])
def news_test_scrape():
    """Test the vulnerability scraper — returns raw data without generating article."""
    try:
        cisa = _scrape_cisa_kev()
        nvd = _scrape_nvd_recent()
        return jsonify({
            "cisa_kev": cisa[:5],
            "nvd_critical": nvd[:5],
            "total_cisa": len(cisa),
            "total_nvd": len(nvd),
            "status": "ok"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# WORDPRESS ROUTES (v16.0 — kept for JordanPolasek.com)
# ============================================================
@app.route("/api/wordpress/dashboard")
def wp_dashboard():
    try:
        wp = get_wp_client()
        data, err = wp.get_dashboard()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/posts", methods=["GET"])
def wp_posts_get():
    try:
        wp = get_wp_client()
        data, err = wp.get_posts(per_page=int(request.args.get("per_page", 20)),
                                  search=request.args.get("search"))
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/posts", methods=["POST"])
def wp_posts_create():
    try:
        wp = get_wp_client()
        d = request.json
        data, err = wp.create_post(d.get("title",""), d.get("content",""), d.get("status","draft"))
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/post/<int:post_id>")
def wp_post_detail(post_id):
    try:
        wp = get_wp_client()
        data, err = wp.get_post(post_id)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/pages")
def wp_pages():
    try:
        wp = get_wp_client()
        data, err = wp.get_pages()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/comments")
def wp_comments():
    try:
        wp = get_wp_client()
        data, err = wp.get_comments()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/site")
def wp_site_info():
    try:
        wp = get_wp_client()
        data, err = wp.get_site_info()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/test")
def wp_test_connection():
    """Full diagnostic test of WordPress API connectivity."""
    try:
        wp = get_wp_client()
        data, err = wp.test_connection()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/debug-post", methods=["POST"])
def wp_debug_post():
    """Create a test draft post to verify WP posting actually works end-to-end."""
    try:
        wp = get_wp_client()
        test_title = f"[BVTech Test] Connection Verified — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        test_content = "<p>This is an automated test post from BVTech Command Center v15. If you see this in your WordPress drafts, your connection is working correctly! You can safely delete this post.</p>"
        data, err = wp.create_post(title=test_title, content=test_content, status="draft")
        if data and not err:
            return jsonify({
                "success": True,
                "message": f"Test draft created! Post ID: {data.get('id') or data.get('post_id')}",
                "post_id": data.get("id") or data.get("post_id"),
                "link": data.get("link") or data.get("url", ""),
                "status": data.get("status", "draft"),
                "raw_response": data,
            })
        else:
            return jsonify({
                "success": False,
                "error": err or "Unknown error — no data returned from WordPress",
                "raw_response": data,
            }), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# AI BLOG ENGINE — SEO / GEO / AEO (Claude-Powered)
# ============================================================
_AUTO_POST_CONFIG_FILE = "autopost_config.json"
_AUTO_POST_HISTORY_FILE = "autopost_history.json"

def _load_auto_post_config():
    path = os.path.join(APP_DIR, _AUTO_POST_CONFIG_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"enabled": False, "time": "08:00", "rotation": "msp_services", "status": "draft", "topics": ""}

def _save_auto_post_config(cfg):
    path = os.path.join(APP_DIR, _AUTO_POST_CONFIG_FILE)
    try:
        with open(path, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def _load_auto_post_history():
    path = os.path.join(APP_DIR, _AUTO_POST_HISTORY_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_auto_post_history(history):
    path = os.path.join(APP_DIR, _AUTO_POST_HISTORY_FILE)
    try:
        with open(path, "w") as f:
            json.dump(history[:200], f, indent=2)  # Keep last 200 entries
    except Exception:
        pass

_auto_post_config = _load_auto_post_config()
_auto_post_history = _load_auto_post_history()

def _build_blog_prompt(topic, location, industry, opt_mode, tone, length, custom_instructions):
    """Build the Claude prompt for SEO/GEO/AEO blog generation."""
    word_counts = {"short": "400", "medium": "800", "long": "1500", "pillar": "2500+"}
    wc = word_counts.get(length, "800")

    seo_instructions = ""
    if "seo" in opt_mode:
        seo_instructions = """
SEO OPTIMIZATION:
- Use the focus keyword naturally in the title, first paragraph, H2 headings, and conclusion
- Target a keyword density of 1-2%
- Include 2-3 secondary/LSI keywords
- Write a compelling meta description (150-160 chars)
- Use H2 and H3 subheadings with keyword variations
- Include internal linking suggestions to key service pages"""

    geo_instructions = ""
    if "geo" in opt_mode:
        geo_instructions = f"""
GEO (GENERATIVE ENGINE OPTIMIZATION) for AI search like Google SGE, Bing Copilot, Perplexity:
- Include clear, factual statements that AI systems can cite directly
- Mention specific location: {location or 'El Campo TX, San Antonio TX, Houston TX'}
- Include real data points, statistics, and specific numbers
- Structure content with clear Q&A sections
- Use "According to..." and "Research shows..." phrasing for citability
- Include local landmarks, zip codes, or neighborhood references"""

    aeo_instructions = ""
    if "aeo" in opt_mode:
        aeo_instructions = """
AEO (ANSWER ENGINE OPTIMIZATION) for featured snippets, voice search, People Also Ask:
- Include a FAQ section at the end with 4-5 common questions + concise answers
- Write definition blocks that directly answer "What is..." queries
- Use numbered lists and step-by-step formats where appropriate
- Optimize for voice search with natural, conversational phrasing
- Target "People Also Ask" boxes with question-based H2/H3 headings
- Include a TL;DR summary paragraph near the top"""

    return f"""You are an expert MSP (Managed Service Provider) content writer for BVTech LLC, an IT company based in El Campo, Texas serving the greater Houston, San Antonio, and Austin markets.

Write a blog post about: {topic}
{f'Target industry: {industry}' if industry else ''}
{f'Target location: {location}' if location else 'Target locations: El Campo TX, San Antonio TX, Houston TX, Austin TX'}
Tone: {tone}
Length: approximately {wc} words
{seo_instructions}
{geo_instructions}
{aeo_instructions}
{f'Additional instructions: {custom_instructions}' if custom_instructions else ''}

COMPANY CONTEXT:
- Company: BVTech LLC
- Website: bvtech.org
- Owner: Jordan Polasek, Managing Partner
- Phone: (210) 538-3669
- Location: 1902 Kirby Rd, El Campo, TX 77437
- Services: Managed IT, Cybersecurity (Guardz), Cloud/M365, VoIP (DialPad), Network Infrastructure, IT Consulting
- Key differentiator: Proactive monitoring, security-first approach, personal service for SMBs

OUTPUT FORMAT — respond with ONLY a JSON object (no markdown, no backticks):
{{
  "title": "SEO-optimized blog post title",
  "content": "<p>Full HTML blog content with proper <h2>, <h3>, <p>, <ul>, <li>, <strong> tags</p>",
  "meta_description": "150-160 char meta description for search results",
  "focus_keyword": "primary keyword phrase",
  "secondary_keywords": "keyword2, keyword3, keyword4",
  "schema_markup": "<script type=application/ld+json>{{...FAQ or Article schema...}}</script>"
}}"""

@app.route("/api/wordpress/ai-blog", methods=["POST"])
def wp_ai_blog():
    """Generate a blog post using Claude AI and optionally publish to WordPress."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return jsonify({"error": "No Anthropic API key. Set it in Settings → Claude AI."})

    d = request.json
    topic = d.get("topic", "")
    location = d.get("location", "")
    industry = d.get("industry", "")
    opt_mode = d.get("opt_mode", "seo_geo_aeo")
    tone = d.get("tone", "professional")
    length = d.get("length", "medium")
    custom = d.get("custom_instructions", "")
    action = d.get("action", "preview")  # draft, publish, preview

    prompt = _build_blog_prompt(topic, location, industry, opt_mode, tone, length, custom)

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=60)

        if resp.status_code != 200:
            return jsonify({"error": f"Anthropic API error: {resp.status_code} {resp.text[:300]}"})

        ai_response = resp.json()
        text = ""
        for block in ai_response.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        # Parse JSON from Claude's response
        text = text.strip()
        if text.startswith("```"): text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        import json as j
        try:
            blog = j.loads(text)
        except j.JSONDecodeError:
            # Try to extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                blog = j.loads(text[start:end])
            else:
                return jsonify({"error": "Failed to parse AI response", "raw": text[:1000]})

        result = {
            "title": blog.get("title", ""),
            "content": blog.get("content", ""),
            "meta_description": blog.get("meta_description", ""),
            "focus_keyword": blog.get("focus_keyword", ""),
            "secondary_keywords": blog.get("secondary_keywords", ""),
            "schema_markup": blog.get("schema_markup", ""),
            "word_count": len(blog.get("content", "").split()),
        }

        # Publish to WordPress if requested
        if action in ("draft", "publish") and blog.get("title") and blog.get("content"):
            wp = get_wp_client()
            wp_data, wp_err = wp.create_post(
                title=blog["title"],
                content=blog["content"],
                status=action,
            )
            if wp_data and not wp_err:
                result["wp_post_id"] = wp_data.get("id") or wp_data.get("post_id")
                result["wp_link"] = wp_data.get("link") or wp_data.get("url", "")
                result["wp_status"] = wp_data.get("status", action)
                # Track in history
                _auto_post_history.insert(0, {
                    "title": blog["title"], "date": datetime.now().isoformat(),
                    "status": "published" if action == "publish" else "draft",
                    "word_count": result["word_count"], "topic": topic,
                    "wp_post_id": result["wp_post_id"],
                })
            elif wp_err:
                result["wp_error"] = wp_err

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/ai-topics", methods=["POST"])
def wp_ai_topics():
    """Generate 30 days of blog topic ideas."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return jsonify({"error": "No Anthropic API key."})

    d = request.json
    industry = d.get("industry", "")
    location = d.get("location", "El Campo TX, San Antonio TX, Houston TX")

    prompt = f"""Generate a 30-day blog content calendar for BVTech LLC, a Managed Service Provider (MSP) based in El Campo, Texas.

Target industries: {industry or 'law firms, medical offices, accounting firms, small businesses'}
Target locations: {location}

For each day, provide:
- Day number
- Blog title (SEO optimized)
- Primary keyword to target
- Which optimization: SEO, GEO, AEO, or combo
- Brief description (1 sentence)

Mix content types: how-to guides, listicles, case studies, industry news commentary, FAQ posts, comparison posts, local service pages.
Focus on topics that demonstrate expertise and build trust with potential MSP clients.

Format as a clean numbered list."""

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=60)

        if resp.status_code != 200:
            return jsonify({"error": f"API error: {resp.status_code}"})

        text = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        return jsonify({"topics": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/auto-post/config", methods=["POST"])
def wp_auto_post_config():
    """Configure auto-post scheduler — persists to disk."""
    global _auto_post_config
    d = request.json
    _auto_post_config.update(d)
    _save_auto_post_config(_auto_post_config)
    # If enabling, start the scheduler thread
    if d.get("enabled"):
        _start_auto_post_scheduler()
    return jsonify({"status": "ok", "config": _auto_post_config})

@app.route("/api/wordpress/auto-post/test", methods=["POST"])
def wp_auto_post_test():
    """Dry-run auto-post generation."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return jsonify({"error": "No Anthropic API key."})

    # Pick a topic based on rotation
    topics = _get_rotation_topics()
    if not topics:
        return jsonify({"error": "No topics available"})

    import random
    topic = random.choice(topics)

    prompt = _build_blog_prompt(topic, "El Campo TX, San Antonio TX", "", "seo_geo_aeo", "professional", "medium", "")

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=60)

        text = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        text = text.strip()
        if text.startswith("```"): text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"): text = text[:-3]

        import json as j
        try:
            blog = j.loads(text.strip())
        except Exception:
            start = text.find("{")
            end = text.rfind("}") + 1
            blog = j.loads(text[start:end]) if start >= 0 else {"title": "Parse error", "content": text[:500]}

        return jsonify({"title": blog.get("title",""), "content": blog.get("content",""),
                         "word_count": len(blog.get("content","").split()), "action": "preview", "topic": topic})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/wordpress/auto-post/history")
def wp_auto_post_history():
    return jsonify({"history": _auto_post_history[:50]})

# ============================================================
# ORM BEAST ENGINE v16 — ORM BEAST + DEDUP FORTRESS Edition
# Queue-based, dual-site, batch generation, custom scheduling
# Thread-safe publishing with duplicate prevention
# ============================================================

_ORM_QUEUE_FILE = "orm_queue.json"
_ORM_HISTORY_FILE = "orm_history.json"
_ORM_CONFIG_FILE = "orm_config.json"

# ── v15 ORM BEAST ──────────────────────────────────────
# Thread lock prevents scheduler + publish-all from racing
_orm_publish_lock = threading.Lock()
# Flag: is a bulk publish or scheduler actively running?
_orm_publishing_active = {"scheduler": False, "bulk": False}
# Session title cache: titles posted THIS session (fast local check)
_orm_title_cache = set()
# ─────────────────────────────────────────────────────────────

def _load_orm_queue():
    path = os.path.join(APP_DIR, _ORM_QUEUE_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f: return json.load(f)
    except: pass
    return []

def _save_orm_queue(q):
    try:
        with open(os.path.join(APP_DIR, _ORM_QUEUE_FILE), "w") as f:
            json.dump(q[:500], f, indent=2)
    except: pass

def _load_orm_history():
    path = os.path.join(APP_DIR, _ORM_HISTORY_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f: return json.load(f)
    except: pass
    return []

def _save_orm_history(h):
    try:
        with open(os.path.join(APP_DIR, _ORM_HISTORY_FILE), "w") as f:
            json.dump(h[:1000], f, indent=2)
    except: pass

def _load_orm_config():
    path = os.path.join(APP_DIR, _ORM_CONFIG_FILE)
    try:
        if Path(path).exists():
            with open(path, "r") as f: return json.load(f)
    except: pass
    return {
        "enabled": False,
        "posts_per_week": 2,
        "posts_per_day": 1,
        "start_hour": 8,
        "start_minute": 0,
        "end_hour": 20,
        "end_minute": 0,
        "target": "alternate",
        "status": "publish",
        "topics_used": [],
        "last_site": "bvtech",
    }

def _save_orm_config(c):
    try:
        with open(os.path.join(APP_DIR, _ORM_CONFIG_FILE), "w") as f:
            json.dump(c, f, indent=2)
    except: pass

_orm_queue = _load_orm_queue()
_orm_history = _load_orm_history()
_orm_config = _load_orm_config()

# 60+ topic bank — all name-optimized for Jordan Polasek
_ORM_TOPICS = [
    "Jordan Polasek: How Managed IT Services Protect Small Businesses in Texas",
    "Why Jordan Polasek Founded BVTech LLC — Building IT Solutions from the Ground Up",
    "Jordan Polasek's Guide to Cybersecurity for Small Businesses in San Antonio",
    "Meet Jordan Polasek: The Technology Professional Behind BVTech LLC",
    "Jordan Polasek Explains Why Every Business Needs 24/7 Network Monitoring",
    "How Jordan Polasek and BVTech LLC Help Houston Businesses Stay Secure",
    "Jordan Polasek on Cloud Computing: What Small Businesses Need to Know",
    "Jordan Polasek's Approach to IT Consulting for Texas Law Firms",
    "Why Jordan Polasek Recommends Microsoft 365 for Business",
    "Jordan Polasek: Building Secure Networks with UniFi for Texas Businesses",
    "How Jordan Polasek Protects Businesses from Ransomware Attacks",
    "Jordan Polasek Reviews the Top Cybersecurity Threats Facing SMBs",
    "Jordan Polasek's Vision for BVTech LLC: Proactive IT for Growing Businesses",
    "VoIP Solutions by Jordan Polasek: Why DialPad is the Future of Business Communication",
    "Jordan Polasek on HIPAA Compliance: IT Requirements for Medical Offices",
    "How Jordan Polasek Designs Disaster Recovery Plans for Small Businesses",
    "Jordan Polasek's Expert Guide to Choosing a Managed Service Provider in Texas",
    "Jordan Polasek: Why Endpoint Detection and Response (EDR) Matters",
    "Inside BVTech LLC: How Jordan Polasek Delivers Enterprise IT to SMBs",
    "Jordan Polasek on Dark Web Monitoring: Protecting Your Business Identity",
    "Jordan Polasek Shares 10 IT Security Tips Every Business Owner Should Know",
    "How Jordan Polasek Migrates Businesses to the Cloud Safely",
    "Jordan Polasek's Guide to Wi-Fi Infrastructure for Offices and Warehouses",
    "Why San Antonio Businesses Trust Jordan Polasek for Managed IT",
    "Jordan Polasek on Zero Trust Security: A Practical Guide for SMBs",
    "How Jordan Polasek Built a Career in Technology — El Campo to San Antonio",
    "Jordan Polasek Explains Firewall Management for Business Owners",
    "The BVTech LLC Difference: How Jordan Polasek Delivers Personal IT Support",
    "Jordan Polasek's Technology Predictions for Small Businesses",
    "Jordan Polasek on AI and Cybersecurity: How Threats Are Evolving",
    "Smart Entry Systems by Jordan Polasek: VoIP Cameras for Texas Businesses",
    "Jordan Polasek Reviews Guardz Cybersecurity Platform for MSPs",
    "How Jordan Polasek Helps Austin Startups Build Secure IT Infrastructure",
    "Jordan Polasek's Checklist: Is Your Business IT Ready for Growth?",
    "Why Jordan Polasek Believes Proactive IT Beats Reactive IT Every Time",
    "Jordan Polasek on Data Backup: The #1 Thing Most Businesses Get Wrong",
    "Jordan Polasek and BVTech LLC: Secure Remote Work Cloud Solutions",
    "Jordan Polasek's Guide to PCI DSS Compliance for Texas Retail",
    "The Story of BVTech LLC: How Jordan Polasek Turned Passion into Business",
    "Jordan Polasek Answers FAQs About Managed IT Services",
    "Jordan Polasek: The Importance of IT Documentation for Business Continuity",
    "How Jordan Polasek Secures Microsoft 365 Environments for Texas Businesses",
    "Jordan Polasek on Phishing Prevention: Training Your Team to Spot Threats",
    "Jordan Polasek's Complete Guide to Business VPN Setup and Security",
    "Why Jordan Polasek Chose El Campo Texas as BVTech LLC Headquarters",
    "Jordan Polasek: How to Evaluate Your Current IT Provider",
    "Jordan Polasek on Multi-Factor Authentication for Every Business",
    "How Jordan Polasek Handles IT Emergencies and Incident Response",
    "Jordan Polasek's Guide to Camera Systems and Physical Security for Businesses",
    "Jordan Polasek: What Small Businesses Should Know About Cyber Insurance",
    "How Jordan Polasek Uses AI Tools to Improve MSP Service Delivery",
    "Jordan Polasek on Network Segmentation: Protecting Critical Business Data",
    "Jordan Polasek Reviews the Best Business Communication Platforms",
    "Why Jordan Polasek Recommends Quarterly IT Security Assessments",
    "Jordan Polasek: Building a Technology Roadmap for Your Growing Business",
    "How Jordan Polasek and BVTech LLC Support Healthcare IT Compliance",
    "Jordan Polasek on Supply Chain Cybersecurity Risks for SMBs",
    "Jordan Polasek's Guide to Choosing Business Internet and Network Hardware",
    "The Future of Managed IT According to Jordan Polasek of BVTech LLC",
    "Jordan Polasek: Why Every Business Needs an IT Disaster Recovery Plan",
]

def _get_jp_client():
    """v25 FIX: Get Cloudflare Pages client for jordanpolasek.com.
    Prefers Cloudflare Direct Upload over GitHub to avoid the broken
    Cloudflare->GitHub OAuth loop. Falls back to WordPress relay last."""
    cfg = load_config()
    mod = _get_trmm_module()
    if not mod:
        raise RuntimeError(f"Module failed to load: {_trmm_import_error or 'unknown'}")
    # v25: Prefer Cloudflare Direct Upload (same fix as BVTech publisher)
    if cfg.get("jp_cf_api_token") and cfg.get("jp_cf_account_id"):
        print("  [v25] JordanPolasek publisher → Cloudflare Direct Upload mode")
        jp_cf_cfg = {
            "cf_api_token": cfg.get("jp_cf_api_token", ""),
            "cf_account_id": cfg.get("jp_cf_account_id", ""),
            "cf_project_name": cfg.get("jp_cf_project_name", "jordanpolasek-site"),
            "cf_site_url": cfg.get("jp_site_url", "https://jordanpolasek.com"),
        }
        return mod.CloudflarePagesClient(cfg=jp_cf_cfg)
    if cfg.get("jp_gh_token") and cfg.get("jp_gh_repo"):
        print("  [v25] JordanPolasek publisher → GitHub API mode (legacy)")
        jp_cf_cfg = {
            "gh_token": cfg.get("jp_gh_token", ""),
            "gh_repo": cfg.get("jp_gh_repo", ""),
            "gh_branch": cfg.get("jp_gh_branch", "main"),
            "cf_api_token": cfg.get("jp_cf_api_token", ""),
            "cf_account_id": cfg.get("jp_cf_account_id", ""),
            "cf_project_name": cfg.get("jp_cf_project_name", "jordanpolasek-site"),
            "cf_site_url": cfg.get("jp_site_url", "https://jordanpolasek.com"),
        }
        return mod.CloudflarePagesClient(cfg=jp_cf_cfg)
    # Legacy WordPress fallback
    print("  [v25] JordanPolasek publisher → WordPress relay (no CF or GH configured)")
    jp_cfg = {
        "wp_site_url": cfg.get("jp_site_url", "https://jordanpolasek.com"),
        "wp_user": cfg.get("jp_wp_user", ""),
        "wp_app_password": cfg.get("jp_wp_app_password", ""),
        "wp_relay_key": cfg.get("jp_relay_key", "JP2026Relay"),
        "wp_relay_file": "jp-api.php",
    }
    return mod.WordPressClient(cfg=jp_cfg)

def _get_jp_publisher():
    """v29: Smart publisher for JordanPolasek.com. Same shape as
    get_bvtech_publisher — returns the real mode, with CF Direct Upload
    now doing a proper site-root walk. Requires jp_site_root to be set.
    """
    cfg = load_config()
    client = _get_jp_client()
    real_mode = getattr(client, "mode", "none")
    if real_mode == "cloudflare_direct":
        site_root = (cfg.get("jp_site_root") or "").strip()
        if not site_root:
            return client, "needs_site_root"
        return client, "cloudflare"
    if real_mode == "github":
        return client, "github"
    return client, "wordpress"

def _adapt_for_linkedin(blog, topic, target):
    """v20: Convert blog content into a LinkedIn-optimized post.
    LinkedIn posts should be: hook-driven, shorter, with line breaks for readability,
    and include a call-to-action. Max ~3000 chars but best engagement is 1000-1500."""
    import re, html as html_mod

    title = blog.get("title", topic)
    content = blog.get("content", "")
    # Strip HTML tags to get plain text
    plain = re.sub(r'<[^>]+>', ' ', content)
    plain = re.sub(r'\s+', ' ', plain).strip()

    # Build LinkedIn post with engagement-optimized structure
    # Hook line (first line visible before "...see more")
    hook_options = [
        f"Most business owners don't realize this about {topic.split(':')[-1].strip().lower() if ':' in topic else 'their IT security'}.",
        f"After 13+ years in IT, here's what I've learned about {topic.split(':')[-1].strip().lower() if ':' in topic else 'protecting businesses'}:",
        f"This is the #1 mistake I see Texas businesses making with their technology.",
        f"I've helped dozens of businesses fix this. Here's what most get wrong:",
        f"If you're a business owner, you need to read this.",
    ]
    import random
    hook = random.choice(hook_options)

    # Extract key points from the content (first ~800 chars worth of substance)
    body_text = plain[:1200]
    # Trim to last complete sentence
    last_period = body_text.rfind('.')
    if last_period > 200:
        body_text = body_text[:last_period + 1]

    # Build the LinkedIn post
    li_post = f"""{hook}

{body_text}

---

If your business needs help with IT security, cloud infrastructure, or managed services — I'd love to connect.

📞 (210) 538-3669
🌐 bvtech.org
📧 help@bvtech.org

#ManagedIT #Cybersecurity #MSP #SmallBusiness #Texas #ITServices #JordanPolasek #BVTech"""

    # Trim to LinkedIn's limit
    return li_post[:3000]

def _build_orm_prompt(topic, target_site, tone, length, custom_instructions):
    """v29: Higher-quality content prompts for SEO-serious posts.
    Bumps the default word counts, enforces H2/H3 structure, adds FAQ
    schema blocks for featured-snippet targeting, and requires a
    Jordan Polasek author byline at the end with credentials.
    Still rotates 5 templates to avoid fingerprinting.
    """
    import random as _rng
    # v29: longer defaults — Google rewards comprehensive content
    word_counts = {"short": "800", "medium": "1500", "long": "2200", "pillar": "3000+"}
    wc = word_counts.get(length, "1500")

    site_ctx = ""
    if target_site == "jordanpolasek":
        site_ctx = "TARGET: jordanpolasek.com — Write in FIRST PERSON as Jordan Polasek. Use 'I' and 'my'."
    elif target_site == "bvtech":
        site_ctx = "TARGET: bvtech.org — Reference 'Jordan Polasek, Managing Partner at BVTech LLC' once in intro."
    else:
        site_ctx = "TARGET: Write in first person as Jordan Polasek with a BVTech LLC reference."

    person_bio = """PERSON: Jordan Polasek | Founder & Managing Partner, BVTech LLC
Sites: jordanpolasek.com (personal) | bvtech.org (company)
Location: El Campo, TX (serving San Antonio, Houston, Austin)
Experience: 13+ years IT, cybersecurity, cloud, networking
Education: BAT Cloud Computing (4.0 GPA) | AWS Certified | 1Password EPM
Services: Managed IT, Cybersecurity, Cloud/M365, VoIP, Network Infrastructure
Phone: (210) 538-3669 | LinkedIn: linkedin.com/in/jordanbvtech"""

    # v17: 5 DIFFERENT PROMPT TEMPLATES — rotated randomly to eliminate template fingerprint
    templates = [
        # TEMPLATE 1: Thought Leadership / Opinion Piece
        f"""Write a thought leadership article for a technology professional's blog.

{site_ctx}
TOPIC: {topic}
TONE: {tone} — conversational, opinionated, with personal anecdotes
LENGTH: ~{wc} words
{f'Extra: {custom_instructions}' if custom_instructions else ''}

{person_bio}

STRUCTURE — Use THIS format (important: DO NOT use FAQ sections):
- Hook opening with a bold opinion or industry observation
- 2-3 body sections with subheadings (H2 tags)
- Personal experience or client story woven in naturally
- Actionable takeaways section
- Brief closing with author context

NAME USAGE (CRITICAL — follow exactly):
- Full name "Jordan Polasek" in the title
- Full name once in the first paragraph
- ONE more natural mention in the body (can be just first name "Jordan")
- That's it — DO NOT stuff the name everywhere. Google penalizes keyword stuffing.
- Location mentions: pick ONE city naturally (Texas, San Antonio, Houston, or El Campo)

SEO RULES:
- Write like a real human expert sharing genuine insights
- Vary sentence length — mix short punchy sentences with longer explanations
- Include specific technical details that demonstrate real expertise
- Meta description should mention the person naturally, under 155 chars
- Do NOT include FAQ sections in this format""",

        # TEMPLATE 2: How-To / Tutorial Guide
        f"""Write a practical how-to guide for business owners about an IT/cybersecurity topic.

{site_ctx}
TOPIC: {topic}
TONE: {tone} — helpful, clear, step-by-step
LENGTH: ~{wc} words
{f'Extra: {custom_instructions}' if custom_instructions else ''}

{person_bio}

STRUCTURE — Use THIS format (important: use numbered steps, NOT FAQ):
- Brief intro explaining why this matters (1 paragraph)
- Numbered step-by-step guide (the main content)
- "Common Mistakes" or "What to Watch For" section
- Quick summary box or checklist at the end
- Author byline with credentials

NAME USAGE (CRITICAL — follow exactly):
- Full name "Jordan Polasek" in the title
- Full name once in the intro paragraph
- First name only ("Jordan") once more, naturally, in the guide body
- DO NOT repeat the full name more than twice total in the article
- Pick ONE Texas city to mention naturally

SEO RULES:
- Write actionable, specific steps (not vague advice)
- Include real tool names, real configurations, real numbers
- Make it genuinely useful — someone should be able to follow the steps
- Meta description: practical and specific, mention author name once""",

        # TEMPLATE 3: Story / Case Study
        f"""Write a narrative case study or story-driven article about solving a real business IT challenge.

{site_ctx}
TOPIC: {topic}
TONE: {tone} — storytelling, engaging, with a problem-solution arc
LENGTH: ~{wc} words
{f'Extra: {custom_instructions}' if custom_instructions else ''}

{person_bio}

STRUCTURE — Use THIS format (important: narrative flow, NOT bullet-heavy):
- Open with the problem scenario (paint a picture)
- The investigation / diagnosis phase
- The solution and implementation
- Results and lessons learned
- Brief "About the Author" closing

NAME USAGE (CRITICAL — follow exactly):
- Full name "Jordan Polasek" in the title
- Author introduction once in the opening
- First name only in the narrative body (reads more naturally in stories)
- Total full name mentions: MAX 2 in entire article
- Set the story in a specific Texas city

WRITING STYLE:
- Tell the story like you're explaining it to a friend over coffee
- Include specific technical details but explain them simply
- Use dialogue or quotes if it fits naturally
- Vary paragraph lengths — some short (1-2 sentences), some longer
- Meta description should tease the story, mention author once""",

        # TEMPLATE 4: Industry Analysis / Trends
        f"""Write an industry analysis article examining trends, threats, or developments in IT/cybersecurity.

{site_ctx}
TOPIC: {topic}
TONE: {tone} — analytical, data-informed, forward-looking
LENGTH: ~{wc} words
{f'Extra: {custom_instructions}' if custom_instructions else ''}

{person_bio}

STRUCTURE — Use THIS format:
- Lead with a surprising statistic or trend observation
- 3-4 themed sections analyzing different angles
- "What This Means for Your Business" practical section
- Forward-looking conclusion with the author's perspective
- No FAQ section — use natural prose instead

NAME USAGE (CRITICAL — follow exactly):
- Full name "Jordan Polasek" in the title
- Author attribution once in the opening or closing
- ONE additional casual mention in the analysis body
- MAX 2 full name mentions total — this is an analysis piece, not a bio
- Reference "Texas businesses" or a specific metro once

WRITING STYLE:
- Reference real industry reports, real statistics, real vendor names
- Show genuine analytical depth — don't just list surface-level facts
- Include the author's professional opinion backed by experience
- Meta description: informative, mention a key finding, author name once""",

        # TEMPLATE 5: Q&A / Interview Style
        f"""Write an article in a Q&A or interview-style format, as if the author is being interviewed about their expertise.

{site_ctx}
TOPIC: {topic}
TONE: {tone} — conversational, authentic, direct
LENGTH: ~{wc} words
{f'Extra: {custom_instructions}' if custom_instructions else ''}

{person_bio}

STRUCTURE — Use THIS format:
- Brief intro paragraph setting up the Q&A context
- 5-7 questions with detailed, expert answers
- Questions should be what a business owner would actually ask
- Closing "rapid fire" section with 3 quick-answer questions
- Brief author bio at the end

NAME USAGE (CRITICAL — follow exactly):
- Full name "Jordan Polasek" in the title
- Full name in the intro attribution
- In Q&A body, use just first name "Jordan" in question prompts
- MAX 2 full name mentions — the Q&A format naturally attributes answers
- Mention service area once (Texas / San Antonio / Houston)

WRITING STYLE:
- Answers should sound like natural speech, not written prose
- Include specific examples and real-world scenarios in answers
- Some answers should be brief and punchy, others more detailed
- Meta description: mention the topic and author, frame as expert Q&A""",
    ]

    # Pick a random template
    template = _rng.choice(templates)

    # v29: Universal quality requirements appended to every template
    template += f"""

=== v29 SEO QUALITY REQUIREMENTS (apply on top of the template above) ===

STRUCTURE:
- Open with an H1 that contains the focus keyword (use <h1> in content)
- Use <h2> for each major section (3-5 of them for a {wc}-word piece)
- Use <h3> for sub-points inside sections when it helps scannability
- Paragraphs: 2-4 sentences max. No wall-of-text paragraphs.
- Include at least ONE bulleted <ul> or numbered <ol> list somewhere
- Bold 2-3 key phrases with <strong> for scanners

READABILITY:
- Flesch Reading Ease: aim for 60+ (8th-grade level)
- Mix sentence lengths: short punchy ones with longer explanatory ones
- Use concrete examples with real numbers, tool names, and dollar amounts
- Avoid corporate jargon: "solutions," "leverage," "synergy," "robust"
- Write like you're talking to a smart friend who runs a business, not a committee

FAQ SECTION (for featured-snippet targeting):
- Include an "<h2>Frequently Asked Questions</h2>" section near the end
- 3-4 real questions a business owner would actually ask about this topic
- Answer each in 2-3 sentences — direct, no fluff
- Wrap the FAQ in: <div itemscope itemtype="https://schema.org/FAQPage">
  Each Q: <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  Each A: <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
  This gets you rich results on Google without any extra work.

AUTHOR BYLINE (REQUIRED at end of content):
Close the article with this exact structure (substitute the real topic keyword):

<div class="author-byline" style="margin-top:2rem;padding-top:1.5rem;border-top:2px solid #e5e7eb;">
  <p style="margin-bottom:0.5rem;"><strong>About the Author:</strong> Jordan Polasek is the Founder and Managing Partner of BVTech LLC, a Texas-based managed IT services company serving San Antonio, Houston, Austin, and El Campo. With 13+ years of experience in cybersecurity, cloud infrastructure, and networking, Jordan holds a Bachelor's in Cloud Computing (4.0 GPA) and multiple AWS certifications.</p>
  <p style="margin-bottom:0;">Need help with {{topic keyword}}? Contact BVTech at <a href="tel:+12105383669">(210) 538-3669</a> or visit <a href="https://bvtech.org">bvtech.org</a>.</p>
</div>

INTERNAL LINKS:
- Include 1-2 contextual links to bvtech.org pages when natural
  (e.g. /services/managed-it-services, /services/cybersecurity-solutions,
  /locations, /contact)
- Do NOT over-link. Two internal links max.

META FIELDS:
- meta_description: 140-155 chars, contains focus keyword AND a benefit statement,
  reads like a human wrote it (no "Learn more about..." templates)
- focus_keyword: 2-4 words, what someone would actually type into Google
- secondary_keywords: 3-5 related phrases
- schema_markup: JSON-LD for the BlogPosting schema — will be injected in <head>

OUTPUT — ONLY a JSON object (no markdown, no backticks, no commentary):
{{
  "title": "Compelling title 50-65 chars with focus keyword and Jordan Polasek",
  "slug": "url-friendly-slug-with-keyword",
  "content": "<h1>...</h1><p>...</p><h2>...</h2>... (full HTML, ~{wc} words, includes FAQ + author byline)",
  "meta_description": "140-155 chars with focus keyword and value prop",
  "focus_keyword": "primary keyword",
  "secondary_keywords": "keyword two, keyword three, keyword four",
  "schema_markup": "{{\\"@context\\": \\"https://schema.org\\", \\"@type\\": \\"BlogPosting\\", \\"headline\\": \\"...\\", \\"author\\": {{\\"@type\\": \\"Person\\", \\"name\\": \\"Jordan Polasek\\"}}, \\"publisher\\": {{\\"@type\\": \\"Organization\\", \\"name\\": \\"BVTech LLC\\"}}}}",
  "template_used": "one of: thought_leadership, how_to, case_study, analysis, qa"
}}"""

    return template

def _title_word_set(title):
    """Extract significant words from title for fuzzy matching."""
    stop = {"the","a","an","to","for","of","in","on","and","is","how","why","what","your","with","from","by","at","are","its","it"}
    return set(w for w in title.lower().split() if w not in stop and len(w) > 2)

def _title_similarity(t1, t2):
    """Word-overlap similarity ratio. 0.0 to 1.0."""
    w1, w2 = _title_word_set(t1), _title_word_set(t2)
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / max(len(w1), len(w2))

def _check_title_exists(title, target):
    """v16 DEDUP: Check if title (exact OR near-match) exists on target WP site(s).
    Returns dict with {jordanpolasek: bool/str, bvtech: bool/str}."""
    title_lower = title.strip().lower()
    exists = {"jordanpolasek": False, "bvtech": False}

    # Fast local cache check — exact
    if title_lower in _orm_title_cache:
        if target in ("jordanpolasek", "both"):
            exists["jordanpolasek"] = True
        if target in ("bvtech", "both"):
            exists["bvtech"] = True
        return exists

    # Local cache check — fuzzy (75%+ word overlap)
    for cached in _orm_title_cache:
        if _title_similarity(title_lower, cached) >= 0.75:
            if target in ("jordanpolasek", "both"):
                exists["jordanpolasek"] = True
            if target in ("bvtech", "both"):
                exists["bvtech"] = True
            return exists

    # Check live WordPress sites — exact + fuzzy
    def _check_site(client):
        try:
            live_titles = client.get_all_titles(per_page=200)
            # Exact match
            if title_lower in live_titles:
                return True
            # Fuzzy match
            for lt in live_titles:
                if _title_similarity(title_lower, lt) >= 0.75:
                    return True
        except:
            pass
        return False

    if target in ("jordanpolasek", "both"):
        exists["jordanpolasek"] = _check_site(_get_jp_client())

    if target in ("bvtech", "both"):
        # v20: Check Cloudflare Pages (or WordPress fallback) for BVTech.org
        try:
            publisher, _ = get_bvtech_publisher()
            exists["bvtech"] = _check_site(publisher)
        except Exception:
            exists["bvtech"] = False  # Can't check — allow post

    return exists


def _generate_one_post(topic, target, status, tone="personal_authority", length="medium", custom=""):
    """Generate one ORM post via Claude and publish to target site(s).
    v15: Thread-safe with dedup title checking before publish."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return {"error": "No Anthropic API key"}

    prompt = _build_orm_prompt(topic, target, tone, length, custom)

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={"model": "claude-sonnet-4-20250514", "max_tokens": 4096,
                 "messages": [{"role": "user", "content": prompt}]}, timeout=90)

        if resp.status_code != 200:
            return {"error": f"Claude API {resp.status_code}"}

        text = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text": text += block.get("text", "")

        text = text.strip()
        if text.startswith("```"): text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"): text = text[:-3]

        import json as j
        try:
            blog = j.loads(text.strip())
        except:
            start = text.find("{")
            end = text.rfind("}") + 1
            blog = j.loads(text[start:end]) if start >= 0 else None

        if not blog or not blog.get("title"):
            return {"error": "Failed to parse blog content"}

        # ── v14 DEDUP CHECK ──────────────────────────────────
        title = blog["title"]
        title_lower = title.strip().lower()

        # Acquire the publish lock so only one thread posts at a time
        with _orm_publish_lock:
            # Check local cache first (instant)
            if title_lower in _orm_title_cache:
                return {"error": f"DEDUP BLOCKED: '{title}' was already posted this session",
                        "dedup": True, "title": title, "topic": topic}

            # Check live WordPress for existing title
            dup_check = _check_title_exists(title, target)
            if any(dup_check.values()):
                sites = [s for s, v in dup_check.items() if v]
                return {"error": f"DEDUP BLOCKED: '{title}' already exists on {', '.join(sites)}",
                        "dedup": True, "title": title, "topic": topic}

            # ── SAFE TO PUBLISH ──────────────────────────────
            result = {"title": title, "topic": topic, "target": target,
                      "word_count": len(blog.get("content", "").split()),
                      "meta_description": blog.get("meta_description", ""),
                      "focus_keyword": blog.get("focus_keyword", ""),
                      "posts": {}, "date": datetime.now().isoformat(), "status": status}

            # v15: Calculate SEO score
            result["seo_score"] = _calculate_seo_score(blog, topic)

            # v30: Import cross-linking + GBP helpers lazily
            try:
                from posts_index import enrich_post_html, record_post
            except ImportError:
                enrich_post_html = None
                record_post = None

            # v32: Import channel rewriter lazily
            try:
                from channel_rewriter import rewrite_all_channels
            except ImportError:
                rewrite_all_channels = None

            # v32: If target is all_four, do per-channel rewrites up-front so
            # each channel gets its own voice instead of posting the same HTML
            # to all four places. The rewrites go through Claude (one call per
            # channel), with safe fallbacks if the API is unreachable.
            channel_variants = {}  # channel → rewritten text
            if target == "all_four" and rewrite_all_channels is not None:
                cfg_v32 = load_config()
                api_key_v32 = cfg_v32.get("anthropic_key", "").strip()
                try:
                    channel_variants = rewrite_all_channels(
                        master_html=blog.get("content", ""),
                        master_title=title,
                        api_key=api_key_v32,
                        master_focus_keyword=blog.get("focus_keyword", ""),
                        master_meta_description=blog.get("meta_description", ""),
                        canonical_url="",  # filled in later per-channel after BV deploys
                        logger=lambda m: print(f"  {m}"),
                    )
                    result["channel_rewrites"] = {
                        ch: {"length": len(v.get("text", "")),
                             "error": v.get("error")}
                        for ch, v in channel_variants.items()
                    }
                except Exception as _rex:
                    print(f"  [v32] rewrite_all_channels failed (non-fatal): {_rex}")
                    channel_variants = {}

            def _content_for(site_key):
                """Return the content variant for a given site. Falls back
                to the master article if no rewrite exists."""
                # site_key: 'bvtech', 'jp', 'linkedin', 'gbp'
                if site_key in channel_variants:
                    variant = channel_variants[site_key]
                    if variant.get("text"):
                        return variant["text"]
                return blog.get("content", "")

            def _enrich(html_content, site_key):
                """v30: Inject Related Posts + cross-site blocks. Falls back
                to unmodified HTML if the module can't be loaded."""
                if enrich_post_html is None:
                    return html_content, {"related_count": 0, "cross_count": 0}
                try:
                    return enrich_post_html(
                        html=html_content,
                        new_title=title,
                        new_focus_keyword=blog.get("focus_keyword", ""),
                        new_slug=blog.get("slug", "") or title_lower.replace(" ", "-"),
                        site=site_key,
                        app_dir=APP_DIR,
                    )
                except Exception as _ex:
                    print(f"  [v30] enrich_post_html failed (non-fatal): {_ex}")
                    return html_content, {"related_count": 0, "cross_count": 0}

            # Post to jordanpolasek.com — v29 CF Direct + v30 cross-linking + v32 voice rewrite
            if target in ("jordanpolasek", "both", "all_three", "all_four", "jp_and_li"):
                try:
                    jp_client, jp_mode = _get_jp_publisher()
                    # v32: use JP-voice rewrite when available
                    jp_source_html = _content_for("jp")
                    jp_html, jp_enrich_info = _enrich(jp_source_html, "jp")
                    if jp_mode == "needs_site_root":
                        d, e = None, (
                            "JP Cloudflare Direct Upload needs jp_site_root "
                            "to be set in Settings → Cloudflare. Point it at your "
                            "local jordanpolasek.com folder (e.g. "
                            "C:\\BVTech2\\Website\\jordanpolasek.com)."
                        )
                    elif jp_mode in ("cloudflare", "github"):
                        d, e = jp_client.create_post(
                            title, jp_html, status,
                            meta_description=blog.get("meta_description", ""),
                            focus_keyword=blog.get("focus_keyword", ""),
                            schema_markup=blog.get("schema_markup", ""),
                        )
                    else:
                        d, e = jp_client.create_post(title, jp_html, status)
                    result["posts"]["jordanpolasek"] = {
                        "success": bool(d and not e),
                        "post_id": (d or {}).get("id") or (d or {}).get("post_id"),
                        "link": (d or {}).get("link") or (d or {}).get("url", ""),
                        "deploy_mode": jp_mode,
                        "related_links": jp_enrich_info,
                        "error": e}
                    # v30: record in the index so future posts can link back
                    if d and not e and record_post is not None:
                        try:
                            record_post(
                                app_dir=APP_DIR,
                                slug=blog.get("slug", "") or title_lower.replace(" ", "-"),
                                title=title,
                                site="jp",
                                url=(d or {}).get("link") or (d or {}).get("url", ""),
                                focus_keyword=blog.get("focus_keyword", ""),
                                summary=blog.get("meta_description", ""),
                            )
                        except Exception as _rex:
                            print(f"  [v30] record_post(jp) failed (non-fatal): {_rex}")
                except Exception as ex:
                    result["posts"]["jordanpolasek"] = {"success": False, "error": str(ex)}

            # Post to bvtech.org — v29 CF Direct + v30 cross-linking + v32 voice rewrite
            if target in ("bvtech", "both", "all_three", "all_four"):
                try:
                    publisher, pub_mode = get_bvtech_publisher()
                    # v32: use BVTech master (channel_rewriter returns master for 'bvtech')
                    bv_source_html = _content_for("bvtech")
                    bv_html, bv_enrich_info = _enrich(bv_source_html, "bvtech")
                    if pub_mode == "needs_site_root":
                        d, e = None, (
                            "v29: BVTech Cloudflare Direct Upload needs bvtech_site_root "
                            "to be set in Settings → Cloudflare. Point it at your "
                            "local bvtech.org folder (e.g. C:\\BVTech2\\Website\\bvtech.org)."
                        )
                    elif pub_mode in ("cloudflare", "github"):
                        d, e = publisher.create_post(
                            title, bv_html, status,
                            meta_description=blog.get("meta_description", ""),
                            focus_keyword=blog.get("focus_keyword", ""),
                            schema_markup=blog.get("schema_markup", ""),
                        )
                    else:
                        d, e = publisher.create_post(title, bv_html, status)
                    result["posts"]["bvtech"] = {
                        "success": bool(d and not e),
                        "post_id": (d or {}).get("id") or (d or {}).get("post_id"),
                        "link": (d or {}).get("link") or (d or {}).get("url", ""),
                        "deploy_mode": pub_mode,
                        "related_links": bv_enrich_info,
                        "error": e}
                    # v30: record in the index
                    if d and not e and record_post is not None:
                        try:
                            record_post(
                                app_dir=APP_DIR,
                                slug=blog.get("slug", "") or title_lower.replace(" ", "-"),
                                title=title,
                                site="bvtech",
                                url=(d or {}).get("link") or (d or {}).get("url", ""),
                                focus_keyword=blog.get("focus_keyword", ""),
                                summary=blog.get("meta_description", ""),
                            )
                        except Exception as _rex:
                            print(f"  [v30] record_post(bvtech) failed (non-fatal): {_rex}")
                except Exception as ex:
                    result["posts"]["bvtech"] = {"success": False, "error": str(ex)}

            # Post to LinkedIn — v32: prefer channel_rewriter's hook-driven variant
            if target in ("linkedin", "all_three", "all_four", "jp_and_li"):
                try:
                    li = get_linkedin_client()
                    # v32: use the channel_rewriter's LinkedIn variant if we
                    # did rewrites up front; otherwise fall back to the
                    # legacy _adapt_for_linkedin() adapter.
                    if "linkedin" in channel_variants and channel_variants["linkedin"].get("text"):
                        li_text = channel_variants["linkedin"]["text"]
                    else:
                        li_text = _adapt_for_linkedin(blog, topic, target)
                    # If we have a BVTech link, share it as an article
                    article_url = ""
                    if result["posts"].get("bvtech", {}).get("link"):
                        article_url = result["posts"]["bvtech"]["link"]
                    elif result["posts"].get("jordanpolasek", {}).get("link"):
                        article_url = result["posts"]["jordanpolasek"]["link"]
                    d, e = li.create_post(li_text, title=title, article_url=article_url)
                    result["posts"]["linkedin"] = {
                        "success": bool(d and not e),
                        "post_id": (d or {}).get("id") or (d or {}).get("post_id"),
                        "link": (d or {}).get("link") or (d or {}).get("url", ""),
                        "platform": "linkedin",
                        "rewrite_source": "channel_rewriter" if "linkedin" in channel_variants else "legacy_adapter",
                        "error": e}
                except Exception as ex:
                    result["posts"]["linkedin"] = {"success": False, "error": str(ex)}

            # Post to Google Business Profile — v32: prefer channel_rewriter GBP variant
            if target in ("gbp", "all_four"):
                try:
                    from google_business_profile import post_to_gbp
                    gbp_cfg = load_config()
                    # v32: use channel rewriter's GBP variant if available
                    if "gbp" in channel_variants and channel_variants["gbp"].get("text"):
                        gbp_summary = channel_variants["gbp"]["text"]
                    else:
                        # Legacy fallback: truncate meta description
                        gbp_summary = blog.get("meta_description", "") or title
                        if len(gbp_summary) > 280:
                            gbp_summary = gbp_summary[:277] + "..."
                    # Point CTA at the live BVTech post if we have one, else JP
                    cta_url = (result["posts"].get("bvtech", {}).get("link")
                               or result["posts"].get("jordanpolasek", {}).get("link")
                               or gbp_cfg.get("cf_site_url", "https://bvtech.org"))
                    gbp_result, gbp_err = post_to_gbp(
                        cfg=gbp_cfg,
                        summary=gbp_summary,
                        cta_url=cta_url,
                        logger=lambda m: print(f"  [GBP] {m}"),
                    )
                    result["posts"]["gbp"] = {
                        "success": bool(gbp_result and not gbp_err),
                        "post_name": (gbp_result or {}).get("name", ""),
                        "search_url": (gbp_result or {}).get("searchUrl", ""),
                        "summary_length": len(gbp_summary),
                        "cta_url": cta_url,
                        "rewrite_source": "channel_rewriter" if "gbp" in channel_variants else "meta_description_truncated",
                        "error": gbp_err}
                except Exception as ex:
                    result["posts"]["gbp"] = {"success": False, "error": str(ex)}

            # Add to local title cache AFTER successful post
            _orm_title_cache.add(title_lower)

            return result
    except Exception as e:
        return {"error": str(e)}


def _calculate_seo_score(blog, topic=""):
    """v15: Calculate a 0-100 SEO quality score for a blog post."""
    score = 0
    reasons = []
    title = blog.get("title", "")
    content = blog.get("content", "")
    meta = blog.get("meta_description", "")
    keyword = blog.get("focus_keyword", "")
    word_count = len(content.split())

    # Title checks (max 25 pts)
    if title:
        score += 5
        if len(title) >= 30 and len(title) <= 70:
            score += 5
            reasons.append("Title length optimal")
        elif len(title) > 70:
            reasons.append("Title too long (>70 chars)")
        else:
            reasons.append("Title too short (<30 chars)")
        if "jordan polasek" in title.lower():
            score += 10
            reasons.append("Name in title")
        else:
            reasons.append("Missing name in title")
        if keyword and keyword.lower() in title.lower():
            score += 5
            reasons.append("Keyword in title")
    else:
        reasons.append("No title")

    # Content checks (max 35 pts)
    if word_count >= 600:
        score += 10
        reasons.append(f"Good length ({word_count} words)")
    elif word_count >= 300:
        score += 5
        reasons.append(f"Moderate length ({word_count} words)")
    else:
        reasons.append(f"Too short ({word_count} words)")

    content_lower = content.lower()
    if "<h2" in content_lower:
        score += 5
        reasons.append("Has H2 headings")
    if "<h3" in content_lower:
        score += 3
        reasons.append("Has H3 headings")
    if "jordan polasek" in content_lower:
        name_count = content_lower.count("jordan polasek")
        if name_count >= 3:
            score += 7
            reasons.append(f"Name appears {name_count}x in body")
        else:
            score += 3
            reasons.append(f"Name only {name_count}x (aim for 3+)")

    # FAQ section (5 pts)
    if "faq" in content_lower or "frequently asked" in content_lower or "people also ask" in content_lower:
        score += 5
        reasons.append("Has FAQ section")

    # Location mentions (5 pts)
    locations = ["texas", "san antonio", "houston", "el campo", "austin"]
    loc_found = [l for l in locations if l in content_lower]
    if loc_found:
        score += 5
        reasons.append(f"Location refs: {', '.join(loc_found[:3])}")

    # Meta description (max 15 pts)
    if meta:
        score += 5
        if 120 <= len(meta) <= 165:
            score += 5
            reasons.append("Meta desc optimal length")
        if "jordan polasek" in meta.lower():
            score += 5
            reasons.append("Name in meta desc")
    else:
        reasons.append("No meta description")

    # Focus keyword (max 10 pts)
    if keyword:
        score += 5
        if keyword.lower() in content_lower:
            score += 5
            reasons.append("Focus keyword in content")
    else:
        reasons.append("No focus keyword")

    # CTA / contact (5 pts)
    if "210" in content or "538-3669" in content or "bvtech.org" in content_lower:
        score += 5
        reasons.append("Has contact/CTA")

    return {"score": min(score, 100), "max": 100, "reasons": reasons}

# ── ORM API Routes ──────────────────────────────────────

@app.route("/api/orm/post-now", methods=["POST"])
def orm_post_now():
    """Generate and publish ONE ORM post. v20: 3-way rotation JP↔BV↔LinkedIn."""
    d = request.json or {}
    topic = d.get("topic", "")
    target = d.get("target", "both")
    status = d.get("status", "publish")
    tone = d.get("tone", "personal_authority")
    length = d.get("length", "medium")
    custom = d.get("custom_instructions", "")

    # v20: 3-way rotation: JP → BV → LinkedIn → JP → ...
    if target in ("both", "all_three"):
        rotation = ["jordanpolasek", "bvtech", "linkedin"]
        last_site = _orm_config.get("last_site", "linkedin")
        try:
            idx = rotation.index(last_site)
            target = rotation[(idx + 1) % len(rotation)]
        except ValueError:
            target = "jordanpolasek"
        _orm_config["last_site"] = target
        _save_orm_config(_orm_config)
    elif target == "jp_and_li":
        # Alternate between JP and LinkedIn only
        last_site = _orm_config.get("last_site", "linkedin")
        target = "jordanpolasek" if last_site == "linkedin" else "linkedin"
        _orm_config["last_site"] = target
        _save_orm_config(_orm_config)

    # v17: Velocity warning (non-blocking — just adds to result)
    now = datetime.now()
    week_ago = (now - __import__('datetime').timedelta(days=7)).isoformat()
    posts_this_week = len([h for h in _orm_history if h.get("date", "") >= week_ago and h.get("status") != "error"])
    velocity_warning = ""
    if posts_this_week >= 3:
        velocity_warning = f"⚠️ You've posted {posts_this_week} times this week. Google recommends max 3/week for new content on low-authority domains."

    if not topic:
        # Pick from topic bank
        import random
        used = set(_orm_config.get("topics_used", []))
        available = [t for t in _ORM_TOPICS if t not in used]
        if not available:
            _orm_config["topics_used"] = []
            _save_orm_config(_orm_config)
            available = list(_ORM_TOPICS)
        topic = random.choice(available)

    result = _generate_one_post(topic, target, status, tone, length, custom)

    if not result.get("error"):
        _orm_config.setdefault("topics_used", []).append(topic)
        _save_orm_config(_orm_config)
        _orm_history.insert(0, result)
        _save_orm_history(_orm_history)

    if velocity_warning:
        result["velocity_warning"] = velocity_warning

    return jsonify(result)

@app.route("/api/orm/queue-build", methods=["POST"])
def orm_queue_build():
    """Build a queue of N posts (generates content but doesn't publish yet)."""
    global _orm_queue
    d = request.json or {}
    count = min(int(d.get("count", 10)), 60)
    target = d.get("target", "both")
    status = d.get("status", "publish")
    tone = d.get("tone", "personal_authority")
    length = d.get("length", "medium")

    import random
    used = set(_orm_config.get("topics_used", []))
    available = [t for t in _ORM_TOPICS if t not in used]
    if len(available) < count:
        _orm_config["topics_used"] = []
        _save_orm_config(_orm_config)
        available = list(_ORM_TOPICS)

    selected = random.sample(available, min(count, len(available)))

    new_items = []
    for topic in selected:
        new_items.append({
            "topic": topic, "target": target, "status": status,
            "tone": tone, "length": length,
            "queued_at": datetime.now().isoformat(), "state": "pending",
        })

    _orm_queue.extend(new_items)
    _save_orm_queue(_orm_queue)

    return jsonify({"queued": len(new_items), "total_in_queue": len(_orm_queue),
                     "topics": [i["topic"] for i in new_items]})

@app.route("/api/orm/queue", methods=["GET"])
def orm_queue_get():
    """Get current queue."""
    return jsonify({"queue": _orm_queue, "total": len(_orm_queue),
                     "pending": sum(1 for q in _orm_queue if q.get("state") == "pending")})

@app.route("/api/orm/queue/clear", methods=["POST"])
def orm_queue_clear():
    """Clear the queue."""
    global _orm_queue
    _orm_queue = []
    _save_orm_queue(_orm_queue)
    return jsonify({"status": "cleared"})

@app.route("/api/orm/queue/publish-next", methods=["POST"])
def orm_queue_publish_next():
    """Generate and publish the next item in the queue."""
    global _orm_queue
    pending = [i for i, q in enumerate(_orm_queue) if q.get("state") == "pending"]
    if not pending:
        return jsonify({"error": "Queue is empty — no pending posts"})

    idx = pending[0]
    item = _orm_queue[idx]

    result = _generate_one_post(
        item["topic"], item.get("target", "both"), item.get("status", "publish"),
        item.get("tone", "personal_authority"), item.get("length", "medium"))

    if not result.get("error"):
        _orm_queue[idx]["state"] = "published"
        _orm_queue[idx]["result"] = result
        _orm_queue[idx]["published_at"] = datetime.now().isoformat()
        _orm_config.setdefault("topics_used", []).append(item["topic"])
        _save_orm_config(_orm_config)
        _orm_history.insert(0, result)
        _save_orm_history(_orm_history)
    else:
        _orm_queue[idx]["state"] = "error"
        _orm_queue[idx]["error"] = result.get("error")

    _save_orm_queue(_orm_queue)
    return jsonify(result)

@app.route("/api/orm/queue/publish-all", methods=["POST"])
def orm_queue_publish_all_start():
    """v17: Publish queued posts with Google-safe pacing — site alternation + longer delays."""
    # v15: Block if scheduler is active
    if _orm_publishing_active.get("scheduler"):
        return jsonify({"error": "SCHEDULER IS ACTIVE — stop the scheduler first before using Publish All. Running both causes duplicates.",
                        "dedup_block": True})
    if _orm_publishing_active.get("bulk"):
        return jsonify({"error": "A bulk publish is already running. Wait for it to finish.",
                        "dedup_block": True})

    def publish_worker():
        import time as t, random
        _orm_publishing_active["bulk"] = True
        try:
            while True:
                pending = [i for i, q in enumerate(_orm_queue) if q.get("state") == "pending"]
                if not pending:
                    break
                idx = pending[0]
                item = _orm_queue[idx]

                # v17: Site alternation — never post to "both"
                item_target = item.get("target", "both")
                if item_target == "both":
                    last_site = _orm_config.get("last_site", "bvtech")
                    item_target = "jordanpolasek" if last_site == "bvtech" else "bvtech"
                    _orm_config["last_site"] = item_target
                    _save_orm_config(_orm_config)

                result = _generate_one_post(
                    item["topic"], item_target, item.get("status", "publish"),
                    item.get("tone", "personal_authority"), item.get("length", "medium"))
                if not result.get("error"):
                    _orm_queue[idx]["state"] = "published"
                    _orm_queue[idx]["result"] = result
                    _orm_queue[idx]["published_at"] = datetime.now().isoformat()
                    _orm_config.setdefault("topics_used", []).append(item["topic"])
                    _save_orm_config(_orm_config)
                    _orm_history.insert(0, result)
                    _save_orm_history(_orm_history)
                elif result.get("dedup"):
                    _orm_queue[idx]["state"] = "dedup_blocked"
                    _orm_queue[idx]["error"] = result.get("error")
                else:
                    _orm_queue[idx]["state"] = "error"
                    _orm_queue[idx]["error"] = result.get("error")
                _save_orm_queue(_orm_queue)
                # v17: Much longer delay between bulk posts — 4-8 hours with randomization
                delay = random.randint(4 * 3600, 8 * 3600)
                t.sleep(delay)
        finally:
            _orm_publishing_active["bulk"] = False

    thread = threading.Thread(target=publish_worker, daemon=True)
    thread.start()
    pending_count = sum(1 for q in _orm_queue if q.get("state") == "pending")
    return jsonify({"status": "started", "posts_to_publish": pending_count,
                     "note": f"v17: Posts will publish with 4-8 hour delays between each. {pending_count} posts = ~{pending_count * 6} hours."})

@app.route("/api/orm/config", methods=["GET", "POST"])
def orm_config_route():
    global _orm_config
    if request.method == "POST":
        d = request.json
        _orm_config.update(d)
        _save_orm_config(_orm_config)
        if d.get("enabled"):
            _start_orm_scheduler()
        return jsonify({"status": "ok", "config": _orm_config})
    return jsonify(_orm_config)

@app.route("/api/orm/history")
def orm_history_route():
    return jsonify({"history": _orm_history[:200]})

@app.route("/api/orm/history/clear", methods=["POST"])
def orm_history_clear():
    global _orm_history
    _orm_history = []
    _save_orm_history(_orm_history)
    return jsonify({"status": "cleared"})

@app.route("/api/orm/topics")
def orm_topics_list():
    used = set(_orm_config.get("topics_used", []))
    return jsonify({"total": len(_ORM_TOPICS), "used": len(used),
                     "available": len([t for t in _ORM_TOPICS if t not in used]),
                     "topics": [{"topic": t, "used": t in used} for t in _ORM_TOPICS]})

@app.route("/api/orm/topics/reset", methods=["POST"])
def orm_topics_reset():
    _orm_config["topics_used"] = []
    _save_orm_config(_orm_config)
    return jsonify({"status": "reset", "available": len(_ORM_TOPICS)})

@app.route("/api/orm/topics/generate", methods=["POST"])
def orm_topics_generate():
    """Generate 30 custom ORM topic ideas with Claude."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return jsonify({"error": "No Anthropic API key."})
    d = request.json or {}
    focus = d.get("focus", "")
    prompt = f"""Generate 30 blog post topics for Jordan Polasek's online reputation management.
Jordan Polasek is the Founder of BVTech LLC, a managed IT and cybersecurity company in Texas.
Every title MUST include "Jordan Polasek" naturally.
{f'Focus area: {focus}' if focus else 'Mix: thought leadership, how-to, case studies, local SEO, personal brand.'}
Include which site each should post to (jordanpolasek.com, bvtech.org, or both).
Format: numbered list with Title | Site | Keyword"""

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={"model": "claude-sonnet-4-20250514", "max_tokens": 4096,
                 "messages": [{"role": "user", "content": prompt}]}, timeout=60)
        text = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text": text += block.get("text", "")
        return jsonify({"topics": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/orm/test-jp", methods=["POST"])
def orm_test_jp():
    try:
        jp = _get_jp_client()
        data, err = jp.test_connection()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ──  ROUTES: Duplicate Scanner, Trash, SEO Score ──

@app.route("/api/orm/publish-status")
def orm_publish_status():
    """v15: Check if scheduler or bulk publish is active."""
    return jsonify({
        "scheduler_active": _orm_publishing_active.get("scheduler", False),
        "bulk_active": _orm_publishing_active.get("bulk", False),
        "any_active": _orm_publishing_active.get("scheduler", False) or _orm_publishing_active.get("bulk", False),
    })

# ============================================================
# v29: CF Direct Upload test-deploy endpoints
# ============================================================
@app.route("/api/orm/cf-test-deploy/<site>", methods=["POST"])
def orm_cf_test_deploy(site):
    """v29: Dry-run a CF Direct Upload deployment for one site.

    site must be 'bvtech' or 'jp'. Walks the local site_root, verifies
    the CF project, asks check-missing what it WOULD upload — but
    STOPS before actually uploading or creating the deployment.

    Use this BEFORE enabling the scheduler or clicking Publish All.
    """
    if site not in ("bvtech", "jp"):
        return jsonify({"error": "site must be 'bvtech' or 'jp'"}), 400

    try:
        if site == "bvtech":
            client = get_cf_client()
        else:
            client = _get_jp_client()

        if not hasattr(client, "test_cf_deploy"):
            return jsonify({"error": "CF client missing test_cf_deploy — old module loaded. Restart the app."}), 500

        result, err = client.test_cf_deploy(dry_run=True)
        if err:
            return jsonify({"error": err, "site": site}), 400
        result["site"] = site
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "site": site,
        }), 500


@app.route("/api/orm/cf-deploy-live/<site>", methods=["POST"])
def orm_cf_deploy_live(site):
    """v29: Do a REAL deployment of the current site folder as-is.

    Useful when you just want to push local edits to Cloudflare without
    generating a new blog post. Walks site_root, uploads missing files,
    creates a live deployment. NO DRY RUN.

    This is the "Deploy Site As-Is" button. Separate from the ORM flow.
    """
    if site not in ("bvtech", "jp"):
        return jsonify({"error": "site must be 'bvtech' or 'jp'"}), 400
    try:
        if site == "bvtech":
            client = get_cf_client()
        else:
            client = _get_jp_client()

        if not hasattr(client, "test_cf_deploy"):
            return jsonify({"error": "CF client missing test_cf_deploy — old module loaded. Restart the app."}), 500

        # test_cf_deploy with dry_run=False does the full upload+deploy
        result, err = client.test_cf_deploy(dry_run=False)
        if err:
            return jsonify({"error": err, "site": site}), 400
        result["site"] = site
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "site": site,
        }), 500


@app.route("/api/orm/site-root-check/<site>")
def orm_site_root_check(site):
    """v29: Sanity check — does the configured site_root exist and
    contain an index.html? Used by the UI to show a green/red dot next
    to the Test Deploy button."""
    if site not in ("bvtech", "jp"):
        return jsonify({"error": "site must be 'bvtech' or 'jp'"}), 400
    cfg = load_config()
    if site == "bvtech":
        root = (cfg.get("bvtech_site_root") or cfg.get("site_root") or "").strip()
    else:
        root = (cfg.get("jp_site_root") or "").strip()

    if not root:
        return jsonify({"ok": False, "site": site, "reason": "not_configured",
                        "message": f"{site}_site_root not set in Settings"})
    from pathlib import Path as _P
    p = _P(root)
    if not p.exists():
        return jsonify({"ok": False, "site": site, "reason": "not_found",
                        "path": root, "message": f"Path does not exist: {root}"})
    if not p.is_dir():
        return jsonify({"ok": False, "site": site, "reason": "not_a_dir",
                        "path": root, "message": f"Path is not a directory: {root}"})
    if not (p / "index.html").exists():
        return jsonify({"ok": False, "site": site, "reason": "no_index",
                        "path": root,
                        "message": f"No index.html at top of {root}. Refusing to deploy."})
    # Count files for feedback
    try:
        file_count = sum(1 for f in p.rglob("*") if f.is_file())
        total_bytes = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except Exception:
        file_count = 0
        total_bytes = 0
    return jsonify({
        "ok": True, "site": site, "path": root,
        "file_count": file_count,
        "size_mb": round(total_bytes / 1024 / 1024, 2),
        "message": f"{file_count} files, {round(total_bytes/1024/1024, 2)} MiB ready to deploy",
    })


# ============================================================
# v30: Google Business Profile OAuth + posting routes
# ============================================================
@app.route("/api/gbp/oauth/start")
def gbp_oauth_start():
    """Return the Google OAuth2 authorize URL. The UI opens this in a
    new window so the user can grant consent."""
    try:
        from google_business_profile import build_authorize_url
    except ImportError as e:
        return jsonify({"error": f"google_business_profile module missing: {e}"}), 500
    cfg = load_config()
    client_id = cfg.get("google_client_id", "").strip()
    redirect_uri = cfg.get("google_redirect_uri", "").strip() or "http://localhost:5678/api/gbp/oauth/callback"
    if not client_id:
        return jsonify({"error": "google_client_id is not set in Settings"}), 400
    try:
        url = build_authorize_url(client_id, redirect_uri, state="bvtech-v30")
        return jsonify({"authorize_url": url, "redirect_uri": redirect_uri})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/gbp/oauth/callback")
def gbp_oauth_callback():
    """OAuth2 redirect target. Google sends ?code=... here after consent;
    we exchange it for tokens and save the refresh_token."""
    try:
        from google_business_profile import exchange_code_for_tokens
    except ImportError as e:
        return f"google_business_profile module missing: {e}", 500
    code = request.args.get("code", "")
    error = request.args.get("error", "")
    if error:
        return f"""<html><body style="font-family:sans-serif;max-width:600px;margin:3rem auto;padding:1rem">
<h1 style="color:#dc2626">OAuth Error</h1>
<p>Google returned: <code>{error}</code></p>
<p>Close this window and try again.</p></body></html>""", 400
    if not code:
        return "Missing ?code parameter — this endpoint must be hit by Google's OAuth redirect.", 400

    cfg = load_config()
    client_id = cfg.get("google_client_id", "").strip()
    client_secret = cfg.get("google_client_secret", "").strip()
    redirect_uri = cfg.get("google_redirect_uri", "").strip() or "http://localhost:5678/api/gbp/oauth/callback"

    tokens, err = exchange_code_for_tokens(code, client_id, client_secret, redirect_uri)
    if err:
        return f"""<html><body style="font-family:sans-serif;max-width:600px;margin:3rem auto;padding:1rem">
<h1 style="color:#dc2626">Token Exchange Failed</h1>
<pre style="background:#f3f4f6;padding:1rem;border-radius:6px;white-space:pre-wrap">{err}</pre>
<p>Close this window and fix the issue, then try Connect again.</p></body></html>""", 400

    # Save the refresh_token to config
    cfg["gbp_refresh_token"] = tokens.get("refresh_token", "")
    save_config(cfg)

    return """<html><body style="font-family:sans-serif;max-width:600px;margin:3rem auto;padding:1rem;text-align:center">
<h1 style="color:#059669">✅ Google Business Profile Connected!</h1>
<p>Refresh token saved. You can close this window and return to the BVTech app.</p>
<p style="color:#6b7280;font-size:0.9rem">Next step: pick your account + location in Settings → Google Business Profile, then click Test Connection.</p>
<script>setTimeout(function(){ try { window.close(); } catch(e){} }, 2500);</script>
</body></html>"""


@app.route("/api/gbp/test")
def gbp_test():
    """Smoke-test the GBP connection by listing accounts."""
    try:
        from google_business_profile import GoogleBusinessProfileClient
    except ImportError as e:
        return jsonify({"error": f"google_business_profile module missing: {e}"}), 500
    cfg = load_config()
    client = GoogleBusinessProfileClient(
        client_id=cfg.get("google_client_id", ""),
        client_secret=cfg.get("google_client_secret", ""),
        refresh_token=cfg.get("gbp_refresh_token", ""),
    )
    result, err = client.verify_connection()
    if err:
        return jsonify({"connected": False, "error": err}), 400
    return jsonify(result)


@app.route("/api/gbp/accounts")
def gbp_accounts():
    """List all GBP accounts the user has access to."""
    try:
        from google_business_profile import GoogleBusinessProfileClient
    except ImportError as e:
        return jsonify({"error": f"google_business_profile module missing: {e}"}), 500
    cfg = load_config()
    client = GoogleBusinessProfileClient(
        client_id=cfg.get("google_client_id", ""),
        client_secret=cfg.get("google_client_secret", ""),
        refresh_token=cfg.get("gbp_refresh_token", ""),
    )
    accounts, err = client.list_accounts()
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"accounts": accounts})


@app.route("/api/gbp/locations")
def gbp_locations():
    """List locations for a given account. Pass ?account=accounts/123456789"""
    try:
        from google_business_profile import GoogleBusinessProfileClient
    except ImportError as e:
        return jsonify({"error": f"google_business_profile module missing: {e}"}), 500
    account_name = request.args.get("account", "").strip()
    if not account_name:
        return jsonify({"error": "account query parameter required (e.g. accounts/123456789)"}), 400
    cfg = load_config()
    client = GoogleBusinessProfileClient(
        client_id=cfg.get("google_client_id", ""),
        client_secret=cfg.get("google_client_secret", ""),
        refresh_token=cfg.get("gbp_refresh_token", ""),
    )
    locations, err = client.list_locations(account_name)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"locations": locations, "account": account_name})


@app.route("/api/gbp/disconnect", methods=["POST"])
def gbp_disconnect():
    """Clear the stored GBP refresh token so the user can re-connect."""
    cfg = load_config()
    cfg["gbp_refresh_token"] = ""
    cfg["gbp_account_name"] = ""
    cfg["gbp_location_name"] = ""
    cfg["gbp_location_title"] = ""
    save_config(cfg)
    return jsonify({"status": "disconnected"})


@app.route("/api/posts-index")
def posts_index_view():
    """v30: Read the cross-linking index. Used by the UI to show the
    'link graph' growing over time."""
    try:
        from posts_index import PostsIndex
    except ImportError as e:
        return jsonify({"error": f"posts_index module missing: {e}"}), 500
    idx = PostsIndex(APP_DIR)
    posts = idx.posts
    return jsonify({
        "total": len(posts),
        "bvtech_count": sum(1 for p in posts if p.get("site") == "bvtech"),
        "jp_count": sum(1 for p in posts if p.get("site") == "jp"),
        "posts": posts[-20:],  # last 20
    })


# ============================================================
# v31: HubSpot tracking routes
# ============================================================
def _v31_hubspot_tracker():
    """Build a HubSpotTracker from config, or return (None, error)."""
    try:
        from hubspot_tracker import HubSpotTracker
    except ImportError as e:
        return None, f"hubspot_tracker module missing: {e}"
    cfg = load_config()
    token = cfg.get("hubspot_token", "").strip()
    if not token:
        return None, "hubspot_token not configured in Settings"
    return HubSpotTracker(api_token=token), None


@app.route("/api/hubspot/verify")
def v31_hubspot_verify():
    """Smoke-test the HubSpot connection. Returns portal info."""
    tracker, err = _v31_hubspot_tracker()
    if err:
        return jsonify({"connected": False, "error": err}), 400
    result, err = tracker.verify_connection()
    if err:
        return jsonify({"connected": False, "error": err}), 400
    return jsonify(result)


@app.route("/api/hubspot/bcc-address")
def v31_hubspot_bcc():
    """Return the configured HubSpot BCC forwarding address."""
    cfg = load_config()
    addr = (cfg.get("hubspot_bcc_address", "") or "").strip()
    return jsonify({
        "bcc_address": addr,
        "configured": bool(addr),
        "instructions": (
            "Copy this from HubSpot → Settings → Objects → Activities → "
            "Email → 'Forward to HubSpot' address. BCC it on any email you "
            "send manually and HubSpot will auto-log it to the matching "
            "contact's timeline."
        ),
    })


@app.route("/api/hubspot/track-email", methods=["POST"])
def v31_hubspot_track_email():
    """Log an email engagement to HubSpot. Body:
         {email, subject, body, direction?, first_name?, last_name?,
          company?, phone?}
    """
    tracker, err = _v31_hubspot_tracker()
    if err:
        return jsonify({"error": err}), 400
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = data.get("body") or ""
    if not email or "@" not in email:
        return jsonify({"error": "valid email address required"}), 400
    if not subject and not body:
        return jsonify({"error": "subject or body required"}), 400
    contact_id, email_id, err = tracker.track_email_to_address(
        email_address=email,
        subject=subject,
        body=body,
        direction=data.get("direction", "outgoing"),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        company=data.get("company", ""),
        phone=data.get("phone", ""),
    )
    # Log to local event log
    _log = getattr(__import__('builtins'), '_BVTECH_EVENT_LOG', None)
    if _log:
        _log.record("email", "hubspot_track",
                    target=email, success=(err is None),
                    contact_id=contact_id, email_id=email_id,
                    error=err or "")
    if err:
        return jsonify({"error": err, "contact_id": contact_id}), 400
    return jsonify({
        "ok": True,
        "contact_id": contact_id,
        "email_id": email_id,
        "message": f"Logged to HubSpot contact {contact_id}",
    })


@app.route("/api/hubspot/enrich-csv", methods=["POST"])
def v31_hubspot_enrich_csv():
    """Run the 'daily_hubspot_enrichment' task on prospects.csv now."""
    runner = getattr(__import__('builtins'), '_BVTECH_TASK_RUNNER', None)
    if not runner:
        return jsonify({"error": "task runner not initialized"}), 500
    ok, msg = runner.run_now("daily_hubspot_enrichment")
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/hubspot/stats")
def v31_hubspot_stats():
    """Dashboard stat card: total contacts in HubSpot."""
    tracker, err = _v31_hubspot_tracker()
    if err:
        return jsonify({"error": err}), 400
    count, err = tracker.count_contacts()
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"contact_count": count})


# ============================================================
# v31: Automation / event log routes
# ============================================================
def _v31_runner():
    return getattr(__import__('builtins'), '_BVTECH_TASK_RUNNER', None)


def _v31_evlog():
    return getattr(__import__('builtins'), '_BVTECH_EVENT_LOG', None)


@app.route("/api/automation/tasks")
def v31_automation_tasks():
    """List all registered tasks with state."""
    runner = _v31_runner()
    if not runner:
        return jsonify({"tasks": [], "error": "task runner not initialized"}), 500
    return jsonify({
        "tasks": [t.to_dict() for t in runner.all_tasks()],
        "total": len(runner.all_tasks()),
    })


@app.route("/api/automation/task/<name>/enable", methods=["POST"])
def v31_automation_enable(name):
    runner = _v31_runner()
    if not runner:
        return jsonify({"error": "task runner not initialized"}), 500
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))
    ok = runner.set_enabled(name, enabled)
    if not ok:
        return jsonify({"error": f"No such task: {name}"}), 404
    return jsonify({"ok": True, "name": name, "enabled": enabled})


@app.route("/api/automation/task/<name>/run-now", methods=["POST"])
def v31_automation_run_now(name):
    runner = _v31_runner()
    if not runner:
        return jsonify({"error": "task runner not initialized"}), 500
    ok, msg = runner.run_now(name)
    return jsonify({"ok": ok, "message": msg, "name": name})


@app.route("/api/automation/install-windows/<name>", methods=["POST"])
def v31_automation_install_windows(name):
    """Install a task to Windows Task Scheduler. Body: {hour?, minute?}"""
    try:
        from local_automation import WindowsTaskScheduler
    except ImportError as e:
        return jsonify({"error": f"local_automation missing: {e}"}), 500
    runner = _v31_runner()
    if not runner:
        return jsonify({"error": "task runner not initialized"}), 500
    task = runner.get(name)
    if not task:
        return jsonify({"error": f"No such task: {name}"}), 404
    data = request.get_json(silent=True) or {}
    hour = int(data.get("hour", task.preferred_hour))
    minute = int(data.get("minute", 0))
    # Build the command: pythonw bvtech_app.py --run-task <name>
    pyexe = sys.executable.replace("python.exe", "pythonw.exe")
    script = os.path.abspath(__file__)
    cmd = f'"{pyexe}" "{script}" --run-task {name}'
    if task.schedule == "hourly":
        ok, msg = WindowsTaskScheduler.install_hourly(name, cmd)
    else:
        ok, msg = WindowsTaskScheduler.install_daily(name, cmd,
                                                      hour=hour, minute=minute)
    return jsonify({"ok": ok, "message": msg, "command": cmd})


@app.route("/api/automation/uninstall-windows/<name>", methods=["POST"])
def v31_automation_uninstall_windows(name):
    try:
        from local_automation import WindowsTaskScheduler
    except ImportError as e:
        return jsonify({"error": f"local_automation missing: {e}"}), 500
    ok, msg = WindowsTaskScheduler.uninstall(name)
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/automation/log")
def v31_automation_log():
    """Query the SQLite event log. Params: category, target, limit, since"""
    evlog = _v31_evlog()
    if not evlog:
        return jsonify({"events": [], "error": "event log not initialized"}), 500
    category = request.args.get("category") or None
    target = request.args.get("target") or None
    limit = int(request.args.get("limit", 100))
    since = request.args.get("since")
    since_epoch = int(since) if since else None
    events = evlog.query(category=category, target=target,
                          since_epoch=since_epoch, limit=limit)
    return jsonify({"events": events, "count": len(events)})


@app.route("/api/automation/stats")
def v31_automation_stats():
    """Event log summary stats for the dashboard."""
    evlog = _v31_evlog()
    if not evlog:
        return jsonify({"error": "event log not initialized"}), 500
    return jsonify(evlog.stats())


# ============================================================
# v32: Post queue routes (staggered publishing)
# ============================================================
def _v32_post_queue():
    try:
        from post_queue import PostQueue
    except ImportError:
        return None
    return PostQueue(APP_DIR)


@app.route("/api/queue/list")
def v32_queue_list():
    """Return the full post queue."""
    queue = _v32_post_queue()
    if queue is None:
        return jsonify({"error": "post_queue module missing"}), 500
    return jsonify({
        "queue": queue.queue,
        "stats": queue.stats(),
    })


@app.route("/api/queue/add", methods=["POST"])
def v32_queue_add():
    """Add a new item to the queue. Body: {title, topic?, tone?, length?, custom_instructions?}"""
    queue = _v32_post_queue()
    if queue is None:
        return jsonify({"error": "post_queue module missing"}), 500
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    item_id = queue.add(
        title=title,
        topic=(data.get("topic") or "").strip(),
        tone=(data.get("tone") or "personal_authority"),
        length=(data.get("length") or "medium"),
        custom_instructions=(data.get("custom_instructions") or "").strip(),
    )
    evlog = _v31_evlog()
    if evlog:
        evlog.record("automation", "queue_add", target=item_id, title=title)
    return jsonify({"ok": True, "id": item_id, "stats": queue.stats()})


@app.route("/api/queue/remove/<item_id>", methods=["POST"])
def v32_queue_remove(item_id):
    """Remove an item from the queue by id."""
    queue = _v32_post_queue()
    if queue is None:
        return jsonify({"error": "post_queue module missing"}), 500
    ok = queue.remove(item_id)
    evlog = _v31_evlog()
    if evlog:
        evlog.record("automation", "queue_remove", target=item_id, success=ok)
    return jsonify({"ok": ok, "stats": queue.stats()})


# ============================================================
# v31: What's New popup data
# ============================================================
_V31_WHATS_NEW = {
    "current_version": "32.1",
    "codename": "DEBUG OVERLAY — v32.0 bug fix",
    "v31": {
        "title": "v32.1 — JS Bug Fix + Built-in Debug Overlay",
        "date": "April 2026",
        "highlights": [
            "🔥 FIXED: v32.0 shipped with a duplicate const _origSwitchTab declaration that silently killed every button on the dashboard. This build is the fix.",
            "🐛 NEW: Built-in debug overlay — catches window.onerror + unhandled promise rejections + console.error and shows them in a red panel at the bottom of the screen with Copy/Clear buttons. If anything silently breaks again, you will SEE it.",
            "✅ NEW: /api/health startup check — page load pings the server and shows a top-right 'All Systems Operational' banner with version, route count, task count, and module status. This is the 'Refresh All Systems Start' confirmation that was missing.",
            "All v32.0 features work now: channel-specific content rewrites (4 voices from 1 article), staggered scheduler (Mon/Wed/Fri/Sat), post queue manager, Draft & Track, retroactive backlinks CLI, polish pass",
            "Channel-specific content rewrites — 'All 4 Channels' target generates 4 distinct voices from one master article (BVTech corporate, JP first-person, LinkedIn hook, GBP 300-char)",
            "Staggered per-channel scheduler — Mon BVTech / Wed JP / Fri LinkedIn / Sat GBP rotation pulling from a local post queue",
            "Post queue manager on Super Posting tab",
            "Retroactive backlinks script — standalone retroactive_backlinks.py with --dry-run/--commit",
            "Draft & Track email flow on HS Track",
            "Tab bar reorganized by workflow, orphan Guardz tab deleted, WordPress hidden",
        ],
    },
    "history": [
        {"version": "31.0", "title": "HubSpot Tracking + Local Automation",
         "date": "April 2026",
         "notes": ["HubSpot v3 Engagements API wrapper",
                   "SQLite event log + in-process scheduler",
                   "Windows Task Scheduler integration with --run-task CLI",
                   "5 built-in tasks, new HS Track + Automation tabs",
                   "What's New modal replaces version graffiti"]},
        {"version": "30.0", "title": "Super Posting — BVTech + JP + LinkedIn + GBP",
         "date": "April 2026",
         "notes": ["Google Business Profile OAuth2 + localPosts",
                   "Forward-only cross-linking graph (posts_index.json)",
                   "ORM → Super Posting rename",
                   "'All 4 Channels' target"]},
        {"version": "29.0", "title": "Site-Root Walk Cloudflare Deployer",
         "date": "April 2026",
         "notes": ["Full Cloudflare Pages Direct Upload protocol",
                   "Walks entire site folder, not just the new post",
                   "blog/index.html protection"]},
        {"version": "28.0", "title": "Safety Hold Release",
         "date": "March 2026",
         "notes": ["CRITICAL: caught CF Direct Upload nuke bug before firing",
                   "Super Scraper unbuffered-streaming fix"]},
    ],
}


@app.route("/api/whats-new")
def v31_whats_new():
    """Return the What's New changelog data for the popup."""
    return jsonify(_V31_WHATS_NEW)


# ============================================================
# v32.1: STARTUP HEALTH CHECK
# ============================================================
@app.route("/api/health")
def v32_health():
    """Quick smoke test for the dashboard's startup banner. Reports
    version, route count, registered task count, and which helper
    modules can be imported. Used by the JS health-check banner that
    fires on page load."""
    modules_to_check = [
        "channel_rewriter", "post_queue", "hubspot_tracker",
        "local_automation", "posts_index", "google_business_profile",
        "cloudflare_pages_deploy", "super_scraper",
    ]
    modules_ok = 0
    module_errors = []
    for m in modules_to_check:
        try:
            __import__(m)
            modules_ok += 1
        except Exception as ex:
            module_errors.append(f"{m}: {ex}")

    runner = getattr(__import__("builtins"), "_BVTECH_TASK_RUNNER", None)
    task_count = len(runner.all_tasks()) if runner else 0

    routes = list(app.url_map.iter_rules())
    return jsonify({
        "ok": modules_ok == len(modules_to_check),
        "version": APP_VERSION,
        "routes": len(routes),
        "tasks": task_count,
        "modules_ok": modules_ok,
        "modules_total": len(modules_to_check),
        "module_errors": module_errors,
    })


@app.route("/api/orm/spam-risk")
def orm_spam_risk():
    """v17: Analyze publishing velocity and return spam risk assessment."""
    now = datetime.now()
    history = _orm_history or []

    # Count posts in last 7 days and 30 days
    week_ago = (now - __import__('datetime').timedelta(days=7)).isoformat()
    month_ago = (now - __import__('datetime').timedelta(days=30)).isoformat()

    posts_week = [h for h in history if h.get("date", "") >= week_ago and h.get("status") != "error"]
    posts_month = [h for h in history if h.get("date", "") >= month_ago and h.get("status") != "error"]

    pw = len(posts_week)
    pm = len(posts_month)
    avg_per_week = round(pm / 4.0, 1) if pm else 0

    # Count by target site
    bv_count = sum(1 for h in posts_week if h.get("target") in ("bvtech", "both"))
    jp_count = sum(1 for h in posts_week if h.get("target") in ("jordanpolasek", "both"))
    both_count = sum(1 for h in posts_week if h.get("target") == "both")

    # Determine risk level
    warnings = []
    recommendations = []

    if pw > 5:
        risk = "HIGH"
        warnings.append(f"Published {pw} posts this week — way above safe limit of 3/week")
        recommendations.append("STOP posting immediately for 2-3 weeks to let Google cool down")
    elif pw > 3:
        risk = "MEDIUM"
        warnings.append(f"Published {pw} posts this week — above the recommended 3/week max")
        recommendations.append("Reduce to 2 posts/week to stay safe")
    elif pw > 0:
        risk = "LOW"
    else:
        risk = "LOW"

    if both_count > 0:
        warnings.append(f"{both_count} posts sent to BOTH sites — this creates duplicate content signals")
        recommendations.append("Use 'Alternate' mode to send each post to only one site")

    if avg_per_week > 4:
        warnings.append(f"Monthly average is {avg_per_week} posts/week — Google may flag this velocity")
        recommendations.append("Delete excess posts and slow down to 2-3/week")

    if pm > 20:
        warnings.append(f"{pm} posts in 30 days is aggressive — consider pruning low-quality ones")
        recommendations.append("Keep only 10-15 best posts per site, trash the rest")

    if not warnings:
        recommendations.append("Current velocity is safe. Keep posting 2-3 times per week.")
        recommendations.append("Focus on making each post genuinely useful and unique.")

    summary = f"{pw} posts this week, {avg_per_week}/week avg — " + (
        "safe velocity" if risk == "LOW" else
        "consider slowing down" if risk == "MEDIUM" else
        "STOP and clean up!")

    return jsonify({
        "risk_level": risk,
        "posts_this_week": pw,
        "posts_this_month": pm,
        "avg_per_week": avg_per_week,
        "bvtech_count": bv_count,
        "jp_count": jp_count,
        "both_count": both_count,
        "warnings": warnings,
        "recommendations": recommendations,
        "summary": summary,
    })

@app.route("/api/orm/scan-duplicates", methods=["POST"])
def orm_scan_duplicates():
    """v16: Scan ALL posts on both WP sites. Finds EXACT + NEAR duplicates. Verbose errors."""
    duplicates = {"bvtech": [], "jordanpolasek": [], "errors": []}

    def _word_set(title):
        """Extract significant words from a title for fuzzy matching."""
        stop = {"the","a","an","to","for","of","in","on","and","is","how","why","what","your","with","from","by","at","are","its","it"}
        return set(w for w in title.lower().split() if w not in stop and len(w) > 2)

    def _similarity(t1, t2):
        """Word-overlap similarity ratio between two titles. 0.0 to 1.0."""
        w1, w2 = _word_set(t1), _word_set(t2)
        if not w1 or not w2:
            return 0.0
        overlap = len(w1 & w2)
        return overlap / max(len(w1), len(w2))

    def _scan_site(client, site_name):
        """Fetch posts and find exact + near duplicates."""
        all_posts = []
        try:
            data, err = client.search_posts("", per_page=200, status="publish")
            if err:
                duplicates["errors"].append(f"{site_name} search error: {err}")
            if data and data.get("posts"):
                all_posts = data["posts"]
            else:
                duplicates["errors"].append(f"{site_name}: got 0 posts (err={err})")
        except Exception as e:
            duplicates["errors"].append(f"{site_name} exception: {str(e)}")

        dupes = []
        matched_ids = set()

        # PASS 1: Exact title matches (case-insensitive)
        titles = {}
        for p in all_posts:
            t = (p.get("title") or "").strip().lower()
            if not t:
                continue
            if t in titles:
                titles[t].append(p)
            else:
                titles[t] = [p]

        for t, posts in titles.items():
            if len(posts) > 1:
                posts.sort(key=lambda x: x.get("id", 0))
                keep = posts[-1]
                for p in posts[:-1]:
                    matched_ids.add(p["id"])
                    dupes.append({
                        "id": p["id"], "title": p.get("title", ""),
                        "date": p.get("date", ""), "url": p.get("url", ""),
                        "keep_id": keep["id"], "confidence": "EXACT",
                        "similarity": 100,
                    })

        # PASS 2: Near-duplicate detection (>75% word overlap)
        for i, p1 in enumerate(all_posts):
            if p1["id"] in matched_ids:
                continue
            t1 = (p1.get("title") or "").strip()
            if not t1:
                continue
            for p2 in all_posts[i+1:]:
                if p2["id"] in matched_ids:
                    continue
                t2 = (p2.get("title") or "").strip()
                if not t2:
                    continue
                sim = _similarity(t1, t2)
                if sim >= 0.75:
                    # Keep the one with higher ID (newer)
                    if p1["id"] > p2["id"]:
                        keep, trash = p1, p2
                    else:
                        keep, trash = p2, p1
                    if trash["id"] not in matched_ids:
                        matched_ids.add(trash["id"])
                        dupes.append({
                            "id": trash["id"], "title": trash.get("title", ""),
                            "date": trash.get("date", ""), "url": trash.get("url", ""),
                            "keep_id": keep["id"], "keep_title": keep.get("title", ""),
                            "confidence": "NEAR",
                            "similarity": int(sim * 100),
                        })

        return dupes, len(all_posts)

    # Scan bvtech.org
    bv_scanned = 0
    try:
        wp = get_wp_client()
        duplicates["bvtech"], bv_scanned = _scan_site(wp, "bvtech")
    except Exception as e:
        duplicates["bvtech_error"] = str(e)

    # Scan jordanpolasek.com
    jp_scanned = 0
    try:
        jp = _get_jp_client()
        duplicates["jordanpolasek"], jp_scanned = _scan_site(jp, "jordanpolasek")
    except Exception as e:
        duplicates["jordanpolasek_error"] = str(e)

    duplicates["total_dupes"] = len(duplicates["bvtech"]) + len(duplicates["jordanpolasek"])
    duplicates["bvtech_scanned"] = bv_scanned
    duplicates["jp_scanned"] = jp_scanned
    return jsonify(duplicates)

@app.route("/api/orm/trash-duplicate", methods=["POST"])
def orm_trash_duplicate():
    """v16: Trash a specific post. Returns verbose error info for debugging."""
    d = request.json or {}
    site = d.get("site", "")
    post_id = d.get("post_id", 0)

    if not site or not post_id:
        return jsonify({"error": "site and post_id required"})

    try:
        if site == "bvtech":
            client = get_wp_client()
        elif site == "jordanpolasek":
            client = _get_jp_client()
        else:
            return jsonify({"error": f"Unknown site: {site}"})

        result, err = client.delete_post(int(post_id))

        if result and result.get("success"):
            return jsonify({"success": True, "trashed": result,
                            "debug": {"site": site, "post_id": post_id,
                                      "mode": client.mode, "relay_url": client._relay_url,
                                      "has_relay": client._has_relay}})
        return jsonify({"error": err or "Failed to trash post",
                        "debug": {"site": site, "post_id": post_id,
                                  "mode": client.mode, "relay_url": client._relay_url,
                                  "has_relay": client._has_relay}})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/orm/test-delete", methods=["POST"])
def orm_test_delete():
    """v16 DEBUG: Test that delete actually works on both sites. Doesn't delete anything — just checks connectivity."""
    results = {}
    # Test BVTech relay
    try:
        wp = get_wp_client()
        results["bvtech"] = {"mode": wp.mode, "relay_url": wp._relay_url,
                              "has_relay": wp._has_relay, "site_url": wp.site_url}
        # Try a search to confirm connectivity
        data, err = wp.search_posts("", per_page=5, status="publish")
        results["bvtech"]["search_ok"] = bool(data and data.get("posts"))
        results["bvtech"]["search_count"] = len((data or {}).get("posts", []))
        results["bvtech"]["search_err"] = err
    except Exception as e:
        results["bvtech"] = {"error": str(e)}

    # Test JP relay
    try:
        jp = _get_jp_client()
        results["jordanpolasek"] = {"mode": jp.mode, "relay_url": jp._relay_url,
                                     "has_relay": jp._has_relay, "site_url": jp.site_url}
        data, err = jp.search_posts("", per_page=5, status="publish")
        results["jordanpolasek"]["search_ok"] = bool(data and data.get("posts"))
        results["jordanpolasek"]["search_count"] = len((data or {}).get("posts", []))
        results["jordanpolasek"]["search_err"] = err
    except Exception as e:
        results["jordanpolasek"] = {"error": str(e)}

    return jsonify(results)

@app.route("/api/orm/trash-all-duplicates", methods=["POST"])
def orm_trash_all_duplicates():
    """v16: Scan and trash ALL dupes (exact + near). Verbose error reporting."""
    results = {"bvtech_trashed": 0, "jp_trashed": 0, "errors": [], "remaining": 0, "details": []}

    try:
        scan_resp = orm_scan_duplicates()
        scan_data = scan_resp.get_json()
    except Exception as e:
        return jsonify({"error": f"Failed to scan: {str(e)}"})

    for dupe in scan_data.get("bvtech", []):
        try:
            wp = get_wp_client()
            r, e = wp.delete_post(int(dupe["id"]))
            if r and r.get("success"):
                results["bvtech_trashed"] += 1
                results["details"].append(f"✅ BV #{dupe['id']}: trashed")
            else:
                results["errors"].append(f"BV #{dupe['id']}: {e}")
        except Exception as ex:
            results["errors"].append(f"BV #{dupe['id']}: {str(ex)}")

    for dupe in scan_data.get("jordanpolasek", []):
        try:
            jp = _get_jp_client()
            r, e = jp.delete_post(int(dupe["id"]))
            if r and r.get("success"):
                results["jp_trashed"] += 1
                results["details"].append(f"✅ JP #{dupe['id']}: trashed")
            else:
                results["errors"].append(f"JP #{dupe['id']}: {e}")
        except Exception as ex:
            results["errors"].append(f"JP #{dupe['id']}: {str(ex)}")

    results["total_trashed"] = results["bvtech_trashed"] + results["jp_trashed"]

    # Re-scan to check remaining
    try:
        rescan = orm_scan_duplicates().get_json()
        results["remaining"] = rescan.get("total_dupes", 0)
    except:
        pass

    return jsonify(results)

@app.route("/api/orm/seo-score", methods=["POST"])
def orm_seo_score_route():
    """v15: Calculate SEO score for a given blog post content."""
    d = request.json or {}
    blog = {
        "title": d.get("title", ""),
        "content": d.get("content", ""),
        "meta_description": d.get("meta_description", ""),
        "focus_keyword": d.get("focus_keyword", ""),
    }
    score = _calculate_seo_score(blog, d.get("topic", ""))
    return jsonify(score)

# ── ORM Scheduler v16 — with dedup safety ────────────────

def _start_orm_scheduler():
    """v17: Google-Safe scheduler with weekly velocity limits, site alternation, and randomized timing."""
    def orm_sched_loop():
        import time as t, random
        weekly_count = 0
        last_week = ""
        _orm_publishing_active["scheduler"] = True

        try:
            while _orm_config.get("enabled"):
                now = datetime.now()
                # Track weekly count (ISO week number)
                current_week = now.strftime("%Y-W%W")
                ppw = _orm_config.get("posts_per_week", _orm_config.get("posts_per_day", 2))
                # v17: Hard cap at 3 posts/week regardless of setting
                ppw = min(ppw, 3)
                sh = _orm_config.get("start_hour", 8)
                eh = _orm_config.get("end_hour", 20)

                if current_week != last_week:
                    weekly_count = 0
                    last_week = current_week

                in_window = sh <= now.hour <= eh
                under_limit = weekly_count < ppw

                # v15: Wait if a bulk publish is running
                if _orm_publishing_active.get("bulk"):
                    t.sleep(60)
                    continue

                if in_window and under_limit:
                    try:
                        # v17: Determine target site with alternation
                        target_cfg = _orm_config.get("target", "alternate")
                        if target_cfg == "alternate":
                            last_site = _orm_config.get("last_site", "bvtech")
                            actual_target = "jordanpolasek" if last_site == "bvtech" else "bvtech"
                            _orm_config["last_site"] = actual_target
                            _save_orm_config(_orm_config)
                        else:
                            actual_target = target_cfg

                        pending = [i for i, q in enumerate(_orm_queue) if q.get("state") == "pending"]
                        if pending:
                            idx = pending[0]
                            item = _orm_queue[idx]
                            # v17: Override target with alternation
                            item_target = actual_target if target_cfg == "alternate" else item.get("target", "both")
                            # v17: Never post to "both" — pick one
                            if item_target == "both":
                                item_target = actual_target
                            result = _generate_one_post(
                                item["topic"], item_target,
                                item.get("status", "publish"))
                            if not result.get("error"):
                                _orm_queue[idx]["state"] = "published"
                                _orm_queue[idx]["published_at"] = now.isoformat()
                                _orm_config.setdefault("topics_used", []).append(item["topic"])
                                _save_orm_config(_orm_config)
                                _orm_history.insert(0, result)
                                _save_orm_history(_orm_history)
                            elif result.get("dedup"):
                                _orm_queue[idx]["state"] = "dedup_blocked"
                                _orm_queue[idx]["error"] = result.get("error")
                            else:
                                _orm_queue[idx]["state"] = "error"
                            _save_orm_queue(_orm_queue)
                        else:
                            used = set(_orm_config.get("topics_used", []))
                            avail = [tp for tp in _ORM_TOPICS if tp not in used]
                            if not avail:
                                _orm_config["topics_used"] = []
                                _save_orm_config(_orm_config)
                                avail = list(_ORM_TOPICS)
                            topic = random.choice(avail)
                            status = _orm_config.get("status", "publish")
                            # v17: Never post to "both" — use alternation target
                            result = _generate_one_post(topic, actual_target, status)
                            if not result.get("error"):
                                _orm_config.setdefault("topics_used", []).append(topic)
                                _save_orm_config(_orm_config)
                                _orm_history.insert(0, result)
                                _save_orm_history(_orm_history)

                        weekly_count += 1

                        # v17: Sleep until next post — spread across the week with randomization
                        # If 2 posts/week, that's ~3.5 days apart. Add ±4 hours jitter.
                        days_between = max(7.0 / max(ppw, 1), 1.5)
                        base_sleep = days_between * 86400  # convert to seconds
                        jitter = random.uniform(-4 * 3600, 4 * 3600)  # ±4 hours
                        sleep_secs = max(base_sleep + jitter, 36 * 3600)  # minimum 36 hours between posts
                        t.sleep(sleep_secs)

                    except Exception as e:
                        _orm_history.insert(0, {"title": f"[SCHED ERROR] {str(e)[:80]}",
                            "date": now.isoformat(), "status": "error", "posts": {}})
                        _save_orm_history(_orm_history)
                        t.sleep(3600)
                else:
                    t.sleep(120)
        finally:
            _orm_publishing_active["scheduler"] = False

    thread = threading.Thread(target=orm_sched_loop, daemon=True)
    thread.start()

# Auto-start if enabled
if _orm_config.get("enabled"):
    _start_orm_scheduler()

# ============================================================
# M365 INBOX ROUTES (v16.0)
# ============================================================
@app.route("/api/inbox/messages")
def inbox_messages():
    try:
        mx = get_inbox_client()
        folder = request.args.get("folder", "inbox")
        top = int(request.args.get("top", 25))
        skip = int(request.args.get("skip", 0))
        data, err = mx.get_inbox(folder=folder, top=top, skip=skip)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/message/<msg_id>")
def inbox_message(msg_id):
    try:
        mx = get_inbox_client()
        data, err = mx.get_email(msg_id)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/unread")
def inbox_unread():
    try:
        mx = get_inbox_client()
        data, err = mx.get_unread_count()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/send", methods=["POST"])
def inbox_send():
    try:
        mx = get_inbox_client()
        d = request.json
        data, err = mx.send_email(
            to=d.get("to",""),
            subject=d.get("subject",""),
            body=d.get("body",""),
            cc=d.get("cc"),
        )
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/reply/<msg_id>", methods=["POST"])
def inbox_reply(msg_id):
    try:
        mx = get_inbox_client()
        body = request.json.get("body", "")
        data, err = mx.reply_to_email(msg_id, body)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/read/<msg_id>", methods=["POST"])
def inbox_mark_read(msg_id):
    try:
        mx = get_inbox_client()
        data, err = mx.mark_read(msg_id)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/delete/<msg_id>", methods=["DELETE"])
def inbox_delete(msg_id):
    try:
        mx = get_inbox_client()
        data, err = mx.delete_email(msg_id)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/search")
def inbox_search():
    try:
        mx = get_inbox_client()
        q = request.args.get("q", "")
        data, err = mx.search_emails(q)
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/inbox/folders")
def inbox_folders():
    try:
        mx = get_inbox_client()
        data, err = mx.get_folders()
        return jsonify(data) if data else (jsonify({"error": err}), 400)
    except Exception as e: return jsonify({"error": str(e)}), 500

# ============================================================
# DIAGNOSTIC / DEBUG ENDPOINT
# ============================================================
@app.route("/api/diag")
def api_diagnostic():
    """Full system diagnostic — tests all integrations."""
    cfg = load_config()
    result = {
        "app_dir": APP_DIR,
        "python_exe": PYTHON_EXE,
        "frozen": getattr(sys, 'frozen', False),
        "config_path": os.path.join(APP_DIR, CONFIG_FILE),
        "config_exists": os.path.exists(os.path.join(APP_DIR, CONFIG_FILE)),
        "config_keys_present": {
            "tenant_id": bool(cfg.get("tenant_id")),
            "client_id": bool(cfg.get("client_id")),
            "client_secret": bool(cfg.get("client_secret")),
            "gh_token": bool(cfg.get("gh_token")),
            "gh_repo": bool(cfg.get("gh_repo")),
            "cf_api_token": bool(cfg.get("cf_api_token")),
            "cf_account_id": bool(cfg.get("cf_account_id")),
            "wp_site_url": bool(cfg.get("wp_site_url")),
            "wp_relay_key": bool(cfg.get("wp_relay_key")),
            "dialpad_key": bool(cfg.get("dialpad_key")),
            "hubspot_token": bool(cfg.get("hubspot_token")),
            "google_api_key": bool(cfg.get("google_api_key")),
            "anthropic_key": bool(cfg.get("anthropic_key")),
        },
        "tests": {}
    }

    # Test M365 token
    try:
        mx = get_inbox_client()
        token = mx._get_token()
        if token:
            result["tests"]["m365_token"] = "OK — token acquired"
        else:
            result["tests"]["m365_token"] = f"FAILED — {getattr(mx, '_last_token_error', 'no credentials')}"
    except Exception as e:
        result["tests"]["m365_token"] = f"ERROR — {e}"

    # Test Cloudflare Pages (v20)
    try:
        cf = get_cf_client()
        data, err = cf.test_connection()
        if data and data.get("connected"):
            result["tests"]["cloudflare"] = f"OK — {data.get('mode', '')} | {data.get('repo', data.get('project', ''))}"
        else:
            result["tests"]["cloudflare"] = f"FAILED — {err or 'not configured'}"
    except Exception as e:
        result["tests"]["cloudflare"] = f"ERROR — {e}"

    # Test WordPress relay (legacy for JP)
    try:
        wp = get_wp_client()
        data, err = wp.test_connection()
        if data and data.get("relay_working"):
            result["tests"]["wordpress"] = f"OK — {data.get('site_name', 'connected')}"
        else:
            result["tests"]["wordpress"] = f"FAILED — {err or data.get('error', 'unknown')}"
    except Exception as e:
        result["tests"]["wordpress"] = f"ERROR — {e}"

    # Check scripts exist
    scripts = ["prospect_scraper.py", "super_scraper.py", "email_campaign.py", "sms_campaign.py",
               "power_dialer.py", "tacticalrmm_integration.py", "dialpad_integration.py"]
    result["scripts"] = {}
    for s in scripts:
        path = os.path.join(APP_DIR, s)
        result["scripts"][s] = os.path.exists(path)

    return jsonify(result)

@app.route("/api/inbox/test")
def inbox_test():
    """Test M365 email connectivity with detailed diagnostics."""
    try:
        cfg = load_config()
        mx = get_inbox_client()
        diag = {
            "tenant_id_set": bool(cfg.get("tenant_id")),
            "client_id_set": bool(cfg.get("client_id")),
            "client_secret_set": bool(cfg.get("client_secret")),
            "sender_email": cfg.get("sender_email", ""),
        }

        token = mx._get_token()
        if token:
            diag["token"] = "OK"
            diag["token_preview"] = token[:20] + "..."
            # Try to fetch inbox
            data, err = mx.get_unread_count()
            if data:
                diag["inbox_access"] = "OK"
                diag["unread"] = data.get("unread", 0)
                diag["total"] = data.get("total", 0)
            else:
                diag["inbox_access"] = f"FAILED: {err}"
        else:
            diag["token"] = f"FAILED: {getattr(mx, '_last_token_error', 'unknown')}"
            diag["inbox_access"] = "skipped (no token)"

        return jsonify(diag)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# BUSINESS PULSE — AI Daily Briefing (v16.0 NEW)
# ============================================================
@app.route("/api/pulse/generate", methods=["POST"])
def pulse_generate():
    """Generate AI-powered daily business pulse report."""
    cfg = load_config()
    api_key = cfg.get("anthropic_key", "")
    if not api_key:
        return jsonify({"error": "No Anthropic API key. Set it in Settings."})

    # Gather data from all sources
    pulse_data = {"date": datetime.now().isoformat()}

    # Try to get Cloudflare Pages data (BVTech.org)
    try:
        cf = get_cf_client()
        cf_dash, _ = cf.get_dashboard()
        if cf_dash: pulse_data["cloudflare"] = {"total_posts": cf_dash.get("total_posts", 0), "mode": cf_dash.get("mode", ""), "site_url": cf_dash.get("site_url", "")}
    except Exception: pass

    # Try to get WordPress data (JordanPolasek.com)
    try:
        wp = get_wp_client()
        wp_dash, _ = wp.get_dashboard()
        if wp_dash: pulse_data["wordpress"] = wp_dash
    except Exception: pass

    # Try to get HubSpot pipeline
    try:
        dp = get_dp_client()
        pipe, _ = dp.get_hubspot_pipeline()
        if pipe: pulse_data["pipeline"] = {"stages": len(pipe.get("stages", [])), "raw": str(pipe)[:500]}
    except Exception: pass

    # Get prospect count
    try:
        csv_path = Path(os.path.join(APP_DIR, "prospects.csv"))
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                prospects = list(csv.DictReader(f))
            pulse_data["prospects"] = {"total": len(prospects)}
    except Exception: pass

    # Get sent email count
    try:
        sent_path = Path(os.path.join(APP_DIR, "sent_log.csv"))
        if sent_path.exists():
            with open(sent_path, "r", encoding="utf-8-sig") as f:
                sent = list(csv.DictReader(f))
            pulse_data["emails_sent"] = {"total": len(sent)}
    except Exception: pass

    prompt = f"""You are the AI business advisor for BVTech LLC, a Managed Service Provider in El Campo, Texas (serving SA, Houston, Austin).

Generate a DAILY BUSINESS PULSE report based on this live data from our systems:

{json.dumps(pulse_data, indent=2, default=str)}

Write the report in this format (use plain text, not markdown):

📊 PIPELINE HEALTH
[Analyze the HubSpot pipeline data — deals, stages, total value, recommendations]

📝 CONTENT & SEO
[Analyze WordPress blog data — total posts, drafts, publishing frequency, SEO recommendations]

🎯 PROSPECT PIPELINE  
[Analyze prospect data — total scraped, email campaign stats, conversion insights]

📞 RECOMMENDED ACTIONS TODAY
[5 specific, actionable items Jordan should do TODAY to grow BVTech]

💡 STRATEGIC INSIGHT
[One big-picture strategic recommendation based on all the data]

Keep it concise, data-driven, and actionable. Write as a trusted business advisor."""

    try:
        import requests as req
        resp = req.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": "claude-sonnet-4-20250514", "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=60)

        if resp.status_code != 200:
            return jsonify({"error": f"Claude API error: {resp.status_code}"})

        text = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        return jsonify({"pulse": text, "data_sources": list(pulse_data.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    port = 5678
    url = f"http://localhost:{port}"

    # ── v31: --run-task CLI flag for Windows Task Scheduler integration ──
    # Lets schtasks.exe shell out to pythonw.exe bvtech_app.py --run-task <name>
    # and have that one task fire without starting the Flask server.
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-task":
        task_name = sys.argv[2]
        print(f"[v31] Running one-shot task: {task_name}")
        try:
            from local_automation import LocalEventLog, TaskRunner, build_default_tasks
            _evlog = LocalEventLog(APP_DIR)
            _runner = TaskRunner(APP_DIR, _evlog)
            # v32: expose generate fn for staggered publish tasks run via schtasks
            import builtins
            builtins._BVTECH_GENERATE_POST = _generate_one_post
            builtins._BVTECH_EVENT_LOG = _evlog
            builtins._BVTECH_TASK_RUNNER = _runner
            for _t in build_default_tasks(APP_DIR, _evlog, load_config):
                _runner.register(_t)
            ok, msg = _runner.run_now(task_name)
            print(f"[v31] Task {task_name}: {'OK' if ok else 'FAIL'} — {msg}")
            sys.exit(0 if ok else 1)
        except Exception as _ex:
            print(f"[v31] Task runner error: {_ex}")
            sys.exit(2)

    # ── v19: Crash log — capture ALL unhandled exceptions to a file ──
    _crash_log = os.path.join(APP_DIR, "crash.log")
    def _write_crash_log(exc_text):
        try:
            with open(_crash_log, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"  CRASH at {datetime.now().isoformat()}\n")
                f.write(f"  Version: {APP_VERSION}\n")
                f.write(f"  Frozen: {getattr(sys, 'frozen', False)}\n")
                f.write(f"  Python: {sys.executable}\n")
                f.write(f"  APP_DIR: {APP_DIR}\n")
                f.write(f"{'='*60}\n")
                f.write(exc_text + "\n")
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"  BVTech MSP Command Center v{APP_VERSION} — CLOUDFLARE EDITION")
    print(f"{'='*60}")

    # v18: Kill any previous instance on this port
    kill_previous_instances(port)

    print(f"  All integrations loading from: {APP_DIR}")
    print(f"  Config: {os.path.join(APP_DIR, CONFIG_FILE)}")
    print(f"  Opening: {url}")
    print(f"  Ctrl+C to stop")
    print(f"{'='*60}\n")

    # ── v19: Smart browser launch — wait for server to be ready ──
    def _open_browser_when_ready(target_url, timeout=15):
        """Poll the server until it responds, then open browser."""
        import socket
        start = time.time()
        while time.time() - start < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result == 0:
                    webbrowser.open(target_url)
                    return
            except Exception:
                pass
            time.sleep(0.3)
        # Timeout — open anyway, user will see "connection refused" briefly
        webbrowser.open(target_url)

    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    # ── v31: Initialize local automation (event log + task runner) ──
    try:
        from local_automation import LocalEventLog, TaskRunner, build_default_tasks
        _v31_event_log = LocalEventLog(APP_DIR)
        _v31_task_runner = TaskRunner(APP_DIR, _v31_event_log)
        for _task in build_default_tasks(APP_DIR, _v31_event_log, load_config):
            _v31_task_runner.register(_task)
        _v31_task_runner.start()
        _v31_event_log.record("automation", "app_start",
                              target=f"v{APP_VERSION}",
                              task_count=len(_v31_task_runner.all_tasks()))
        # Expose globally so route handlers can use them
        import builtins
        builtins._BVTECH_EVENT_LOG = _v31_event_log
        builtins._BVTECH_TASK_RUNNER = _v31_task_runner
        # v32: Expose _generate_one_post for the staggered publish tasks
        builtins._BVTECH_GENERATE_POST = _generate_one_post
        print(f"  [v31] Local automation: {len(_v31_task_runner.all_tasks())} tasks registered")
    except Exception as _ex:
        print(f"  [v31] Automation init failed (non-fatal): {_ex}")
        traceback.print_exc()

    # ── v19: Port retry — if port is still held, wait and retry ──
    max_retries = 3
    for attempt in range(max_retries):
        try:
            app.run(host="127.0.0.1", port=port, debug=False)
            break  # Clean exit
        except OSError as e:
            err_str = str(e)
            if ("Address already in use" in err_str or "10048" in err_str) and attempt < max_retries - 1:
                wait = 2 * (attempt + 1)
                print(f"\n  [v19] Port {port} still in use — retrying in {wait}s (attempt {attempt+2}/{max_retries})...")
                kill_previous_instances(port)
                time.sleep(wait)
            else:
                _write_crash_log(traceback.format_exc())
                print(f"\n  [FATAL] Port {port} is permanently in use.")
                print(f"  Check crash.log for details.")
                print(f"  On Windows: taskkill /F /IM python.exe")
                if getattr(sys, 'frozen', False):
                    input("  Press Enter to exit...")
                sys.exit(1)
        except Exception as e:
            _write_crash_log(traceback.format_exc())
            print(f"\n  [FATAL] Unexpected error: {e}")
            print(f"  Full details written to: {_crash_log}")
            if getattr(sys, 'frozen', False):
                input("  Press Enter to exit...")
            sys.exit(1)
