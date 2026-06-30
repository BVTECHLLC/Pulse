#!/usr/bin/env python3
"""
BVTech MSP Marketing Automation — Program 1: Email Campaign Engine v2
======================================================================
+ HubSpot CRM Integration (syncs contacts + logs activity)
+ Fixed CAN-SPAM footer with real address
+ Fixed Windows emoji logging
+ Jordan Polasek / BVTech pre-configured

SETUP:
1. Azure AD App: tenant_id, client_id, client_secret
2. HubSpot Private App: access token with contacts read/write
3. pip install msal requests

USAGE:
    python email_campaign.py --dry-run          # Preview without sending
    python email_campaign.py --warmup           # Warm-up mode (50/day ramp)
    python email_campaign.py                    # Full send
    python email_campaign.py --daily-limit 50   # Custom limit
    python email_campaign.py --sync-only        # Just sync prospects to HubSpot
"""

import json
import csv
import time
import logging
import argparse
import random
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import msal
    import requests
except ImportError:
    print("Install required packages: pip install msal requests")
    sys.exit(1)


# ============================================================
# CONFIGURATION
# ============================================================
CONFIG = {
    # Azure AD App Registration
    "tenant_id": os.getenv("M365_TENANT_ID", "YOUR_TENANT_ID"),
    "client_id": os.getenv("M365_CLIENT_ID", "YOUR_CLIENT_ID"),
    "client_secret": os.getenv("M365_CLIENT_SECRET", "YOUR_CLIENT_SECRET"),

    # HubSpot Private App
    "hubspot_token": os.getenv("HUBSPOT_TOKEN", "YOUR_HUBSPOT_TOKEN"),
    "hubspot_enabled": True,  # Set to False to skip HubSpot sync

    # Sender — Pre-filled for Jordan
    "sender_email": "help@bvtech.org",
    "sender_name": "Jordan Polasek",
    "sender_title": "Managing Partner",
    "sender_phone": "(210) 538-3669",

    # Sending Limits
    "daily_limit": 200,
    "emails_per_minute": 25,
    "delay_between_emails": 3,
    "warmup_start": 50,
    "warmup_increment": 25,

    # Bounce/Reputation Protection
    "max_bounce_rate": 0.05,
    "max_complaint_rate": 0.01,

    # CAN-SPAM Compliance
    "physical_address": "BVTech LLC, 1902 Kirby Rd, El Campo, TX 77437",
    # HubSpot handles unsubscribes — this is a mailto fallback
    "unsubscribe_url": "mailto:help@bvtech.org?subject=Unsubscribe&body=Please%20remove%20me%20from%20your%20mailing%20list.",

    # File paths
    "prospects_csv": "prospects.csv",
    "sent_log": "sent_log.csv",
    "bounce_log": "bounce_log.csv",
    "state_file": "campaign_state.json",
}

