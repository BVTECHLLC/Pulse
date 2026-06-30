#!/usr/bin/env python3
"""
BVTech v4.5 EXTREME — Unified Integration Module
===================================================
Tactical RMM (self-hosted, REST API) — replaces SuperOps
WordPress REST API — site/blog management via Application Passwords
Guardz Security — portal launcher + manual tracking
M365 Inbox — read/send/reply business emails

Auth methods:
  Tactical RMM: X-API-KEY header
  WordPress: Basic Auth with Application Passwords (user:app_password)
  M365: OAuth2 client credentials
"""

import json, os, sys, base64, requests
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_FILE = "bvtech_config.json"

def _get_app_dir():
    """Get the real app directory — works in dev AND PyInstaller EXE mode."""
    if getattr(sys, 'frozen', False):
        # PyInstaller EXE: config lives next to the .exe, NOT in the temp _MEIPASS dir
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__)) or "."

def _load_config():
    cfg_path = os.path.join(_get_app_dir(), CONFIG_FILE)
    if Path(cfg_path).exists():
        with open(cfg_path, "r") as f:
            return json.load(f)
    # Fallback: try CWD (covers edge cases)
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


# ╔══════════════════════════════════════════════════════════════╗
# ║  TACTICAL RMM — Self-Hosted RMM via REST API               ║
# ╚══════════════════════════════════════════════════════════════╝
class TacticalRMMClient:
    """REST API client for self-hosted Tactical RMM."""

    def __init__(self, api_url=None, api_key=None):
        cfg = _load_config()
        self.api_url = (api_url or cfg.get("trmm_api_url", "")).rstrip("/")
        self.api_key = api_key or cfg.get("trmm_api_key", "")

    def _headers(self):
        return {"Content-Type": "application/json", "X-API-KEY": self.api_key}

    def _get(self, path, params=None):
        if not self.api_url or not self.api_key:
            return None, "Tactical RMM API URL or key not configured"
        try:
            r = requests.get(f"{self.api_url}/{path}", headers=self._headers(), params=params, timeout=30)
            if r.status_code == 200:
                return r.json(), None
            return None, f"HTTP {r.status_code}: {r.text[:500]}"
        except Exception as e:
            return None, str(e)

    def _post(self, path, data=None):
        if not self.api_url or not self.api_key:
            return None, "Tactical RMM not configured"
        try:
            r = requests.post(f"{self.api_url}/{path}", headers=self._headers(), json=data or {}, timeout=30)
            if r.status_code in (200, 201):
                return r.json() if r.text else {"status": "ok"}, None
            return None, f"HTTP {r.status_code}: {r.text[:500]}"
        except Exception as e:
            return None, str(e)

    def _put(self, path, data=None):
        if not self.api_url or not self.api_key:
            return None, "Tactical RMM not configured"
        try:
            r = requests.put(f"{self.api_url}/{path}", headers=self._headers(), json=data or {}, timeout=30)
            if r.status_code == 200:
                return r.json() if r.text else {"status": "ok"}, None
            return None, f"HTTP {r.status_code}: {r.text[:500]}"
        except Exception as e:
            return None, str(e)

    def _patch(self, path, data=None):
        if not self.api_url or not self.api_key:
            return None, "Tactical RMM not configured"
        try:
            r = requests.patch(f"{self.api_url}/{path}", headers=self._headers(), json=data or {}, timeout=30)
            if r.status_code == 200:
                return r.json() if r.text else {"status": "ok"}, None
            return None, f"HTTP {r.status_code}: {r.text[:500]}"
        except Exception as e:
            return None, str(e)

    # ── Agents ───────────────────────────────────────────────
    def get_agents(self, detail=True):
        """List all agents. detail=false for lightweight list."""
        params = {} if detail else {"detail": "false"}
        return self._get("agents/", params)

    def get_agent(self, agent_id):
        """Get single agent details."""
        return self._get(f"agents/{agent_id}/")

    def get_agent_checks(self, agent_id):
        """Get checks for an agent."""
        return self._get(f"checks/{agent_id}/")

    def get_agent_tasks(self, agent_id):
        """Get automated tasks for an agent."""
        return self._get(f"agents/{agent_id}/tasks/")

    def run_command(self, agent_id, shell, cmd, timeout=30):
        """Run a command on an agent."""
        return self._post(f"agents/{agent_id}/cmd/", {
            "shell": shell, "cmd": cmd, "timeout": timeout
        })

    def run_script(self, agent_id, script_id, args=None, timeout=90):
        """Run a script on an agent."""
        return self._post(f"agents/{agent_id}/runscript/", {
            "output": "wait", "script": script_id,
            "args": args or [], "timeout": timeout,
            "run_as_user": False, "env_vars": [],
        })

    def reboot_agent(self, agent_id):
        """Reboot an agent's machine."""
        return self._post(f"agents/{agent_id}/reboot/")

    def send_wol(self, agent_id):
        """Send Wake-on-LAN."""
        return self._post(f"agents/{agent_id}/wol/")

    # ── Clients & Sites ──────────────────────────────────────
    def get_clients(self):
        """List all clients."""
        return self._get("clients/")

    def get_sites(self):
        """List all sites."""
        return self._get("sites/")

    def create_client(self, name):
        """Create a new client."""
        return self._post("clients/", {"client": {"name": name}})

    def create_site(self, name, client_id):
        """Create a new site under a client."""
        return self._post("sites/", {"site": {"client": client_id, "name": name}})

    # ── Alerts ───────────────────────────────────────────────
    def get_alerts(self, severity=None, resolved=None):
        """Get alerts. Optionally filter by severity/resolved status."""
        params = {}
        if severity: params["severity"] = severity
        if resolved is not None: params["resolved"] = str(resolved).lower()
        return self._get("alerts/", params)

    def resolve_alert(self, alert_id):
        """Resolve an alert."""
        return self._put(f"alerts/{alert_id}/resolve/")

    # ── Software ─────────────────────────────────────────────
    def get_software(self, agent_id):
        """Get installed software for an agent."""
        return self._get(f"software/{agent_id}/")

    def refresh_software(self, agent_id):
        """Trigger software inventory refresh."""
        return self._put(f"software/{agent_id}/")

    # ── Windows Updates ──────────────────────────────────────
    def scan_updates(self, agent_id):
        """Trigger a Windows Update scan."""
        return self._post(f"winupdate/{agent_id}/scan/")

    def get_updates(self, agent_id):
        """Get pending Windows Updates."""
        return self._get(f"winupdate/{agent_id}/")

    def install_updates(self, agent_id):
        """Install pending updates."""
        return self._post(f"winupdate/{agent_id}/install/")

    # ── Services ─────────────────────────────────────────────
    def get_services(self, agent_id):
        """Get services on an agent."""
        return self._get(f"services/{agent_id}/")

    def control_service(self, agent_id, service_name, action):
        """Control a service (start, stop, restart)."""
        return self._post(f"services/{agent_id}/{action}/", {"svc_name": service_name})

    # ── Scripts Library ──────────────────────────────────────
    def get_scripts(self):
        """List all scripts in the library."""
        return self._get("scripts/")

    # ── Event Logs ───────────────────────────────────────────
    def get_eventlog(self, agent_id, log_type="Application", days=1):
        """Get Windows event logs."""
        return self._post(f"agents/{agent_id}/eventlog/", {
            "logType": log_type, "days": str(days)
        })

    # ── Custom Fields ────────────────────────────────────────
    def get_custom_fields(self):
        """Get all custom fields definitions."""
        return self._get("core/customfields/")

    # ── Audit Logs ───────────────────────────────────────────
    def get_audit_logs(self, agent_id=None, action=None, page=1, per_page=50):
        """Get audit logs."""
        payload = {
            "pagination": {"sortBy": "entry_time", "descending": True,
                           "page": page, "rowsPerPage": per_page}
        }
        if agent_id: payload["agentFilter"] = [agent_id]
        if action: payload["actionFilter"] = [action]
        return self._patch("logs/audit/", payload)

    # ── Dashboard Summary ────────────────────────────────────
    def get_dashboard(self):
        """Build a dashboard summary from agents data."""
        agents, err = self.get_agents(detail=False)
        if err:
            return None, err
        total = len(agents) if isinstance(agents, list) else 0
        online = sum(1 for a in (agents or []) if a.get("status") == "online")
        offline = total - online
        # Try to get alert counts
        alerts, _ = self.get_alerts()
        alert_count = len(alerts) if isinstance(alerts, list) else 0
        clients, _ = self.get_clients()
        client_count = len(clients) if isinstance(clients, list) else 0
        return {
            "total_agents": total, "online": online, "offline": offline,
            "alerts": alert_count, "clients": client_count,
        }, None