# Bridge: Load API keys + sender info from GUI settings (bvtech_config.json)
# Works in both script mode and when spawned by PyInstaller EXE
def _find_gui_config():
    """Find bvtech_config.json — next to this script, in CWD, or next to the parent EXE."""
    candidates = [
        Path("bvtech_config.json"),                                          # CWD
        Path(os.path.dirname(os.path.abspath(__file__))) / "bvtech_config.json",  # Next to script
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

_gui_config_path = _find_gui_config()
if _gui_config_path:
    try:
        with open(_gui_config_path, "r") as _f:
            _gui = json.load(_f)
            _bridge_fields = {
                "tenant_id": "tenant_id", "client_id": "client_id",
                "client_secret": "client_secret", "hubspot_token": "hubspot_token",
                "sender_email": "sender_email", "sender_name": "sender_name",
                "sender_title": "sender_title", "sender_phone": "sender_phone",
                "physical_address": "physical_address",
            }
            for gui_key, config_key in _bridge_fields.items():
                if _gui.get(gui_key):
                    CONFIG[config_key] = _gui[gui_key]
    except Exception:
        pass


# ============================================================
# EMAIL TEMPLATES — 4-Touch Sequence
# ============================================================
TEMPLATES = {
    "cold_intro": {
        "delay_days": 0,
        "subject": "Quick question about {{company}}'s IT setup",
        "body_html": """
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6; max-width: 600px;">
    <p>Hi {{first_name}},</p>

    <p>I noticed {{company}} is growing in the {{city}} market &mdash; congrats on that.</p>

    <p>I work with {{industry}} businesses across Texas to eliminate IT headaches so
    owners can focus on what they do best. We handle everything from cybersecurity
    to cloud management to day-to-day helpdesk support.</p>

    <p>Most of our clients save 30-40% compared to hiring in-house IT, and they get
    enterprise-grade security they couldn't afford on their own.</p>

    <p>Would you be open to a 15-minute call this week to see if we might be a good fit?</p>

    <p>Best,<br>
    <strong>{{sender_name}}</strong><br>
    {{sender_title}}<br>
    BVTech | <a href="https://bvtech.org" style="color: #2563eb;">bvtech.org</a><br>
    {{sender_phone}}</p>

    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="font-size: 11px; color: #999;">
        {{physical_address}}<br>
        <a href="{{unsubscribe_url}}" style="color: #999;">Unsubscribe</a> from future emails.
    </p>
</div>
""",
    },
    "follow_up_1": {
        "delay_days": 3,
        "subject": "Re: Quick question about {{company}}'s IT setup",
        "body_html": """
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6; max-width: 600px;">
    <p>Hi {{first_name}},</p>

    <p>Just bumping this to the top of your inbox. I know you're busy running
    {{company}}, so I'll keep this brief.</p>

    <p>We recently helped a {{industry}} company in {{city}} reduce their downtime
    by 94% and cut IT costs by $2,400/month. Happy to share how.</p>

    <p>Worth a quick chat?</p>

    <p>{{sender_name}}<br>
    BVTech | <a href="https://bvtech.org" style="color: #2563eb;">bvtech.org</a></p>

    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="font-size: 11px; color: #999;">
        {{physical_address}}<br>
        <a href="{{unsubscribe_url}}" style="color: #999;">Unsubscribe</a>
    </p>
</div>
""",
    },
    "follow_up_2": {
        "delay_days": 7,
        "subject": "Free IT Security Assessment for {{company}}",
        "body_html": """
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6; max-width: 600px;">
    <p>Hi {{first_name}},</p>

    <p>I wanted to offer {{company}} a complimentary IT Security Assessment &mdash;
    no strings attached.</p>

    <p>With ransomware attacks up 300% targeting {{industry}} businesses in Texas,
    it's worth knowing where your vulnerabilities are before someone else finds them.</p>

    <p>Our assessment covers:</p>
    <ul style="color: #555;">
        <li>Network vulnerability scan</li>
        <li>Email security review (spoofing, phishing exposure)</li>
        <li>Microsoft 365 security configuration audit</li>
        <li>Backup &amp; disaster recovery evaluation</li>
        <li>Compliance gap analysis (if applicable)</li>
    </ul>

    <p>It takes about 30 minutes and you'll get a full report you keep regardless
    of whether we work together.</p>

    <p>Interested? Just reply with a good time.</p>

    <p>{{sender_name}}<br>
    BVTech | <a href="https://bvtech.org" style="color: #2563eb;">bvtech.org</a><br>
    {{sender_phone}}</p>

    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="font-size: 11px; color: #999;">
        {{physical_address}}<br>
        <a href="{{unsubscribe_url}}" style="color: #999;">Unsubscribe</a>
    </p>
</div>
""",
    },
    "breakup": {
        "delay_days": 14,
        "subject": "Should I close your file?",
        "body_html": """
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6; max-width: 600px;">
    <p>Hi {{first_name}},</p>

    <p>I've reached out a few times and haven't heard back, so I'll assume the
    timing isn't right.</p>

    <p>No hard feelings at all &mdash; I'll close your file for now. But if {{company}}
    ever needs IT support, cybersecurity help, or just a second opinion on your
    tech setup, we're here.</p>

    <p>Wishing you continued success in {{city}}.</p>

    <p>{{sender_name}}<br>
    BVTech | <a href="https://bvtech.org" style="color: #2563eb;">bvtech.org</a></p>

    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="font-size: 11px; color: #999;">
        {{physical_address}}<br>
        <a href="{{unsubscribe_url}}" style="color: #999;">Unsubscribe</a>
    </p>
</div>
""",
    },
}


# ============================================================
# HUBSPOT CRM CLIENT
# ============================================================
class HubSpotClient:
    """Sync contacts and log activity to HubSpot CRM."""

    BASE_URL = "https://api.hubapi.com"

    def __init__(self, access_token):
        self.token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def create_or_update_contact(self, prospect):
        """Create or update a contact in HubSpot."""
        email = prospect.get("email", "").strip().lower()
        if not email:
            return None, "No email"

        properties = {
            "email": email,
            "firstname": prospect.get("first_name", ""),
            "lastname": prospect.get("last_name", ""),
            "company": prospect.get("company", ""),
            "city": prospect.get("city", ""),
            "state": prospect.get("state", "TX"),
            "zip": prospect.get("zip", ""),
            "phone": prospect.get("phone", ""),
            "industry": prospect.get("industry", ""),
            "numberofemployees": prospect.get("employees", ""),
            "hs_lead_status": "NEW",
            "lifecyclestage": "lead",
        }

        # Try to create first
        payload = {"properties": properties}
        response = requests.post(
            f"{self.BASE_URL}/crm/v3/objects/contacts",
            headers=self.headers,
            json=payload,
            timeout=15,
        )

        if response.status_code == 201:
            contact_id = response.json().get("id")
            return contact_id, "created"
        elif response.status_code == 409:
            # Contact exists — update instead
            existing_id = response.json().get("message", "")
            # Extract contact ID from conflict message or search
            return self._update_by_email(email, properties)
        else:
            return None, f"HTTP {response.status_code}: {response.text[:200]}"

    def _update_by_email(self, email, properties):
        """Update existing contact by email."""
        # Search for contact
        search_payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": email,
                }]
            }],
            "limit": 1,
        }
        response = requests.post(
            f"{self.BASE_URL}/crm/v3/objects/contacts/search",
            headers=self.headers,
            json=search_payload,
            timeout=15,
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                contact_id = results[0]["id"]
                # Update
                update_resp = requests.patch(
                    f"{self.BASE_URL}/crm/v3/objects/contacts/{contact_id}",
                    headers=self.headers,
                    json={"properties": properties},
                    timeout=15,
                )
                if update_resp.status_code == 200:
                    return contact_id, "updated"
                return None, f"Update failed: {update_resp.status_code}"
        return None, "Search failed"

    def log_email_activity(self, contact_id, subject, body_preview, status="SENT"):
        """Log an email engagement to a contact's timeline."""
        if not contact_id:
            return

        # Create a note on the contact as email activity log
        note_body = f"Email Campaign: {subject}\nStatus: {status}\nSent: {datetime.now().isoformat()}"
        payload = {
            "properties": {
                "hs_timestamp": str(int(datetime.now().timestamp() * 1000)),
                "hs_note_body": note_body,
            },
            "associations": [{
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]
            }]
        }
        requests.post(
            f"{self.BASE_URL}/crm/v3/objects/notes",
            headers=self.headers,
            json=payload,
            timeout=15,
        )

    def check_unsubscribed(self, email):
        """Check if contact has opted out in HubSpot."""
        search_payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": email,
                }]
            }],
            "properties": ["hs_email_optout", "hs_email_optout_all"],
            "limit": 1,
        }
        response = requests.post(
            f"{self.BASE_URL}/crm/v3/objects/contacts/search",
            headers=self.headers,
            json=search_payload,
            timeout=15,
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                props = results[0].get("properties", {})
                if props.get("hs_email_optout") == "true" or props.get("hs_email_optout_all") == "true":
                    return True
        return False

    def sync_all_prospects(self, prospects, logger):
        """Bulk sync prospects to HubSpot as contacts."""
        logger.info(f"Syncing {len(prospects)} prospects to HubSpot...")
        created = 0
        updated = 0
        failed = 0

        for i, prospect in enumerate(prospects):
            contact_id, status = self.create_or_update_contact(prospect)
            if status == "created":
                created += 1
            elif status == "updated":
                updated += 1
            else:
                failed += 1

            if (i + 1) % 20 == 0:
                logger.info(f"  Progress: {i+1}/{len(prospects)} ({created} new, {updated} updated)")
                time.sleep(0.2)  # Rate limit protection

        logger.info(f"HubSpot sync complete: {created} created, {updated} updated, {failed} failed")
        return created, updated, failed


# ============================================================
# MICROSOFT GRAPH API CLIENT
# ============================================================
class GraphMailClient:
    """Authenticates with Azure AD and sends email via Microsoft Graph."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, tenant_id, client_id, client_secret):
        self.app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        self._token_cache = None
        self._token_expiry = None

    def _get_token(self):
        if self._token_cache and self._token_expiry and datetime.now() < self._token_expiry:
            return self._token_cache

        result = self.app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" in result:
            self._token_cache = result["access_token"]
            self._token_expiry = datetime.now() + timedelta(minutes=50)
            return self._token_cache
        else:
            raise Exception(f"Auth failed: {result.get('error_description', 'Unknown error')}")

    def send_email(self, sender_email, to_email, subject, body_html, reply_to=None):
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html,
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_email}}
                ],
            },
            "saveToSentItems": True,
        }

        if reply_to:
            message["message"]["replyTo"] = [
                {"emailAddress": {"address": reply_to}}
            ]

        url = f"{self.GRAPH_URL}/users/{sender_email}/sendMail"
        response = requests.post(url, headers=headers, json=message, timeout=30)

        if response.status_code == 202:
            return True, "Sent"
        elif response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            return False, f"Rate limited. Retry after {retry_after}s"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"


# ============================================================
# CAMPAIGN ENGINE
# ============================================================
class EmailCampaignEngine:

    def __init__(self, config, dry_run=False, warmup=False, sync_only=False):
        self.config = config
        self.dry_run = dry_run
        self.warmup = warmup
        self.sync_only = sync_only
        self.logger = self._setup_logging()
        self.state = self._load_state()
        self.sent_today = 0
        self.bounces = 0
        self.complaints = 0

        if not dry_run and not sync_only:
            self.mail_client = GraphMailClient(
                config["tenant_id"],
                config["client_id"],
                config["client_secret"],
            )
        else:
            self.mail_client = None

        # HubSpot integration
        self.hubspot = None
        if config.get("hubspot_enabled") and config.get("hubspot_token") != "YOUR_HUBSPOT_TOKEN":
            try:
                self.hubspot = HubSpotClient(config["hubspot_token"])
                self.logger.info("HubSpot integration: ACTIVE")
            except Exception as e:
                self.logger.warning(f"HubSpot init failed: {e}")
        else:
            self.logger.info("HubSpot integration: DISABLED (no token)")

    def _setup_logging(self):
        logger = logging.getLogger("email_campaign")
        logger.setLevel(logging.INFO)

        # Windows-safe formatter (no emojis in console)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        # Force UTF-8 on Windows
        if sys.platform == "win32":
            import io
            handler.stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        logger.addHandler(handler)

        fh = logging.FileHandler("email_campaign.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(fh)
        return logger

    def _load_state(self):
        state_file = Path(self.config["state_file"])
        if state_file.exists():
            return json.loads(state_file.read_text())
        return {
            "sent_emails": {},
            "unsubscribes": [],
            "bounced": [],
            "day_count": 0,
            "last_run_date": None,
            "total_sent": 0,
        }

    def _save_state(self):
        Path(self.config["state_file"]).write_text(json.dumps(self.state, indent=2))

    def _load_prospects(self):
        prospects = []
        csv_path = Path(self.config["prospects_csv"])
        if not csv_path.exists():
            self.logger.error(f"Prospects CSV not found: {csv_path}")
            self.logger.info("Expected columns: email,first_name,last_name,company,industry,city")
            return []

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = row.get("email", "").strip().lower()
                if not email:
                    continue
                if email in self.state["unsubscribes"] or email in self.state["bounced"]:
                    continue
                # Check HubSpot unsubscribe status
                if self.hubspot and self.hubspot.check_unsubscribed(email):
                    self.logger.info(f"Skipping {email} -- unsubscribed in HubSpot")
                    self.state["unsubscribes"].append(email)
                    continue
                prospects.append(row)

        self.logger.info(f"Loaded {len(prospects)} prospects (excluded {len(self.state['unsubscribes'])} unsubs, {len(self.state['bounced'])} bounces)")
        return prospects

    def _fill_template(self, template_str, prospect):
        replacements = {
            "{{first_name}}": prospect.get("first_name", "there"),
            "{{last_name}}": prospect.get("last_name", ""),
            "{{company}}": prospect.get("company", "your company"),
            "{{industry}}": prospect.get("industry", "business"),
            "{{city}}": prospect.get("city", "Texas"),
            "{{email}}": prospect.get("email", ""),
            "{{sender_name}}": self.config["sender_name"],
            "{{sender_title}}": self.config["sender_title"],
            "{{sender_phone}}": self.config["sender_phone"],
            "{{physical_address}}": self.config["physical_address"],
            "{{unsubscribe_url}}": self.config["unsubscribe_url"].replace(
                "{{email}}", prospect.get("email", "")
            ),
        }
        result = template_str
        for key, value in replacements.items():
            result = result.replace(key, str(value))
        return result

    def _get_daily_limit(self):
        if self.warmup:
            limit = self.config["warmup_start"] + (
                self.state["day_count"] * self.config["warmup_increment"]
            )
            return min(limit, self.config["daily_limit"])
        return self.config["daily_limit"]

    def _check_reputation(self):
        if self.sent_today < 10:
            return True
        bounce_rate = self.bounces / self.sent_today
        if bounce_rate > self.config["max_bounce_rate"]:
            self.logger.warning(f"!! Bounce rate {bounce_rate:.1%} exceeds limit. Pausing.")
            return False
        return True

    def _get_next_template(self, email):
        sent_templates = self.state["sent_emails"].get(email, [])
        sequence = ["cold_intro", "follow_up_1", "follow_up_2", "breakup"]
        for tmpl_key in sequence:
            if tmpl_key not in sent_templates:
                template = TEMPLATES[tmpl_key]
                return tmpl_key, template
        return None, None

    def _log_sent(self, prospect, template_key, success, detail=""):
        log_file = Path(self.config["sent_log"])
        write_header = not log_file.exists()
        with open(log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["timestamp", "email", "name", "company", "template", "status", "detail"])
            writer.writerow([
                datetime.now().isoformat(),
                prospect.get("email"),
                f"{prospect.get('first_name')} {prospect.get('last_name')}",
                prospect.get("company"),
                template_key,
                "sent" if success else "failed",
                detail,
            ])

    def run(self, daily_limit_override=None):
        self.logger.info("=" * 60)
        self.logger.info("BVTech Email Campaign Engine v2")
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'SYNC ONLY' if self.sync_only else 'LIVE'}")
        self.logger.info(f"Warmup: {'ON' if self.warmup else 'OFF'}")
        self.logger.info(f"HubSpot: {'ACTIVE' if self.hubspot else 'DISABLED'}")
        self.logger.info("=" * 60)

        prospects = self._load_prospects()
        if not prospects:
            return

        # Sync prospects to HubSpot
        if self.hubspot:
            self.hubspot.sync_all_prospects(prospects, self.logger)

        if self.sync_only:
            self.logger.info("Sync-only mode. Done.")
            return

        daily_limit = daily_limit_override or self._get_daily_limit()
        self.logger.info(f"Daily limit: {daily_limit} emails")
        self.logger.info(f"Rate: {self.config['emails_per_minute']}/min")

        random.shuffle(prospects)

        for prospect in prospects:
            if self.sent_today >= daily_limit:
                self.logger.info(f"Daily limit reached ({daily_limit}). Stopping.")
                break

            if not self._check_reputation():
                self.logger.error("Reputation check failed. Campaign paused.")
                break

            email = prospect.get("email", "").strip().lower()
            template_key, template = self._get_next_template(email)

            if template is None:
                continue

            subject = self._fill_template(template["subject"], prospect)
            body = self._fill_template(template["body_html"], prospect)

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would send '{subject}' to {email}")
                self._log_sent(prospect, template_key, True, "dry_run")
                self.sent_today += 1
            else:
                success, detail = self.mail_client.send_email(
                    sender_email=self.config["sender_email"],
                    to_email=email,
                    subject=subject,
                    body_html=body,
                )
                if success:
                    self.logger.info(f"[SENT] [{template_key}] to {email}")
                    self.sent_today += 1
                    self.state["total_sent"] += 1
                    if email not in self.state["sent_emails"]:
                        self.state["sent_emails"][email] = []
                    self.state["sent_emails"][email].append(template_key)

                    # Log to HubSpot
                    if self.hubspot:
                        cid, _ = self.hubspot.create_or_update_contact(prospect)
                        self.hubspot.log_email_activity(cid, subject, "", "SENT")
                else:
                    self.logger.warning(f"[FAILED] {email}: {detail}")
                    if "550" in detail or "invalid" in detail.lower():
                        self.bounces += 1
                        self.state["bounced"].append(email)
                    elif "429" in detail:
                        self.logger.info("Rate limited. Waiting 60s...")
                        time.sleep(60)
                        continue

                self._log_sent(prospect, template_key, success, detail)

            delay = self.config["delay_between_emails"] + random.uniform(-1, 1)
            time.sleep(max(1, delay))

            if self.sent_today % 10 == 0:
                self._save_state()

        # Update state
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state["last_run_date"] != today:
            self.state["day_count"] += 1
        self.state["last_run_date"] = today
        self._save_state()

        self.logger.info("=" * 60)
        self.logger.info(f"Session complete: {self.sent_today} emails sent")
        self.logger.info(f"Total campaign: {self.state['total_sent']} emails")
        self.logger.info(f"Bounces: {self.bounces} | Unsubs: {len(self.state['unsubscribes'])}")
        self.logger.info("=" * 60)


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BVTech MSP Email Campaign Engine v2")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--warmup", action="store_true", help="Start in warm-up mode")
    parser.add_argument("--daily-limit", type=int, help="Override daily send limit")
    parser.add_argument("--sync-only", action="store_true", help="Only sync prospects to HubSpot")
    args = parser.parse_args()

    engine = EmailCampaignEngine(
        config=CONFIG,
        dry_run=args.dry_run,
        warmup=args.warmup,
        sync_only=args.sync_only,
    )
    engine.run(daily_limit_override=args.daily_limit)


if __name__ == "__main__":
    main()