# ╔══════════════════════════════════════════════════════════════╗
# ║  WORDPRESS — Dual Mode: REST API + PHP Relay Fallback      ║
# ╚══════════════════════════════════════════════════════════════╝
class WordPressClient:
    """WordPress client with two auth modes:
    
    Mode 1 (REST API): Uses WP Application Passwords (Basic Auth).
       - wp_user + wp_app_password in config
       - Works on most hosts. SiteGround may need .htaccess fix.
    
    Mode 2 (PHP Relay): Uses bvtech-api.php uploaded to the server.
       - wp_relay_key in config
       - Bypasses all auth header issues.
    
    The client auto-detects which mode to use based on config.
    """

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = _load_config()
        raw_url = cfg.get("wp_site_url", "").strip().rstrip("/")
        if raw_url and not raw_url.startswith("http"):
            raw_url = "https://" + raw_url
        self.site_url = raw_url
        
        # REST API mode
        self.wp_user = cfg.get("wp_user", "").strip()
        self.wp_app_password = cfg.get("wp_app_password", "").strip()
        self._rest_url = f"{self.site_url}/wp-json/wp/v2" if self.site_url else ""
        
        # Relay mode — v16: support custom relay filename
        self.relay_key = cfg.get("wp_relay_key", "").strip()
        relay_file = cfg.get("wp_relay_file", "bvtech-api.php").strip()
        self._relay_url = f"{self.site_url}/{relay_file}" if self.site_url else ""
        
        # Auto-detect mode
        if self.wp_user and self.wp_app_password:
            self.mode = "rest"
        elif self.relay_key:
            self.mode = "relay"
        else:
            self.mode = "none"
        
        # v16: Can we also use relay? (for operations like delete that may fail via REST)
        self._has_relay = bool(self.relay_key)

    # ── REST API helpers ─────────────────────────────────────
    def _rest_auth(self):
        """Basic Auth header for WP Application Passwords."""
        cred = base64.b64encode(f"{self.wp_user}:{self.wp_app_password}".encode()).decode()
        return {"Authorization": f"Basic {cred}", "Content-Type": "application/json"}

    def _safe_rest(self, method, url, **kwargs):
        """v19: Safe REST request — blocks redirects, detects WAF, sanitizes errors."""
        kwargs.setdefault("timeout", 20)
        kwargs.setdefault("allow_redirects", False)
        # v19: Merge auth headers with browser-like headers to bypass SiteGround WAF
        default_headers = self._rest_auth()
        default_headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        if "headers" in kwargs:
            default_headers.update(kwargs["headers"])
        kwargs["headers"] = default_headers
        try:
            r = requests.request(method, url, **kwargs)
            # Detect WAF redirects
            if r.status_code in (301, 302, 303, 307):
                loc = r.headers.get("Location", "")[:100]
                return None, f"Redirected by WAF ({r.status_code}) to {loc}. Use Relay mode."
            # Detect WAF blocks
            if r.status_code in (202, 403, 406, 503):
                return None, f"Blocked by firewall (HTTP {r.status_code}). Use Relay mode."
            # Check Content-Type is JSON
            ct = r.headers.get("Content-Type", "")
            if r.status_code in (200, 201) and "json" not in ct and "javascript" not in ct:
                return None, "Server returned HTML instead of JSON (WAF challenge). Use Relay mode."
            # Return raw response for caller to handle
            return r, None
        except requests.exceptions.ConnectionError:
            return None, f"Cannot connect to {url}"
        except requests.exceptions.Timeout:
            return None, "Request timed out"
        except Exception as e:
            return None, str(e)

    def _rest_get(self, path, params=None):
        if not self._rest_url:
            return None, "WordPress Site URL not set"
        r, err = self._safe_rest("GET", f"{self._rest_url}{path}", params=params)
        if err:
            return None, err
        if r.status_code == 200:
            try:
                return r.json(), None
            except Exception:
                return None, "REST returned non-JSON. WAF may be blocking. Use Relay mode."
        elif r.status_code == 401:
            return None, "REST API auth failed. Check wp_user and wp_app_password."
        err_text = r.text[:200].replace("<", "&lt;").replace(">", "&gt;") if r.text else ""
        return None, f"REST HTTP {r.status_code}: {err_text}"

    def _rest_post(self, path, data):
        if not self._rest_url:
            return None, "WordPress Site URL not set"
        r, err = self._safe_rest("POST", f"{self._rest_url}{path}", json=data)
        if err:
            return None, err
        if r.status_code in (200, 201):
            try:
                return r.json(), None
            except Exception:
                return None, "REST returned non-JSON. Use Relay mode."
        elif r.status_code == 401:
            return None, "REST API auth failed (401)"
        err_text = r.text[:200].replace("<", "&lt;").replace(">", "&gt;") if r.text else ""
        return None, f"REST HTTP {r.status_code}: {err_text}"

    # ── PHP Relay helpers ────────────────────────────────────
    def _relay_call(self, action, data=None, params=None):
        """Call the PHP relay script. v18: Always POST with JSON body to avoid SiteGround WAF
        blocking URLs with 'key' query params or long query strings."""
        if not self.site_url:
            return None, "WordPress Site URL is empty. Set it in Settings."
        if not self.relay_key:
            return None, "WordPress Relay Key is empty."

        import time as _time

        # v18: Minimal query params — just action + cache buster. Key goes in POST body.
        # SiteGround's sgcaptcha WAF intercepts requests with suspicious query strings
        # (especially ones containing 'key=', long params, or encoded HTML).
        query = {"action": action, "_": str(int(_time.time()))}

        # v19: Realistic browser headers — SiteGround's sgcaptcha blocks non-browser User-Agents
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Origin": self.site_url,
            "Referer": f"{self.site_url}/",
        }

        # Build POST body — always include key in body, never in URL
        post_body = {"key": self.relay_key}
        if data:
            post_body.update(data)
        if params:
            post_body["_params"] = params  # Pass extra params in body too

        try:
            # v19: POST with allow_redirects=False to prevent WAF redirect loops
            r = requests.post(self._relay_url, params=query, json=post_body,
                            timeout=30, headers=headers, allow_redirects=False)

            if r.status_code == 200:
                return r.json(), None
            elif r.status_code == 403:
                try:
                    err = r.json()
                    return None, f"Relay 403: {err.get('error', '')} {err.get('hint', '')} [received_len={err.get('debug_key_length_received','?')}, expected_len={err.get('debug_key_length_expected','?')}]"
                except Exception:
                    return None, f"Relay HTTP 403: Key rejected. The bvtech-api.php on the server has a different $SECRET_KEY than what you have in Settings."
            elif r.status_code == 404:
                return None, f"Relay HTTP 404: {self._relay_url.split('/')[-1]} not found at {self._relay_url}. Make sure you uploaded the PHP file to public_html/"
            elif r.status_code in (202, 406, 503):
                return None, f"Relay blocked by SiteGround WAF (HTTP {r.status_code}). Try: 1) Clear SiteGround cache, 2) Whitelist your IP in SiteGround Security → Blocked IPs, 3) Temporarily disable SG Security plugin"
            else:
                # Sanitize — never return raw HTML
                err_text = r.text[:200].replace("<","&lt;").replace(">","&gt;") if r.text else ""
                return None, f"Relay HTTP {r.status_code}: {err_text}"
        except requests.exceptions.ConnectionError:
            return None, f"Cannot connect to {self.site_url}"
        except requests.exceptions.Timeout:
            return None, "Request timed out"
        except Exception as e:
            return None, str(e)

    # ── Unified dispatcher ───────────────────────────────────
    def _call(self, action, data=None, params=None):
        """Route to REST API or Relay based on config. v19: auto-fallback to relay if REST fails."""
        if self.mode == "rest":
            result, err = self._rest_dispatch(action, data, params)
            if err and self._has_relay:
                # REST failed — try relay as fallback (SiteGround WAF, 202, 403, etc.)
                relay_result, relay_err = self._relay_call(action, data, params)
                if relay_result:
                    return relay_result, None
                # Both failed — return original REST error + relay error
                return None, f"REST failed: {err} | Relay also failed: {relay_err}"
            return result, err
        elif self.mode == "relay":
            return self._relay_call(action, data, params)
        else:
            return None, "WordPress not configured. Set either REST API credentials (wp_user + wp_app_password) or Relay key in Settings."

    def _rest_dispatch(self, action, data=None, params=None):
        """Map relay actions to REST API endpoints. v19: all calls use _safe_rest to prevent WAF breakout."""
        if action == "status":
            site_data, err = self._rest_get("/../")
            if err:
                # Try the root wp-json endpoint
                r, err2 = self._safe_rest("GET", f"{self.site_url}/wp-json/")
                if r and r.status_code == 200:
                    try:
                        d = r.json()
                        return {"status": "ok", "site_name": d.get("name", ""), "site_url": d.get("url", ""),
                                "wp_version": "", "relay_version": "REST-API"}, None
                    except Exception:
                        pass
                return None, err2 or err
            return site_data, None

        elif action == "dashboard":
            result = {}
            for key, endpoint, stp in [
                ("total_posts", "/posts", {"per_page": 1, "status": "publish"}),
                ("total_drafts", "/posts", {"per_page": 1, "status": "draft"}),
                ("total_pages", "/pages", {"per_page": 1}),
                ("total_comments", "/comments", {"per_page": 1}),
                ("total_users", "/users", {"per_page": 1}),
            ]:
                r, err = self._safe_rest("GET", f"{self._rest_url}{endpoint}", params=stp)
                result[key] = int(r.headers.get("X-WP-Total", 0)) if r and r.status_code == 200 else 0
            return result, None

        elif action == "list_posts":
            per_page = (params or {}).get("per_page", 20)
            page = (params or {}).get("page", 1)
            status = (params or {}).get("status", "any")
            rp = {"per_page": per_page, "page": page, "orderby": "date", "order": "desc", "context": "edit"}
            if status and status != "any":
                rp["status"] = status
            else:
                rp["status"] = "publish,draft,pending,private"
            r, err = self._safe_rest("GET", f"{self._rest_url}/posts", params=rp)
            if err:
                return None, err
            if r.status_code == 200:
                try:
                    posts = r.json()
                    return {"posts": [{"id": p["id"], "title": p.get("title",{}).get("rendered",""),
                                       "status": p["status"], "date": p["date"],
                                       "url": p.get("link",""),
                                       "excerpt": p.get("excerpt",{}).get("rendered","")[:200]}
                                      for p in posts],
                            "total": int(r.headers.get("X-WP-Total", 0)),
                            "pages": int(r.headers.get("X-WP-TotalPages", 0))}, None
                except Exception:
                    return None, "REST returned non-JSON. WAF may be blocking."
            err_text = r.text[:200].replace("<","&lt;").replace(">","&gt;") if r.text else ""
            return None, f"HTTP {r.status_code}: {err_text}"

        elif action == "get_post":
            post_id = (params or {}).get("id")
            return self._rest_get(f"/posts/{post_id}", {"context": "edit"})

        elif action == "create_post":
            post_data = {
                "title": (data or {}).get("title", ""),
                "content": (data or {}).get("content", ""),
                "status": (data or {}).get("status", "draft"),
            }
            result, err = self._rest_post("/posts", post_data)
            if result:
                return {"success": True, "post_id": result.get("id"),
                        "title": result.get("title",{}).get("rendered",""),
                        "status": result.get("status"), "url": result.get("link","")}, None
            return None, err

        elif action == "list_pages":
            r, err = self._safe_rest("GET", f"{self._rest_url}/pages",
                                     params={"per_page": 50, "orderby": "date", "order": "desc"})
            if err:
                return None, err
            if r.status_code == 200:
                try:
                    pages = r.json()
                    return {"pages": [{"id": p["id"], "title": p.get("title",{}).get("rendered",""),
                                       "status": p["status"], "date": p["date"], "url": p.get("link","")}
                                      for p in pages],
                            "total": int(r.headers.get("X-WP-Total", 0))}, None
                except Exception:
                    return None, "REST returned non-JSON. WAF blocking."
            return None, f"HTTP {r.status_code}"

        elif action == "categories":
            data, err = self._rest_get("/categories", {"per_page": 100})
            if data:
                return {"categories": [{"id": c["id"], "name": c["name"], "count": c["count"], "slug": c["slug"]} for c in data]}, None
            return None, err

        elif action == "delete_post":
            post_id = (data or {}).get("post_id")
            if not post_id:
                return None, "post_id required"
            r, err = self._safe_rest("DELETE", f"{self._rest_url}/posts/{post_id}")
            if err:
                return None, err
            if r.status_code == 200:
                try:
                    d = r.json()
                    return {"success": True, "post_id": post_id,
                            "title": d.get("title",{}).get("rendered",""), "action": "trashed"}, None
                except Exception:
                    return {"success": True, "post_id": post_id, "action": "trashed"}, None
            err_text = r.text[:200].replace("<","&lt;").replace(">","&gt;") if r.text else ""
            return None, f"HTTP {r.status_code}: {err_text}"

        elif action == "search_posts":
            rp = {"per_page": (params or {}).get("per_page", 100),
                  "orderby": "date", "order": "desc"}
            status = (params or {}).get("status", "any")
            if status and status != "any":
                rp["status"] = status
            else:
                rp["status"] = "publish,draft,pending,private"
            search = (params or {}).get("search", "")
            if search:
                rp["search"] = search
            try:
                r = requests.get(f"{self._rest_url}/posts", headers=self._rest_auth(),
                               params=rp, timeout=20)
                if r.status_code == 200:
                    posts = r.json()
                    return {"posts": [{"id": p["id"], "title": p.get("title",{}).get("rendered",""),
                                       "status": p["status"], "date": p["date"],
                                       "url": p.get("link","")} for p in posts],
                            "total": int(r.headers.get("X-WP-Total", 0))}, None
                return None, f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as e:
                return None, str(e)

        else:
            return None, f"Unknown REST action: {action}"

    # ── Test / Status ────────────────────────────────────────
    def test_connection(self):
        """Full diagnostic — tests both REST API and Relay."""
        result = {
            "relay_url_used": self._relay_url,
            "site_url": self.site_url,
            "mode": self.mode,
        }

        if self.mode == "rest":
            result["rest_user"] = self.wp_user
            result["rest_password_set"] = bool(self.wp_app_password)
            rest_ok = False
            # Test REST
            r, err = self._safe_rest("GET", f"{self.site_url}/wp-json/")
            if r and r.status_code == 200:
                try:
                    d = r.json()
                    result["api_reachable"] = True
                    result["site_name"] = d.get("name", "")
                    result["wp_version"] = ""
                except Exception:
                    result["api_reachable"] = False
                    result["api_error"] = "wp-json returned non-JSON (WAF)"
                    result["waf_likely"] = True
            elif err:
                result["api_reachable"] = False
                result["api_error"] = err
                if "WAF" in err or "Redirect" in err or "firewall" in err:
                    result["waf_likely"] = True
            elif r:
                result["api_reachable"] = False
                result["api_error"] = f"HTTP {r.status_code}"
                if r.status_code in (202, 403, 406, 503):
                    result["waf_likely"] = True
                    result["api_error"] += " (likely WAF — try Relay Mode)"

            # Test auth
            r2, err2 = self._safe_rest("GET", f"{self._rest_url}/users/me", params={"context": "edit"})
            if r2 and r2.status_code == 200:
                try:
                    user = r2.json()
                    rest_ok = True
                    result["auth_ok"] = True
                    result["relay_working"] = True
                    result["can_create_posts"] = True
                    result["user_id"] = user.get("id")
                    result["user_display_name"] = user.get("name", "")
                    # Get post count
                    pr, _ = self._safe_rest("GET", f"{self._rest_url}/posts", params={"per_page": 1})
                    if pr and pr.status_code == 200:
                        result["total_posts"] = int(pr.headers.get("X-WP-Total", 0))
                except Exception:
                    result["auth_ok"] = False
                    result["auth_error"] = "REST auth response was not valid JSON"
            else:
                result["auth_ok"] = False
                result["relay_working"] = False
                if err2:
                    result["auth_error"] = err2
                elif r2:
                    err_text = r2.text[:200].replace("<","&lt;").replace(">","&gt;") if r2.text else ""
                    result["auth_error"] = f"HTTP {r2.status_code}: {err_text}"
                    if r2.status_code == 401:
                        result["header_auth_stripped"] = True
                    if r2.status_code in (202, 403, 406, 503):
                        result["waf_likely"] = True

            # v19: If REST failed but we have a relay key, try relay as fallback
            if not rest_ok and self._has_relay:
                result["fallback_to_relay"] = True
                result["mode"] = "rest+relay_fallback"
                try:
                    import time as _time
                    ping_r = requests.get(self._relay_url, params={"action": "ping", "_": str(int(_time.time()))},
                                        headers={"Cache-Control": "no-cache", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Accept": "application/json, text/plain, */*"}, timeout=15)
                    if ping_r.status_code == 200:
                        try:
                            ping_data = ping_r.json()
                            result["relay_reachable"] = True
                            result["relay_version"] = ping_data.get("relay_version", "unknown")
                        except:
                            result["relay_reachable"] = True
                    else:
                        result["relay_reachable"] = False
                        result["relay_error"] = f"HTTP {ping_r.status_code}"
                except Exception as e:
                    result["relay_reachable"] = False
                    result["relay_error"] = str(e)

                # Test relay auth
                data, err = self._relay_call("status")
                if data:
                    result["relay_working"] = True
                    result["auth_ok"] = True
                    result["can_create_posts"] = True
                    result.update(data)
                    result["note"] = "REST API blocked (WAF/firewall) — using Relay mode successfully. Posts will work via relay."
                else:
                    result["relay_working"] = False
                    result["relay_error"] = err

        elif self.mode == "relay":
            result["key_length"] = len(self.relay_key) if self.relay_key else 0
            result["key_preview"] = (self.relay_key[:5] + "..." + self.relay_key[-3:]) if self.relay_key and len(self.relay_key) > 8 else self.relay_key

            # Ping (no auth)
            try:
                import time as _time
                ping_r = requests.get(self._relay_url, params={"action": "ping", "_": str(int(_time.time()))},
                                    headers={"Cache-Control": "no-cache", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Accept": "application/json, text/plain, */*"}, timeout=15)
                if ping_r.status_code == 200:
                    try:
                        ping_data = ping_r.json()
                        result["api_reachable"] = True
                        result["php_version"] = ping_data.get("php_version")
                        result["relay_version"] = ping_data.get("relay_version", "unknown")
                        result["wp_loaded"] = ping_data.get("wp_loaded")
                        result["server_key_length"] = ping_data.get("secret_key_length")
                        result["server_key_preview"] = ping_data.get("secret_key_preview")
                    except:
                        result["api_reachable"] = True
                        result["relay_version"] = "1.0 (old — re-upload bvtech-api.php from v10)"
                elif ping_r.status_code == 403:
                    result["api_reachable"] = True
                    result["relay_version"] = "1.0 (old — re-upload bvtech-api.php from v10)"
                else:
                    result["api_reachable"] = False
                    result["api_error"] = f"HTTP {ping_r.status_code}"
            except Exception as e:
                result["api_reachable"] = False
                result["api_error"] = str(e)
                result["relay_working"] = False
                result["auth_ok"] = False
                result["error"] = str(e)
                return result, None

            # Test auth
            data, err = self._relay_call("status")
            if data:
                result["relay_working"] = True
                result["auth_ok"] = True
                result["can_create_posts"] = True
                result.update(data)
            else:
                result["relay_working"] = False
                result["auth_ok"] = False
                result["error"] = err
                result["hint"] = "Re-upload bvtech-api.php from v10 zip. Make sure $SECRET_KEY in the PHP matches your Settings key exactly."

        else:
            result["relay_working"] = False
            result["auth_ok"] = False
            result["error"] = "WordPress not configured. Add REST API or Relay credentials in Settings."

        return result, None

    # ── Posts ────────────────────────────────────────────────
    def get_posts(self, per_page=20, page=1, status="any", search=None):
        data, err = self._call("list_posts", params={"per_page": per_page, "page": page, "status": status})
        if data:
            return {"items": data.get("posts", []), "total": data.get("total", 0), "pages": data.get("pages", 0)}, None
        return None, err

    def get_post(self, post_id):
        return self._call("get_post", params={"id": post_id})

    def create_post(self, title, content, status="draft", categories=None, author_name=None):
        post_data = {"title": title, "content": content, "status": status}
        if categories:
            post_data["categories"] = categories
        data, err = self._call("create_post", data=post_data)
        if data:
            # Normalize response — ensure 'id' and 'link' exist regardless of mode
            if "id" not in data and "post_id" in data:
                data["id"] = data["post_id"]
            if "link" not in data and "url" in data:
                data["link"] = data["url"]
        return data, err

    def update_post(self, post_id, **kwargs):
        kwargs["post_id"] = post_id
        return self._call("update_post", data=kwargs)

    def delete_post(self, post_id):
        """v16: Trash a post by ID. Tries relay first (more reliable), falls back to REST."""
        errors = []
        
        # Try relay first if available (bypasses SiteGround auth stripping)
        if self._has_relay:
            try:
                result, err = self._relay_call("delete_post", data={"post_id": int(post_id)})
                if result and result.get("success"):
                    return result, None
                if err:
                    errors.append(f"Relay: {err}")
            except Exception as e:
                errors.append(f"Relay exception: {str(e)}")
        
        # Try REST API
        if self.mode == "rest" or (self.wp_user and self.wp_app_password):
            try:
                r = requests.delete(f"{self._rest_url}/posts/{post_id}",
                                   headers=self._rest_auth(), timeout=20)
                if r.status_code == 200:
                    d = r.json()
                    return {"success": True, "post_id": post_id, "title": d.get("title",{}).get("rendered",""), "action": "trashed"}, None
                errors.append(f"REST HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                errors.append(f"REST exception: {str(e)}")
        
        return None, " | ".join(errors) if errors else "No delete method available"

    def search_posts(self, search="", per_page=200, status="any"):
        """v16: Search posts. Tries relay first (gets more results), falls back to REST."""
        # Try relay first if available (supports up to 500 results)
        if self._has_relay:
            try:
                result, err = self._relay_call("search_posts", params={
                    "search": search, "per_page": per_page, "status": status})
                if result and result.get("posts") is not None:
                    return result, None
            except:
                pass
        
        # Fall back to REST API (capped at 100 per page by WP)
        if self.mode == "rest" or (self.wp_user and self.wp_app_password):
            try:
                params = {"per_page": min(per_page, 100), "orderby": "date", "order": "desc"}
                if status and status != "any":
                    params["status"] = status
                else:
                    params["status"] = "publish,draft,pending,private"
                if search:
                    params["search"] = search
                r = requests.get(f"{self._rest_url}/posts", headers=self._rest_auth(),
                               params=params, timeout=20)
                if r.status_code == 200:
                    posts = r.json()
                    return {"posts": [{"id": p["id"], "title": p.get("title",{}).get("rendered",""),
                                       "status": p["status"], "date": p["date"],
                                       "url": p.get("link","")} for p in posts],
                            "total": int(r.headers.get("X-WP-Total", 0))}, None
                return None, f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as e:
                return None, str(e)
        
        return None, "No search method available"

    def get_all_titles(self, per_page=100, status="publish"):
        """Get all post titles from the site. Returns set of lowercase titles."""
        titles = set()
        try:
            data, err = self.search_posts("", per_page=per_page, status=status)
            if data and data.get("posts"):
                for p in data["posts"]:
                    t = (p.get("title") or "").strip().lower()
                    if t:
                        titles.add(t)
        except:
            pass
        return titles

    # ── Pages ────────────────────────────────────────────────
    def get_pages(self, per_page=20, page=1, status="any"):
        data, err = self._call("list_pages")
        if data:
            return {"items": data.get("pages", []), "total": data.get("total", 0)}, None
        return None, err

    def create_page(self, title, content, status="draft"):
        return self._call("create_post", data={"title": title, "content": content, "status": status, "post_type": "page"})

    # ── Users ────────────────────────────────────────────────
    def get_users(self):
        if self.mode == "rest":
            data, err = self._rest_get("/users", {"per_page": 10})
            if data:
                return {"items": [{"id": u["id"], "login": u.get("slug",""), "display_name": u.get("name","")} for u in data]}, None
            return None, err
        data, err = self._call("status")
        if data:
            return {"items": data.get("admin_users", [])}, None
        return None, err

    def get_me(self):
        if self.mode == "rest":
            return self._rest_get("/users/me")
        data, err = self._call("status")
        if data and data.get("admin_users"):
            return data["admin_users"][0], None
        return None, err

    def get_author_id(self):
        me, err = self.get_me()
        if me:
            return me.get("id")
        return None

    # ── Comments ─────────────────────────────────────────────
    def get_comments(self, per_page=20, status="approve"):
        if self.mode == "rest":
            data, err = self._rest_get("/comments", {"per_page": per_page})
            if data:
                return {"items": data, "total": len(data)}, None
            return None, err
        data, err = self._call("dashboard")
        if data:
            return {"items": [], "total": data.get("total_comments", 0)}, None
        return None, err

    # ── Categories ───────────────────────────────────────────
    def get_categories(self):
        return self._call("categories")

    # ── Site Info ────────────────────────────────────────────
    def get_site_info(self):
        return self._call("status")

    # ── Dashboard ────────────────────────────────────────────
    def get_dashboard(self):
        data, err = self._call("dashboard")
        if data:
            return {
                "total_posts": data.get("total_posts", 0),
                "total_pages": data.get("total_pages", 0),
                "total_comments": data.get("total_comments", 0),
                "total_users": data.get("total_users", 0),
                "total_drafts": data.get("total_drafts", 0),
            }, None
        return None, err


# ╔══════════════════════════════════════════════════════════════╗
# ║  GUARDZ SECURITY — Portal Launcher + Manual Tracker         ║
# ╚══════════════════════════════════════════════════════════════╝
class GuardzPortal:
    """Guardz doesn't have a public API. This provides portal links
    and a local tracking file for manual security posture notes."""

    TRACKER_FILE = "guardz_tracker.json"

    def __init__(self):
        cfg = _load_config()
        self.portal_url = cfg.get("guardz_portal_url", "https://app.guardz.com")
        self.app_dir = _get_app_dir()

    def get_portal_url(self):
        return self.portal_url

    def _tracker_path(self):
        return os.path.join(self.app_dir, self.TRACKER_FILE)

    def get_tracker(self):
        """Get local security tracker entries."""
        path = self._tracker_path()
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f), None
        return {"incidents": [], "posture_score": None, "last_updated": None}, None

    def save_tracker(self, data):
        """Save security tracker data."""
        data["last_updated"] = datetime.now().isoformat()
        with open(self._tracker_path(), "w") as f:
            json.dump(data, f, indent=2)
        return data, None

    def add_incident(self, severity, title, description, client=""):
        """Add a manual security incident."""
        tracker, _ = self.get_tracker()
        tracker["incidents"].insert(0, {
            "id": len(tracker["incidents"]) + 1,
            "severity": severity, "title": title,
            "description": description, "client": client,
            "status": "open", "created": datetime.now().isoformat(),
        })
        return self.save_tracker(tracker)

    def resolve_incident(self, incident_id):
        """Mark an incident as resolved."""
        tracker, _ = self.get_tracker()
        for inc in tracker["incidents"]:
            if inc["id"] == incident_id:
                inc["status"] = "resolved"
                inc["resolved_at"] = datetime.now().isoformat()
                break
        return self.save_tracker(tracker)

    def update_posture_score(self, score):
        """Update the overall security posture score (0-100)."""
        tracker, _ = self.get_tracker()
        tracker["posture_score"] = max(0, min(100, int(score)))
        return self.save_tracker(tracker)


# ╔══════════════════════════════════════════════════════════════╗
# ║  M365 INBOX — Microsoft Graph API Email Client              ║
# ╚══════════════════════════════════════════════════════════════╝
class M365InboxClient:
    """M365 Graph API for reading and sending regular emails."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = _load_config()
        self.tenant_id = cfg.get("tenant_id", "")
        self.client_id = cfg.get("client_id", "")
        self.client_secret = cfg.get("client_secret", "")
        self.sender_email = cfg.get("sender_email", "help@bvtech.org")
        self._token = None
        self._token_expires = None

    def _get_token(self):
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token
        if not all([self.tenant_id, self.client_id, self.client_secret]):
            return None
        try:
            r = requests.post(
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
                data={"grant_type": "client_credentials", "client_id": self.client_id,
                      "client_secret": self.client_secret,
                      "scope": "https://graph.microsoft.com/.default"}, timeout=15)
            if r.status_code == 200:
                d = r.json()
                self._token = d["access_token"]
                self._token_expires = datetime.now() + timedelta(seconds=d.get("expires_in", 3600) - 60)
                return self._token
            else:
                # Store error for debugging
                self._last_token_error = f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as e:
            self._last_token_error = str(e)
        return None

    def _headers(self):
        token = self._get_token()
        if not token:
            return None
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _get(self, path, params=None):
        h = self._headers()
        if not h:
            err = getattr(self, '_last_token_error', 'M365 credentials not configured or token fetch failed')
            return None, f"Auth failed: {err}"
        try:
            r = requests.get(f"{self.GRAPH_URL}{path}", headers=h, params=params, timeout=30)
            return (r.json(), None) if r.status_code == 200 else (None, f"HTTP {r.status_code}: {r.text[:500]}")
        except Exception as e:
            return None, str(e)

    def _post(self, path, data):
        h = self._headers()
        if not h:
            err = getattr(self, '_last_token_error', 'M365 credentials not configured or token fetch failed')
            return None, f"Auth failed: {err}"
        try:
            r = requests.post(f"{self.GRAPH_URL}{path}", headers=h, json=data, timeout=30)
            return (r.json() if r.text else {"status": "ok"}, None) if r.status_code in (200, 201, 202) else (None, f"HTTP {r.status_code}: {r.text[:500]}")
        except Exception as e:
            return None, str(e)

    def get_inbox(self, folder="inbox", top=25, skip=0, search=None):
        params = {"$top": top, "$skip": skip, "$orderby": "receivedDateTime desc",
                  "$select": "id,subject,from,toRecipients,receivedDateTime,isRead,importance,hasAttachments,bodyPreview"}
        if search: params["$search"] = f'"{search}"'
        return self._get(f"/users/{self.sender_email}/mailFolders/{folder}/messages", params)

    def get_email(self, message_id):
        return self._get(f"/users/{self.sender_email}/messages/{message_id}",
                         {"$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,importance,hasAttachments,body,bodyPreview"})

    def send_email(self, to, subject, body, cc=None, is_html=True):
        msg = {"message": {"subject": subject,
               "body": {"contentType": "HTML" if is_html else "Text", "content": body},
               "toRecipients": [{"emailAddress": {"address": a.strip()}} for a in to.split(",")]},
               "saveToSentItems": True}
        if cc: msg["message"]["ccRecipients"] = [{"emailAddress": {"address": a.strip()}} for a in cc.split(",")]
        return self._post(f"/users/{self.sender_email}/sendMail", msg)

    def reply_to_email(self, message_id, body, is_html=True):
        return self._post(f"/users/{self.sender_email}/messages/{message_id}/reply",
                          {"message": {"body": {"contentType": "HTML" if is_html else "Text", "content": body}}})

    def mark_read(self, message_id, is_read=True):
        h = self._headers()
        if not h: return None, "Auth failed"
        try:
            r = requests.patch(f"{self.GRAPH_URL}/users/{self.sender_email}/messages/{message_id}",
                               headers=h, json={"isRead": is_read}, timeout=15)
            return ({"status": "ok"}, None) if r.status_code == 200 else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            return None, str(e)

    def delete_email(self, message_id):
        h = self._headers()
        if not h: return None, "Auth failed"
        try:
            r = requests.delete(f"{self.GRAPH_URL}/users/{self.sender_email}/messages/{message_id}",
                                headers=h, timeout=15)
            return ({"status": "deleted"}, None) if r.status_code == 204 else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            return None, str(e)

    def get_unread_count(self):
        data, err = self._get(f"/users/{self.sender_email}/mailFolders/inbox",
                              {"$select": "unreadItemCount,totalItemCount"})
        if data: return {"unread": data.get("unreadItemCount", 0), "total": data.get("totalItemCount", 0)}, None
        return None, err

    def search_emails(self, query, top=25):
        return self._get(f"/users/{self.sender_email}/messages",
                         {"$search": f'"{query}"', "$top": top,
                          "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview"})


# ============================================================
# CLOUDFLARE PAGES CLIENT — v20 NEW
# Deploy static HTML blog posts to Cloudflare Pages via GitHub API
# BVTech.org is a static site on Cloudflare Pages (not WordPress)
# ============================================================

class CloudflarePagesClient:
    """Manages BVTech.org static site deployed on Cloudflare Pages.
    
    Two deployment modes:
      Mode 1 (Cloudflare Direct Upload API): Uses CF API token + account ID + project name.
         - Pushes files directly to Cloudflare Pages via Direct Upload.
      Mode 2 (GitHub API → Cloudflare auto-deploy): Pushes HTML files to GitHub repo,
         Cloudflare Pages auto-deploys from the repo.
    
    v20: Full blog management — create, list, delete posts as static HTML files.
    """

    BLOG_DIR = "blog"

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = _load_config()
        # Cloudflare Direct Upload config
        self.cf_api_token = cfg.get("cf_api_token", "").strip()
        self.cf_account_id = cfg.get("cf_account_id", "").strip()
        self.cf_project_name = cfg.get("cf_project_name", "bvtech-site").strip()
        # GitHub config (for Git-based deploy)
        self.gh_token = cfg.get("gh_token", "").strip()
        self.gh_repo = cfg.get("gh_repo", "").strip()  # e.g. "username/bvtech-site"
        self.gh_branch = cfg.get("gh_branch", "main").strip()
        # Site URL
        self.site_url = cfg.get("cf_site_url", "https://bvtech.org").strip().rstrip("/")
        # v23: Detect which site this client is for (BVTech vs JP)
        self.is_jp = "jordanpolasek" in self.site_url.lower() or "jordanpolasek" in self.cf_project_name.lower()
        self.site_name = "JordanPolasek.com" if self.is_jp else "BVTech.org"
        # Detect mode
        if self.cf_api_token and self.cf_account_id:
            self.mode = "cloudflare_direct"
        elif self.gh_token and self.gh_repo:
            self.mode = "github"
        else:
            self.mode = "none"

    # ── GitHub API Helpers ────────────────────────────────────
    def _gh_headers(self):
        return {
            "Authorization": f"token {self.gh_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "BVTech-MSP-v20",
        }

    def _gh_api(self, method, path, json_data=None, timeout=30):
        url = f"https://api.github.com/repos/{self.gh_repo}{path}"
        try:
            r = requests.request(method, url, headers=self._gh_headers(),
                                json=json_data, timeout=timeout)
            if r.status_code in (200, 201):
                return r.json(), None
            elif r.status_code == 404:
                return None, None  # File not found (expected for new files)
            else:
                return None, f"GitHub API {r.status_code}: {r.text[:300]}"
        except Exception as e:
            return None, str(e)

    def _gh_get_file(self, file_path):
        """Get a file from GitHub repo (returns content + sha for updates)."""
        return self._gh_api("GET", f"/contents/{file_path}?ref={self.gh_branch}")

    def _gh_put_file(self, file_path, content_b64, message, sha=None):
        """Create or update a file in GitHub repo."""
        data = {
            "message": message,
            "content": content_b64,
            "branch": self.gh_branch,
        }
        if sha:
            data["sha"] = sha
        return self._gh_api("PUT", f"/contents/{file_path}", json_data=data)

    def _gh_delete_file(self, file_path, sha, message):
        """Delete a file from GitHub repo."""
        data = {
            "message": message,
            "sha": sha,
            "branch": self.gh_branch,
        }
        return self._gh_api("DELETE", f"/contents/{file_path}", json_data=data)

    # ── Cloudflare Direct Upload Helpers ─────────────────────
    def _cf_headers(self):
        return {
            "Authorization": f"Bearer {self.cf_api_token}",
        }

    def _cf_create_deployment(self, files_dict):
        """Create a Cloudflare Pages deployment with direct upload.
        files_dict: {path: content_bytes, ...}
        """
        import io
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/pages/projects/{self.cf_project_name}/deployments"
        
        # Build multipart form with manifest + files
        manifest = {}
        file_tuples = []
        for i, (path, content) in enumerate(files_dict.items()):
            file_key = f"file_{i}"
            manifest[f"/{path}"] = file_key
            if isinstance(content, str):
                content = content.encode("utf-8")
            file_tuples.append((file_key, (path, io.BytesIO(content), "application/octet-stream")))
        
        import json
        file_tuples.insert(0, ("manifest", (None, json.dumps(manifest), "application/json")))
        
        try:
            r = requests.post(url, headers=self._cf_headers(), files=file_tuples, timeout=120)
            if r.status_code in (200, 201):
                data = r.json()
                return data.get("result", {}), None
            return None, f"CF API {r.status_code}: {r.text[:300]}"
        except Exception as e:
            return None, str(e)

    # ── Blog Template Engine ─────────────────────────────────
    def _build_blog_html(self, title, content, meta_description="", slug="",
                          focus_keyword="", date_published=None, schema_markup=""):
        """Generate a full static HTML blog post matching the BVTech.org design system.
        Produces a complete standalone page with proper SEO, schema, and styling."""
        import html as html_mod
        from datetime import datetime as dt
        
        date_pub = date_published or dt.now().strftime("%Y-%m-%d")
        date_mod = dt.now().strftime("%Y-%m-%d")
        
        safe_title = html_mod.escape(title)
        safe_meta = html_mod.escape(meta_description[:160]) if meta_description else safe_title[:160]
        canonical_slug = slug or self._slugify(title)
        canonical_url = f"{self.site_url}/blog/{canonical_slug}/"
        
        # Schema markup
        blog_schema = f'''{{"@context": "https://schema.org", "@type": "BlogPosting", "headline": "{html_mod.escape(title, quote=True)}", "author": {{"@type": "Person", "name": "Jordan Polasek", "url": "https://jordanpolasek.com", "@id": "https://bvtech.org/#founder"}}, "publisher": {{"@type": "Organization", "name": "BVTech LLC", "url": "https://bvtech.org", "@id": "https://bvtech.org/#org", "logo": {{"@type": "ImageObject", "url": "https://bvtech.org/assets/img/logo.png"}}}}, "url": "{canonical_url}", "mainEntityOfPage": "{canonical_url}", "datePublished": "{date_pub}", "dateModified": "{date_mod}", "image": "https://bvtech.org/assets/img/og-image.png", "inLanguage": "en"}}'''
        
        breadcrumb_schema = f'''{{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{{"@type": "ListItem", "position": 1, "name": "Home", "item": "https://bvtech.org/"}}, {{"@type": "ListItem", "position": 2, "name": "Blog", "item": "https://bvtech.org/blog/"}}, {{"@type": "ListItem", "position": 3, "name": "{html_mod.escape(title, quote=True)}"}}]}}'''

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Language" content="en">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.ico" type="image/x-icon">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/img/favicon-32x32.png">
<link rel="apple-touch-icon" sizes="180x180" href="/assets/img/favicon-180x180.png">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/img/favicon-192x192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/assets/img/favicon-512x512.png">
<title>{safe_title} — BVTech LLC | Managed IT Services Texas</title>
<meta name="description" content="{safe_meta}">
<meta name="author" content="Jordan Polasek">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical_url}">
<meta name="geo.region" content="US-TX">
<meta property="og:type" content="article">
<meta property="og:title" content="{safe_title} — BVTech LLC">
<meta property="og:description" content="{safe_meta}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:site_name" content="BVTech LLC">
<meta property="og:image" content="https://bvtech.org/assets/img/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@bvtechllc">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@300;400;700;900&family=Poppins:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{blog_schema}</script>
{schema_markup or ""}
<style>*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0E0D2C;--bg2:#13123A;--bg3:#1A1950;--accent:#4440DB;--accent2:#5B57E8;--green:#26C485;--gold:#F5BE58;--white:#fff;--text:rgba(255,255,255,.88);--muted:rgba(255,255,255,.5);--border:rgba(255,255,255,.07);--card:rgba(255,255,255,.035);--max-w:1160px;--fh:'Poppins',sans-serif;--fb:'Lato',sans-serif;--r:10px}}
html{{font-size:16px;scroll-behavior:smooth;-webkit-font-smoothing:antialiased}}
body{{font-family:var(--fb);color:var(--text);line-height:1.7;background:var(--bg)}}
img{{max-width:100%;height:auto;display:block}}
a{{color:var(--accent2);text-decoration:none;transition:color .2s}}a:hover{{color:var(--white)}}
h1,h2,h3,h4{{font-family:var(--fh);color:var(--white);line-height:1.25;font-weight:700}}
.ctr{{max-width:var(--max-w);margin:0 auto;padding:0 24px}}
.header{{position:fixed;top:0;left:0;right:0;z-index:1000;background:rgba(14,13,44,.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border)}}
.header-inner{{max-width:var(--max-w);margin:0 auto;padding:0 24px;display:flex;align-items:center;justify-content:space-between;height:72px;gap:16px}}
.header-logo{{display:flex;align-items:center;flex-shrink:0}}.header-logo img{{height:34px;width:auto}}
.header-nav{{display:flex;gap:24px;align-items:center;list-style:none;flex-shrink:0}}
.header-nav a{{color:var(--muted);font-size:.85rem;font-weight:500;white-space:nowrap}}.header-nav a:hover,.header-nav a.active{{color:var(--white)}}
.header-contact{{display:flex;align-items:center;gap:16px;flex-shrink:0}}
.header-phone{{color:var(--white);font-weight:700;font-size:.85rem;white-space:nowrap;display:flex;align-items:center;gap:6px}}.header-phone:hover{{color:var(--green)}}
.header-email{{color:var(--muted);font-size:.8rem;white-space:nowrap;display:flex;align-items:center;gap:5px}}.header-email:hover{{color:var(--white)}}
.header-cta{{background:var(--accent);color:var(--white)!important;padding:9px 20px;border-radius:50px;font-weight:700;font-size:.8rem;letter-spacing:.03em;white-space:nowrap;transition:.2s}}.header-cta:hover{{background:var(--accent2)}}
.header-divider{{width:1px;height:24px;background:var(--border);flex-shrink:0}}
.nav-toggle{{display:none;background:none;border:none;cursor:pointer;padding:8px}}.nav-toggle span{{display:block;width:22px;height:2px;background:var(--white);margin:5px 0}}
.btn-p{{display:inline-flex;align-items:center;gap:8px;background:var(--accent);color:var(--white);padding:15px 32px;border-radius:50px;font-weight:700;font-size:.95rem;transition:.2s;border:none;cursor:pointer}}.btn-p:hover{{background:var(--accent2);transform:translateY(-2px);box-shadow:0 8px 28px rgba(68,64,219,.35);color:var(--white)}}
.page-hero{{padding:140px 0 60px;background:linear-gradient(160deg,#0E0D2C 0%,#1A1950 50%,#0E0D2C 100%);text-align:center;position:relative}}
.page-hero .breadcrumb{{margin-bottom:16px;font-size:.8rem;color:var(--muted)}}.page-hero .breadcrumb a{{color:var(--accent2)}}
.article-body{{max-width:760px;margin:0 auto;padding:60px 24px 100px}}
.article-body h1{{font-size:clamp(1.8rem,3.5vw,2.4rem);margin-bottom:16px}}
.article-body .meta{{color:var(--accent2);font-size:.85rem;margin-bottom:32px}}
.article-body p{{margin-bottom:20px;line-height:1.9;color:var(--text)}}
.article-body h2{{font-size:1.4rem;margin:40px 0 16px}}
.article-body h3{{font-size:1.15rem;margin:32px 0 12px}}
.article-body a{{color:var(--accent2);text-decoration:underline}}
.article-body ul,.article-body ol{{margin:0 0 20px 24px;line-height:1.9}}
.article-body li{{margin-bottom:8px}}
.article-body blockquote{{border-left:3px solid var(--accent);padding:12px 20px;margin:24px 0;background:var(--card);border-radius:0 var(--r) var(--r) 0}}
.article-body strong{{color:var(--white)}}
.article-body .faq-item{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;margin-bottom:12px}}
.article-body .faq-item h3{{margin:0 0 8px;font-size:1rem}}
.fl{{list-style:none}}.fl li{{margin-bottom:9px}}.fl a{{color:var(--muted);font-size:.85rem}}.fl a:hover{{color:var(--accent2)}}
.fg{{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:44px;margin-bottom:44px}}
.footer{{padding:60px 0 32px;background:var(--bg);border-top:1px solid var(--border)}}
.footer p{{color:var(--muted);font-size:.84rem;margin-top:14px;line-height:1.75}}
.footer h4{{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:rgba(255,255,255,.35);margin-bottom:16px;font-weight:600}}
.fb{{display:flex;justify-content:space-between;align-items:center;padding-top:28px;border-top:1px solid var(--border);font-size:.78rem;color:rgba(255,255,255,.3)}}
@media(max-width:860px){{.header-nav{{display:none}}.nav-toggle{{display:block}}.header-contact .header-email,.header-divider{{display:none}}.fg{{grid-template-columns:1fr 1fr}}}}
@media(max-width:640px){{.fg{{grid-template-columns:1fr}}.fb{{flex-direction:column;gap:8px;text-align:center}}.header-contact .header-cta{{display:none}}}}</style>
</head>
<body>
<header class="header"><div class="header-inner">
<a href="/" class="header-logo"><img src="/assets/img/logo-header.png" alt="BVTech LLC" width="200" height="28"></a>
<ul class="header-nav">
<li><a href="/about/">About</a></li>
<li><a href="/services/">Services</a></li>
<li><a href="/industries/">Industries</a></li>
<li><a href="/blog/" class="active">Blog</a></li>
<li><a href="/contact/">Contact</a></li>
</ul>
<div class="header-contact">
<a href="tel:+12105383669" class="header-phone">&#128222; (210) 538-3669</a>
<div class="header-divider"></div>
<a href="mailto:help@bvtech.org" class="header-email">&#9993; help@bvtech.org</a>
<a href="/contact/" class="header-cta">Free Consultation</a>
</div>
<button class="nav-toggle" aria-label="Menu"><span></span><span></span><span></span></button>
</div></header>

<section class="page-hero" style="padding-bottom:40px"><div class="ctr">
<div class="breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/blog/">Blog</a> &rsaquo; Article</div>
</div></section>

<article class="article-body">
<h1>{safe_title}</h1>
<div class="meta">By <a href="https://jordanpolasek.com" target="_blank" rel="noopener">Jordan Polasek</a> &middot; Founder, BVTech LLC &middot; <a href="https://www.linkedin.com/in/jordanbvtech/" target="_blank" rel="noopener">LinkedIn</a></div>
{content}

<div style="margin-top:48px;padding-top:32px;border-top:1px solid var(--border)">
<h3 style="margin-bottom:16px">{"Ready to Level Up Your IT?" if self.is_jp else "Need IT Help?"}</h3>
<p style="color:var(--muted);margin-bottom:16px">{"Jordan Polasek is an experienced IT consultant and MSP expert helping businesses modernize their technology." if self.is_jp else "BVTech LLC provides managed IT services, cybersecurity, and cloud solutions for small businesses across Texas."}</p>
<a href="/{"about-jordan-polasek" if self.is_jp else "contact"}/" class="btn-p">{"Learn More About Jordan" if self.is_jp else "Schedule Free Consultation"} &rarr;</a>
</div>
</article>

<section style="padding:60px 0;border-top:1px solid var(--border)"><div class="ctr">
<p style="font-size:.7rem;text-transform:uppercase;letter-spacing:.15em;color:var(--green);font-weight:700;margin-bottom:10px">Related Resources</p>
<h2 style="font-family:var(--fh);color:var(--white);font-size:1.6rem;margin-bottom:24px">Explore More from BVTech</h2>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px">
<a href="/blog/" style="display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;transition:.2s;text-decoration:none"><span style="color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700">Blog</span><span style="display:block;color:var(--white);font-family:var(--fh);font-weight:600;font-size:.92rem;margin-top:6px">All Blog Posts</span></a>
<a href="/services/" style="display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;transition:.2s;text-decoration:none"><span style="color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700">Services</span><span style="display:block;color:var(--white);font-family:var(--fh);font-weight:600;font-size:.92rem;margin-top:6px">Our IT Solutions</span></a>
<a href="/contact/" style="display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;transition:.2s;text-decoration:none"><span style="color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700">Contact</span><span style="display:block;color:var(--white);font-family:var(--fh);font-weight:600;font-size:.92rem;margin-top:6px">Get a Free Consultation</span></a>
<a href="/san-antonio/" style="display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;transition:.2s;text-decoration:none"><span style="color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700">Service Areas</span><span style="display:block;color:var(--white);font-family:var(--fh);font-weight:600;font-size:.92rem;margin-top:6px">IT Services: San Antonio</span></a>
<a href="/houston/" style="display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;transition:.2s;text-decoration:none"><span style="color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700">Service Areas</span><span style="display:block;color:var(--white);font-family:var(--fh);font-weight:600;font-size:.92rem;margin-top:6px">IT Services: Houston</span></a>
</div>
</div></section>

<footer class="footer"><div class="ctr">
<div class="fg">
<div>
<img src="/assets/img/logo-footer.png" alt="BVTech LLC" width="240" height="34" loading="lazy" style="opacity:.85">
<p>BVTech LLC is an award-winning managed service provider established in 2013. Enterprise-grade IT solutions for small businesses across Texas.</p>
<p style="margin-top:10px;font-size:.84rem"><a href="tel:+12105383669" style="color:var(--green);font-weight:700">Call (210) 538-3669</a><br><a href="mailto:help@bvtech.org" style="color:var(--accent2)">help@bvtech.org</a><br><span style="color:var(--muted)">Houston &middot; San Antonio &middot; Austin, Texas</span></p>
</div>
<div><h4>Services</h4><ul class="fl">
<li><a href="/services/managed-it-services.html">Managed IT Services</a></li>
<li><a href="/services/cybersecurity-solutions.html">Cybersecurity Solutions</a></li>
<li><a href="/services/cloud-solutions-microsoft-365.html">Cloud &amp; Microsoft 365</a></li>
<li><a href="/services/data-backup-disaster-recovery.html">Data Backup &amp; Recovery</a></li>
<li><a href="/services/network-infrastructure-cabling.html">Network &amp; Cabling</a></li>
<li><a href="/services/voip-business-phone-systems.html">VoIP Phone Systems</a></li>
</ul></div>
<div><h4>Company</h4><ul class="fl">
<li><a href="/about/">About BVTech</a></li>
<li><a href="/services/">Services</a></li>
<li><a href="/pricing/">Pricing</a></li>
<li><a href="/blog/">Blog</a></li>
<li><a href="/contact/">Contact</a></li>
</ul></div>
<div><h4>Connect</h4><ul class="fl"><li><a href="https://www.linkedin.com/in/jordanbvtech/" target="_blank" rel="noopener">Jordan Polasek on LinkedIn</a></li><li><a href="https://www.linkedin.com/company/bvtech-llc" target="_blank" rel="noopener">BVTech LLC Company Page</a></li><li><a href="https://jordanpolasek.com" target="_blank" rel="noopener">Visit JordanPolasek.com</a></li></ul></div>
</div>
<div style="text-align:center;padding:20px 0 0;margin-top:20px;border-top:1px solid var(--border)">
<span style="font-size:1.4rem">&#127482;&#127480;</span>
<span style="color:rgba(255,255,255,.35);font-size:.75rem;margin-left:8px;vertical-align:middle">Proudly American-Made &middot; Veteran-Friendly &middot; Faith-Driven</span>
</div>
<div class="fb"><span>&copy; BVTech LLC 2013&ndash;2026. All Rights Reserved.</span><span><a href="https://www.linkedin.com/in/jordanbvtech/" target="_blank" rel="noopener">Follow Us on LinkedIn</a> &middot; <a href="https://jordanpolasek.com" target="_blank" rel="noopener">About the Founder</a></span></div>
<div style="text-align:center;padding:28px 0 10px;border-top:1px solid rgba(255,255,255,.06)">
<a href="#" style="display:inline-block;margin-bottom:16px;padding:8px 20px;border:1px solid rgba(255,255,255,.15);border-radius:50px;color:var(--muted);font-size:.8rem;text-decoration:none" aria-label="Back to top">&uarr; Back to Top</a>
<p style="color:rgba(255,255,255,.3);font-size:.78rem;font-style:italic;max-width:520px;margin:0 auto;line-height:1.6">"Whatever you do, work at it with all your heart, as working for the Lord." &mdash; Colossians 3:23</p>
</div>
</div></footer>
<script>
const nt=document.querySelector('.nav-toggle'),nl=document.querySelector('.header-nav');
if(nt)nt.addEventListener('click',()=>{{const s=nl.style.display==='flex';nl.style.display=s?'none':'flex';if(!s){{nl.style.flexDirection='column';nl.style.position='absolute';nl.style.top='72px';nl.style.left='0';nl.style.right='0';nl.style.background='rgba(14,13,44,.98)';nl.style.padding='24px';nl.style.gap='16px';nl.style.borderBottom='1px solid rgba(255,255,255,.07)'}}}});
</script>
</body></html>'''

    def _slugify(self, text):
        """Convert title to URL-safe slug."""
        import re
        slug = text.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')
        return slug[:80]

    # ── Public API: Create News Post (BVTech News — Vulnerability Reports) ──
    def create_news_post(self, title, content, meta_description="",
                          focus_keyword="", schema_markup="", severity="CRITICAL",
                          cve_ids=None, image_url="", image_alt=""):
        """Create a BVTech News vulnerability report as static HTML under /news/.
        Returns (result_dict, error_string)."""
        slug = self._slugify(title)
        file_path = f"news/{slug}.html"
        html = self._build_news_html(title, content, meta_description, slug,
                                      focus_keyword, schema_markup=schema_markup,
                                      severity=severity, cve_ids=cve_ids or [],
                                      image_url=image_url, image_alt=image_alt)

        if self.mode == "github":
            return self._deploy_news_github(file_path, html, title, slug)
        elif self.mode == "cloudflare_direct":
            return self._deploy_news_cf_direct(file_path, html, title, slug)
        else:
            return None, "No deployment method configured."

    def _deploy_news_github(self, file_path, html_content, title, slug):
        """Deploy news article via GitHub API."""
        import base64
        content_b64 = base64.b64encode(html_content.encode("utf-8")).decode("ascii")
        existing, _ = self._gh_get_file(file_path)
        sha = existing.get("sha") if existing else None
        msg = f"Add BVTech News: {title}" if not sha else f"Update BVTech News: {title}"
        result, err = self._gh_put_file(file_path, content_b64, msg, sha=sha)
        if err:
            return None, f"GitHub deploy failed: {err}"
        post_url = f"{self.site_url}/news/{slug}/"
        return {
            "success": True, "id": slug, "post_id": slug, "title": title,
            "slug": slug, "link": post_url, "url": post_url,
            "deploy_mode": "github", "file_path": file_path,
            "sha": result.get("content", {}).get("sha", ""),
            "status": "published", "section": "news",
        }, None

    def _deploy_news_cf_direct(self, file_path, html_content, title, slug):
        """Deploy news article via Cloudflare Direct Upload."""
        result, err = self._cf_create_deployment({file_path: html_content})
        if err:
            return None, f"Cloudflare deploy failed: {err}"
        post_url = f"{self.site_url}/news/{slug}/"
        return {
            "success": True, "id": slug, "post_id": slug, "title": title,
            "slug": slug, "link": post_url, "url": post_url,
            "deploy_mode": "cloudflare_direct",
            "deployment_id": result.get("id", ""), "status": "published", "section": "news",
        }, None

    def list_news_posts(self, per_page=50):
        """List BVTech News articles from the repo."""
        if self.mode == "github":
            data, err = self._gh_api("GET", f"/contents/news?ref={self.gh_branch}")
            if err:
                return None, err
            if not data:
                return {"posts": [], "total": 0}, None
            posts = []
            for f in data:
                if f.get("name", "").endswith(".html") and f["name"] != "index.html":
                    slug = f["name"].replace(".html", "")
                    posts.append({
                        "id": slug,
                        "title": slug.replace("-", " ").title(),
                        "slug": slug,
                        "url": f"{self.site_url}/news/{slug}/",
                        "file_path": f["path"],
                        "sha": f.get("sha", ""),
                        "size": f.get("size", 0),
                        "status": "published",
                    })
            return {"posts": posts[:per_page], "total": len(posts)}, None
        return {"posts": [], "total": 0, "note": "Use GitHub mode for full news management"}, None

    def _build_news_html(self, title, content, meta_description="", slug="",
                          focus_keyword="", date_published=None, schema_markup="",
                          severity="CRITICAL", cve_ids=None, image_url="", image_alt=""):
        """Generate a full static HTML BVTech News vulnerability report page."""
        import html as html_mod
        from datetime import datetime as dt

        date_pub = date_published or dt.now().strftime("%Y-%m-%d")
        date_display = dt.now().strftime("%B %d, %Y")
        date_mod = dt.now().strftime("%Y-%m-%d")

        safe_title = html_mod.escape(title)
        safe_meta = html_mod.escape(meta_description[:160]) if meta_description else safe_title[:160]
        canonical_slug = slug or self._slugify(title)
        canonical_url = f"{self.site_url}/news/{canonical_slug}/"

        sev_color = "#ef4444" if severity in ("CRITICAL","HIGH") else "#f59e0b" if severity == "MEDIUM" else "#22c55e"
        sev_label = severity.upper()

        cve_tags = ""
        if cve_ids:
            cve_tags = " ".join([f'<span style="display:inline-block;background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);padding:2px 10px;border-radius:4px;font-size:12px;font-weight:700;font-family:monospace">{html_mod.escape(c)}</span>' for c in cve_ids[:8]])

        img_block = ""
        if image_url:
            safe_alt = html_mod.escape(image_alt or f"{title} - Jordan Polasek - BVTech News")
            img_block = f'<div style="margin:0 0 32px;border-radius:12px;overflow:hidden;border:1px solid var(--border)"><img src="{html_mod.escape(image_url)}" alt="{safe_alt}" width="760" height="400" style="width:100%;height:auto;object-fit:cover" loading="eager"></div>'

        news_schema = f'{{"@context":"https://schema.org","@type":"NewsArticle","headline":"{html_mod.escape(title,quote=True)}","author":{{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"}},"publisher":{{"@type":"Organization","name":"BVTech LLC","url":"https://bvtech.org","logo":{{"@type":"ImageObject","url":"https://bvtech.org/assets/img/logo.png"}}}},"url":"{canonical_url}","mainEntityOfPage":"{canonical_url}","datePublished":"{date_pub}","dateModified":"{date_mod}","image":"{image_url or "https://bvtech.org/assets/img/og-image.png"}","inLanguage":"en","articleSection":"Cybersecurity News","keywords":"{html_mod.escape(focus_keyword or "cybersecurity vulnerability")}"}}'

        breadcrumb_schema = f'{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Home","item":"https://bvtech.org/"}},{{"@type":"ListItem","position":2,"name":"BVTech News","item":"https://bvtech.org/news/"}},{{"@type":"ListItem","position":3,"name":"{html_mod.escape(title,quote=True)}"}}]}}'

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title} — BVTech News | BVTech LLC</title>
<meta name="description" content="{safe_meta}">
<meta name="author" content="Jordan Polasek">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical_url}">
<meta name="geo.region" content="US-TX">
<meta property="og:type" content="article">
<meta property="og:title" content="{safe_title} — BVTech News">
<meta property="og:description" content="{safe_meta}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:site_name" content="BVTech LLC">
<meta property="og:image" content="{image_url or "https://bvtech.org/assets/img/og-image.png"}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,300..700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/css/style.css">
<link rel="icon" type="image/png" href="/favicon.png">
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{news_schema}</script>
{schema_markup or ""}
<style>
.news-severity{{display:inline-block;padding:4px 14px;border-radius:6px;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;background:rgba(239,68,68,0.12);color:{sev_color};border:1px solid {sev_color}40}}
.news-cve-tags{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 24px}}
.news-article{{max-width:800px;margin:0 auto;padding:40px 24px 80px}}
.news-article h1{{font-family:'Plus Jakarta Sans',sans-serif;font-size:clamp(1.6rem,3.5vw,2.2rem);margin-bottom:12px;line-height:1.2}}
.news-article .meta{{color:var(--text-muted,rgba(255,255,255,0.5));font-size:14px;margin-bottom:24px;display:flex;flex-wrap:wrap;align-items:center;gap:12px}}
.news-article p{{margin-bottom:18px;line-height:1.85}}
.news-article h2{{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.35rem;margin:36px 0 14px}}
.news-article h3{{font-size:1.1rem;margin:28px 0 10px}}
.news-article ul,.news-article ol{{margin:0 0 18px 24px;line-height:1.85}}
.news-article li{{margin-bottom:6px}}
.news-article blockquote{{border-left:3px solid var(--accent,#6366f1);padding:12px 20px;margin:24px 0;background:rgba(255,255,255,0.03);border-radius:0 8px 8px 0}}
.news-cta{{background:linear-gradient(135deg,rgba(239,68,68,0.08),rgba(124,58,237,0.08));border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:32px;margin:40px 0;text-align:center}}
.news-cta h3{{margin:0 0 12px;font-size:1.2rem}}
.news-cta p{{color:var(--text-muted,rgba(255,255,255,0.6));margin:0 0 20px}}
.news-cta .btn{{display:inline-block;background:linear-gradient(135deg,#ef4444,#7c3aed);color:#fff;padding:14px 32px;border-radius:50px;font-weight:700;font-size:15px;text-decoration:none;transition:0.2s}}.news-cta .btn:hover{{transform:translateY(-2px);box-shadow:0 8px 28px rgba(124,58,237,0.3)}}
</style>
</head>
<body>
<a href="#main-content" class="skip-link">Skip to content</a>
<nav class="nav" role="navigation" aria-label="Main navigation">
<div class="nav-inner">
<a href="https://bvtech.org/" class="nav-logo" aria-label="BVTech LLC — Return to homepage">
<img src="https://bvtech.org/assets/img/logo-header.png" alt="BVTech LLC" width="160" height="38">
</a>
<ul class="nav-links" id="navLinks">
<li><a href="https://bvtech.org/about/">About</a></li>
<li><a href="https://bvtech.org/services/">Services</a></li>
<li><a href="https://bvtech.org/industries/">Industries</a></li>
<li><a href="https://bvtech.org/news/" class="active">&#128240; News</a></li>
<li><a href="https://bvtech.org/blog/">Blog</a></li>
<li><a href="https://bvtech.org/contact/">Contact</a></li>
</ul>
<div class="nav-right">
<div class="nav-contact"><a href="tel:+12105383669">&#128222; (210) 538-3669</a> <a href="mailto:help@bvtech.org">&#9993; help@bvtech.org</a></div>
<a href="https://bvtech.org/contact/" class="btn-primary">Free Consultation</a>
<button class="nav-hamburger" id="navToggle" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>
</div>
</div>
</nav>
<main id="main-content">
<section class="page-hero" style="background:linear-gradient(135deg,rgba(239,68,68,0.06),rgba(124,58,237,0.04))"><div class="container">
<p class="bread"><a href="https://bvtech.org/">Home</a> &rsaquo; <a href="https://bvtech.org/news/">&#128240; BVTech News</a> &rsaquo; Article</p>
<h1 style="font-size:clamp(20px,3vw,28px)">{safe_title}</h1>
</div></section>
<article class="news-article">
{img_block}
<div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-bottom:8px">
<span class="news-severity">{sev_label} SEVERITY</span>
<span style="font-size:13px;color:var(--text-muted,rgba(255,255,255,0.5))">{date_display}</span>
</div>
{f'<div class="news-cve-tags">{cve_tags}</div>' if cve_tags else ''}
<div class="meta">By <a href="https://jordanpolasek.com" target="_blank" rel="noopener" style="font-weight:600">Jordan Polasek</a> &middot; Founder &amp; Managing Partner, <a href="https://bvtech.org">BVTech LLC</a></div>

{content}

<div class="news-cta">
<h3>&#128737;&#65039; Is Your Business Protected?</h3>
<p>BVTech LLC provides 24/7 cybersecurity monitoring, vulnerability management, and incident response for Texas businesses. Don't wait until you're the next headline.</p>
<a href="https://bvtech.org/contact/" class="btn">Schedule Free Security Assessment &rarr;</a>
<div style="margin-top:16px;font-size:13px;color:var(--text-muted,rgba(255,255,255,0.5))">
&#128222; <a href="tel:+12105383669" style="color:inherit;font-weight:600">(210) 538-3669</a> &middot;
&#9993; <a href="mailto:help@bvtech.org" style="color:inherit">help@bvtech.org</a>
</div>
</div>
</article>
</main>
<section class="cta" aria-labelledby="cta-h"><div class="container">
<h2 id="cta-h">Ready to Secure Your Business?</h2>
<p class="cta-desc">Get a free IT consultation with Jordan Polasek and discover how BVTech can protect your business from the latest threats.</p>
<div class="cta-btns"><a href="https://bvtech.org/contact/" class="btn-primary btn-w">Get Your Free IT Assessment &rarr;</a> <a href="tel:+12105383669" class="btn-outline-w btn-g">&#128222; Call Now</a></div>
</div></section>
<footer class="footer" role="contentinfo"><div class="container">
<div class="ft-bottom"><span>&copy; 2013&ndash;2026 BVTech LLC. All rights reserved.</span></div>
<div class="ft-verse">"Whatever you do, work at it with all your heart, as working for the Lord." &mdash; Colossians 3:23</div>
</div></footer>
<script>
const n=document.querySelector('.nav');window.addEventListener('scroll',()=>n.classList.toggle('scrolled',window.scrollY>20));
const t=document.getElementById('navToggle'),l=document.getElementById('navLinks');
if(t)t.addEventListener('click',()=>{{l.classList.toggle('open');t.setAttribute('aria-expanded',l.classList.contains('open'))}});
</script>
</body></html>'''

    # ── Public API: Create Blog Post ─────────────────────────
    def create_post(self, title, content, status="publish", meta_description="",
                     focus_keyword="", schema_markup=""):
        """Create a blog post as a static HTML file and deploy it.
        Returns (result_dict, error_string)."""
        slug = self._slugify(title)
        file_path = f"blog/{slug}.html"
        html = self._build_blog_html(title, content, meta_description, slug,
                                      focus_keyword, schema_markup=schema_markup)

        if self.mode == "github":
            return self._deploy_github(file_path, html, title, slug)
        elif self.mode == "cloudflare_direct":
            return self._deploy_cf_direct(file_path, html, title, slug)
        else:
            return None, "No deployment method configured. Set GitHub token + repo OR Cloudflare API token in Settings."

    def _deploy_github(self, file_path, html_content, title, slug):
        """Deploy via GitHub API (Cloudflare Pages auto-deploys from repo)."""
        import base64
        content_b64 = base64.b64encode(html_content.encode("utf-8")).decode("ascii")

        # Check if file already exists (for update)
        existing, _ = self._gh_get_file(file_path)
        sha = existing.get("sha") if existing else None

        msg = f"Add blog post: {title}" if not sha else f"Update blog post: {title}"
        result, err = self._gh_put_file(file_path, content_b64, msg, sha=sha)

        if err:
            return None, f"GitHub deploy failed: {err}"

        post_url = f"{self.site_url}/blog/{slug}/"
        return {
            "success": True,
            "id": slug,
            "post_id": slug,
            "title": title,
            "slug": slug,
            "link": post_url,
            "url": post_url,
            "deploy_mode": "github",
            "file_path": file_path,
            "sha": result.get("content", {}).get("sha", ""),
            "status": "published",
        }, None

    def _deploy_cf_direct(self, file_path, html_content, title, slug):
        """v29: Deploy via Cloudflare Pages Direct Upload API with full
        site-root walk.

        HISTORY:
          v25-v27: Buggy. Uploaded only the new post. Would have wiped
                   the entire site. Never fired because a second bug
                   was blocking the first one.
          v28:     Safety hold — refused to run at all.
          v29:     Real fix. Writes the new post into the local site
                   mirror, regenerates blog/index.html, then uploads
                   the *entire* folder via the cloudflare_pages_deploy
                   module. Safe because the manifest now contains every
                   file on the site, not just the new one.

        Configuration keys used (from bvtech_config.json):
          site_root (or jp_site_root for the JP client) — absolute
              path to the local mirror of the site, e.g.
              C:\\BVTech2\\Website\\bvtech.org. Must contain index.html
              at the top level. The deployer refuses to run otherwise.
          cf_api_token, cf_account_id, cf_project_name — as before.
          cf_deploy_branch (optional) — defaults to "main".

        The first deployment will upload the full site (~19 MiB for
        bvtech.org). Every subsequent deployment only uploads the new
        blog post + regenerated blog/index.html — Cloudflare's
        check-missing endpoint caches the rest.
        """
        # Lazy import so the main app can still start even if the module
        # has an unexpected issue — the error will surface when the user
        # actually tries to deploy, not at startup.
        try:
            from cloudflare_pages_deploy import write_blog_post_and_deploy
        except ImportError as e:
            return None, f"v29: cloudflare_pages_deploy module missing: {e}"

        # Pick the right site_root for THIS client (BVTech vs JP)
        cfg = _load_config()
        if self.is_jp:
            site_root = (cfg.get("jp_site_root") or "").strip()
            project_name = self.cf_project_name or cfg.get("jp_cf_project_name", "jordanpolasek-site")
            token = self.cf_api_token
            account_id = self.cf_account_id
        else:
            site_root = (cfg.get("bvtech_site_root") or cfg.get("site_root") or "").strip()
            project_name = self.cf_project_name or cfg.get("cf_project_name", "bvtech-website")
            token = self.cf_api_token
            account_id = self.cf_account_id

        if not site_root:
            return None, (
                f"v29: site_root not configured for {self.site_name}. "
                f"Open Settings → Cloudflare and set {'jp_site_root' if self.is_jp else 'bvtech_site_root'} "
                f"to the absolute path of your local site folder "
                f"(e.g. C:\\BVTech2\\Website\\{'jordanpolasek.com' if self.is_jp else 'bvtech.org'})."
            )

        branch = cfg.get("cf_deploy_branch", "main") or "main"

        # Tee log output into a list so we can bubble it up to the caller
        log_lines = []
        def _log(msg):
            log_lines.append(str(msg))
            # Also print in case anything is tailing stdout
            try:
                print(f"  [CF-v29] {msg}")
            except Exception:
                pass

        try:
            result = write_blog_post_and_deploy(
                site_root=site_root,
                slug=slug,
                html=html_content,
                api_token=token,
                account_id=account_id,
                project_name=project_name,
                branch=branch,
                dry_run=False,
                regenerate_index=False,  # v29: default OFF — bvtech.org has a handcrafted blog/index.html
                logger=_log,
            )
        except ValueError as e:
            # ValueError = config/folder validation error — user-actionable
            return None, f"v29 CF deploy refused: {e}"
        except Exception as e:
            return None, f"v29 CF deploy failed: {e}\n\nLast log lines:\n" + "\n".join(log_lines[-10:])

        post_url = f"{self.site_url}/blog/{slug}/"
        return {
            "success": True,
            "id": slug,
            "post_id": slug,
            "title": title,
            "slug": slug,
            "link": post_url,
            "url": post_url,
            "deploy_mode": "cloudflare_direct_v29",
            "deployment_id": result.get("id", ""),
            "deployment_url": result.get("url", ""),
            "files_total": result.get("files_total", 0),
            "files_uploaded": result.get("files_uploaded", 0),
            "files_cached": result.get("files_cached", 0),
            "elapsed_sec": result.get("elapsed_sec", 0),
            "log": log_lines,
            "status": "published",
        }, None

    def test_cf_deploy(self, dry_run=True):
        """v29: Test Deploy button. Walks the local site, verifies the
        CF project, asks check-missing what it WOULD upload, and
        (by default) STOPS before actually uploading or deploying.

        Returns (result_dict, error_string).
        """
        try:
            from cloudflare_pages_deploy import CloudflarePagesDeployer
        except ImportError as e:
            return None, f"v29: cloudflare_pages_deploy module missing: {e}"

        cfg = _load_config()
        if self.is_jp:
            site_root = (cfg.get("jp_site_root") or "").strip()
        else:
            site_root = (cfg.get("bvtech_site_root") or cfg.get("site_root") or "").strip()

        if not site_root:
            return None, (
                f"site_root not configured for {self.site_name}. "
                f"Set {'jp_site_root' if self.is_jp else 'bvtech_site_root'} in Settings."
            )
        if self.mode != "cloudflare_direct":
            return None, f"CF Direct Upload not configured. Mode is: {self.mode}"

        log_lines = []
        def _log(msg):
            log_lines.append(str(msg))

        try:
            deployer = CloudflarePagesDeployer(
                api_token=self.cf_api_token,
                account_id=self.cf_account_id,
                project_name=self.cf_project_name,
                logger=_log,
            )
            result = deployer.deploy_folder(site_root, dry_run=dry_run)
        except ValueError as e:
            return None, f"Test deploy refused: {e}"
        except Exception as e:
            return None, f"Test deploy failed: {e}\n\nLog:\n" + "\n".join(log_lines)

        result["log"] = log_lines
        return result, None

    def _deploy_cf_direct_UNSAFE_v27_ORIGINAL(self, file_path, html_content, title, slug):
        """Preserved only for reference. DO NOT CALL."""
        result, err = self._cf_create_deployment({file_path: html_content})
        if err:
            return None, f"Cloudflare deploy failed: {err}"
        post_url = f"{self.site_url}/blog/{slug}/"
        return {
            "success": True,
            "id": slug,
            "post_id": slug,
            "title": title,
            "slug": slug,
            "link": post_url,
            "url": post_url,
            "deploy_mode": "cloudflare_direct",
            "deployment_id": result.get("id", ""),
            "status": "published",
        }, None

    # ── Public API: List Blog Posts ──────────────────────────
    def list_posts(self, per_page=50):
        """List blog posts from the repo/site."""
        if self.mode == "github":
            data, err = self._gh_api("GET", f"/contents/blog?ref={self.gh_branch}")
            if err:
                return None, err
            if not data:
                return {"posts": [], "total": 0}, None
            posts = []
            for f in data:
                if f.get("name", "").endswith(".html") and f["name"] != "index.html":
                    slug = f["name"].replace(".html", "")
                    posts.append({
                        "id": slug,
                        "title": slug.replace("-", " ").title(),
                        "slug": slug,
                        "url": f"{self.site_url}/blog/{slug}/",
                        "file_path": f["path"],
                        "sha": f.get("sha", ""),
                        "size": f.get("size", 0),
                        "status": "published",
                    })
            return {"posts": posts[:per_page], "total": len(posts)}, None
        elif self.mode == "cloudflare_direct":
            # CF direct doesn't have easy listing — return from local tracking
            return {"posts": [], "total": 0, "note": "Use GitHub mode for full blog management"}, None
        return None, "No deployment method configured"

    # ── Public API: Delete Blog Post ─────────────────────────
    def delete_post(self, slug_or_path):
        """Delete a blog post from the repo."""
        if self.mode != "github":
            return None, "Delete only supported in GitHub mode"

        file_path = slug_or_path if "/" in slug_or_path else f"blog/{slug_or_path}.html"
        existing, err = self._gh_get_file(file_path)
        if not existing:
            return None, f"Post not found: {file_path}"

        sha = existing.get("sha", "")
        result, err = self._gh_delete_file(file_path, sha, f"Delete blog post: {file_path}")
        if err:
            return None, err
        return {"success": True, "deleted": file_path}, None

    # ── Public API: Get All Titles ───────────────────────────
    def get_all_titles(self, per_page=200):
        """Get all blog post titles (for dedup checking). Returns set of lowercase titles."""
        titles = set()
        data, err = self.list_posts(per_page=per_page)
        if data and data.get("posts"):
            for p in data["posts"]:
                t = (p.get("title") or "").strip().lower()
                if t:
                    titles.add(t)
        return titles

    # ── Public API: Test Connection ──────────────────────────
    def test_connection(self):
        """Test the deployment connection."""
        if self.mode == "github":
            data, err = self._gh_api("GET", "")
            if err:
                return None, err
            if data:
                return {
                    "connected": True,
                    "mode": "github",
                    "repo": data.get("full_name", self.gh_repo),
                    "branch": self.gh_branch,
                    "site_url": self.site_url,
                    "description": data.get("description", ""),
                    "private": data.get("private", False),
                }, None
            return None, "Could not connect to GitHub repo"
        elif self.mode == "cloudflare_direct":
            url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/pages/projects/{self.cf_project_name}"
            try:
                r = requests.get(url, headers=self._cf_headers(), timeout=15)
                if r.status_code == 200:
                    d = r.json().get("result", {})
                    return {
                        "connected": True,
                        "mode": "cloudflare_direct",
                        "project": d.get("name", self.cf_project_name),
                        "site_url": self.site_url,
                        "subdomain": d.get("subdomain", ""),
                    }, None
                return None, f"CF API {r.status_code}: {r.text[:200]}"
            except Exception as e:
                return None, str(e)
        return None, "No deployment method configured. Add GitHub token + repo or Cloudflare API token in Settings."

    # ── Public API: Get Dashboard ────────────────────────────
    def get_dashboard(self):
        """Get site overview — posts count, last deploy, etc."""
        result = {"site_url": self.site_url, "mode": self.mode}
        posts_data, err = self.list_posts(per_page=200)
        if posts_data:
            result["total_posts"] = posts_data.get("total", 0)
            result["posts"] = posts_data.get("posts", [])[:10]  # Latest 10
        else:
            result["total_posts"] = 0
            result["error"] = err
        # Get last deployment info if GitHub
        if self.mode == "github":
            deploys, _ = self._gh_api("GET", f"/deployments?per_page=1")
            if deploys and len(deploys) > 0:
                result["last_deploy"] = {
                    "date": deploys[0].get("created_at", ""),
                    "description": deploys[0].get("description", ""),
                }
        return result, None


# ============================================================
# LINKEDIN API CLIENT — v20 ORM Integration
# Posts to LinkedIn as Jordan Polasek for personal brand ORM
# Uses LinkedIn's Share API (OAuth2 UGC Posts)
# ============================================================

class LinkedInClient:
    """LinkedIn posting client for ORM personal brand building.
    
    Uses LinkedIn's Community Management API / UGC Post API.
    Requires an access token with w_member_social scope.
    
    Setup:
      1. Create a LinkedIn App at linkedin.com/developers
      2. Request 'Share on LinkedIn' + 'Sign In with LinkedIn' products  
      3. OAuth2 flow to get access token (or use the 3-legged flow helper below)
      4. Store access token in config
    """

    API_BASE = "https://api.linkedin.com/v2"
    # v2 REST endpoint for posts (new Posts API)
    POSTS_URL = "https://api.linkedin.com/rest/posts"

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = _load_config()
        self.access_token = cfg.get("linkedin_access_token", "").strip()
        self.person_urn = cfg.get("linkedin_person_urn", "").strip()  # e.g., "urn:li:person:xxxxxxx"
        self.client_id = cfg.get("linkedin_client_id", "").strip()
        self.client_secret = cfg.get("linkedin_client_secret", "").strip()
        self.redirect_uri = cfg.get("linkedin_redirect_uri", "http://localhost:5678/api/linkedin/callback").strip()

    def _headers(self, use_rest_api=False):
        """Auth headers for LinkedIn API."""
        h = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        if use_rest_api:
            h["LinkedIn-Version"] = "202401"
        return h

    def test_connection(self):
        """Test LinkedIn connection by fetching profile info."""
        if not self.access_token:
            return None, "No LinkedIn access token. Configure in Settings → LinkedIn."
        try:
            # Try the /v2/userinfo endpoint (OpenID Connect)
            r = requests.get("https://api.linkedin.com/v2/userinfo",
                           headers=self._headers(), timeout=15)
            if r.status_code == 200:
                data = r.json()
                name = data.get("name", data.get("given_name", "Unknown"))
                sub = data.get("sub", "")
                return {
                    "connected": True,
                    "name": name,
                    "sub": sub,
                    "person_urn": self.person_urn or f"urn:li:person:{sub}",
                    "email": data.get("email", ""),
                }, None
            elif r.status_code == 401:
                return None, "LinkedIn token expired or invalid. Re-authenticate in Settings."
            return None, f"LinkedIn API {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return None, str(e)

    def get_person_urn(self):
        """Get the authenticated user's LinkedIn person URN."""
        if self.person_urn:
            return self.person_urn, None
        try:
            r = requests.get("https://api.linkedin.com/v2/userinfo",
                           headers=self._headers(), timeout=15)
            if r.status_code == 200:
                sub = r.json().get("sub", "")
                if sub:
                    self.person_urn = f"urn:li:person:{sub}"
                    return self.person_urn, None
            return None, f"Cannot get person URN: HTTP {r.status_code}"
        except Exception as e:
            return None, str(e)

    def create_post(self, text, title="", article_url="", visibility="PUBLIC"):
        """Create a LinkedIn post.
        
        Supports:
          - Text-only posts (for ORM thought leadership)
          - Article shares (with URL + title + description)
        
        Args:
            text: The post body text (1300 char max for text posts, 3000 for articles)
            title: Article title (if sharing a link)
            article_url: URL to share (optional — turns it into an article share)
            visibility: PUBLIC or CONNECTIONS
        """
        if not self.access_token:
            return None, "No LinkedIn access token configured."

        person_urn, err = self.get_person_urn()
        if not person_urn:
            return None, f"Cannot determine LinkedIn profile: {err}"

        # Build the post payload using the REST Posts API
        post_data = {
            "author": person_urn,
            "commentary": text[:3000],
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
        }

        # If sharing an article/link
        if article_url:
            post_data["content"] = {
                "article": {
                    "source": article_url,
                    "title": title[:200] if title else "",
                    "description": text[:256] if text else "",
                }
            }

        try:
            r = requests.post(self.POSTS_URL, headers=self._headers(use_rest_api=True),
                            json=post_data, timeout=30)
            if r.status_code in (200, 201):
                # LinkedIn returns the post ID in the x-restli-id header or response
                post_id = r.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "post_id": post_id,
                    "id": post_id,
                    "link": f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "",
                    "url": f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "",
                    "platform": "linkedin",
                }, None
            elif r.status_code == 401:
                return None, "LinkedIn token expired. Re-authenticate in Settings."
            elif r.status_code == 403:
                return None, "LinkedIn permissions insufficient. App needs 'w_member_social' scope."
            elif r.status_code == 422:
                # Try legacy UGC Post API as fallback
                return self._create_post_ugc(person_urn, text, title, article_url, visibility)
            return None, f"LinkedIn API {r.status_code}: {r.text[:300]}"
        except Exception as e:
            return None, str(e)

    def _create_post_ugc(self, person_urn, text, title, article_url, visibility):
        """Fallback: Create post via legacy UGC Post API."""
        ugc_data = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text[:3000]},
                    "shareMediaCategory": "ARTICLE" if article_url else "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            },
        }

        if article_url:
            ugc_data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
                "status": "READY",
                "description": {"text": text[:200]},
                "originalUrl": article_url,
                "title": {"text": title[:200] if title else ""},
            }]

        try:
            r = requests.post(f"{self.API_BASE}/ugcPosts", headers=self._headers(),
                            json=ugc_data, timeout=30)
            if r.status_code in (200, 201):
                data = r.json()
                post_id = data.get("id", "")
                return {
                    "success": True,
                    "post_id": post_id,
                    "id": post_id,
                    "link": f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "",
                    "url": f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "",
                    "platform": "linkedin",
                    "api": "ugc",
                }, None
            return None, f"LinkedIn UGC API {r.status_code}: {r.text[:300]}"
        except Exception as e:
            return None, str(e)

    def get_auth_url(self):
        """Generate the OAuth2 authorization URL for LinkedIn login."""
        import urllib.parse
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "openid profile email w_member_social",
            "state": "bvtech_orm_linkedin",
        }
        return f"https://www.linkedin.com/oauth/v2/authorization?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code):
        """Exchange OAuth2 authorization code for access token."""
        try:
            r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }, timeout=15)
            if r.status_code == 200:
                data = r.json()
                return {
                    "access_token": data.get("access_token", ""),
                    "expires_in": data.get("expires_in", 0),
                    "scope": data.get("scope", ""),
                }, None
            return None, f"Token exchange failed: {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return None, str(e)
