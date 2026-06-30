#!/usr/bin/env python3
"""
BVTech MSP Marketing Automation — Program 2: SMS Campaign Engine
=================================================================
Sends personalized SMS messages via DialPad API.

⚠️  TCPA COMPLIANCE WARNING ⚠️
You MUST have prior express written consent before sending marketing texts.
Fines: $500-$1,500 PER unauthorized message. This is not optional.
Only use this with contacts who have explicitly opted in to receive texts.

SETUP:
1. Get DialPad Pro/Enterprise plan (API access required)
2. Request API access at dialpad.com/developers
3. Register your number for 10DLC (A2P messaging compliance)
4. pip install requests --break-system-packages

USAGE:
    python3 sms_campaign.py --dry-run         # Preview messages
    python3 sms_campaign.py                   # Send to opted-in contacts
    python3 sms_campaign.py --template intro  # Use specific template
"""

import json
import csv
import time
import logging
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("Install: pip install requests --break-system-packages")
    sys.exit(1)


# ============================================================
# CONFIGURATION
# ============================================================
CONFIG = {
    # DialPad API
    "api_key": os.getenv("DIALPAD_API_KEY", "YOUR_DIALPAD_API_KEY"),
    "user_id": os.getenv("DIALPAD_USER_ID", "YOUR_DIALPAD_USER_ID"),
    "from_number": os.getenv("DIALPAD_NUMBER", "+15125550100"),

    # Sender
    "sender_name": os.getenv("SENDER_NAME", "Your Name"),

    # Rate Limits (DialPad API limits)
    "messages_per_minute": 80,    # DialPad Tier 0 = 100/min. Stay under.
    "daily_limit": 500,           # Self-imposed daily limit
    "delay_between_sms": 0.8,    # Seconds between messages

    # TCPA Compliance
    "quiet_hours_start": 9,      # 9 AM local time
    "quiet_hours_end": 20,       # 8 PM local time (20:00)
    "timezone": "America/Chicago", # Texas timezone

    # Files
    "prospects_csv": "sms_prospects.csv",  # Must be opted-in contacts!
    "sent_log": "sms_sent_log.csv",
    "opt_out_log": "sms_opt_outs.csv",
    "state_file": "sms_campaign_state.json",
}

# Bridge: Load API keys from GUI settings (bvtech_config.json)
from pathlib import Path as _Path
_gui_path = _Path("bvtech_config.json")
if _gui_path.exists():
    try:
        import json as _json
        with open(_gui_path, "r") as _f:
            _gui = _json.load(_f)
            if _gui.get("dialpad_key"): CONFIG["api_key"] = _gui["dialpad_key"]
            if _gui.get("dialpad_user_id"): CONFIG["user_id"] = _gui["dialpad_user_id"]
            if _gui.get("dialpad_number"): CONFIG["from_number"] = _gui["dialpad_number"]
            if _gui.get("sender_name"): CONFIG["sender_name"] = _gui["sender_name"]
    except Exception:
        pass


# ============================================================
# SMS TEMPLATES
# ============================================================
TEMPLATES = {
    "intro": {
        "text": "Hi {{first_name}}, this is {{sender_name}} from BVTech. "
                "We help {{industry}} businesses in {{city}} with IT support & cybersecurity. "
                "Would you be open to a quick chat about how we could help {{company}}? "
                "Reply STOP to opt out.",
    },
    "follow_up": {
        "text": "Hi {{first_name}}, just following up from BVTech. "
                "We're offering free IT Security Assessments for {{city}} businesses this month. "
                "Interested? Reply STOP to opt out.",
    },
    "value": {
        "text": "Hi {{first_name}}, {{sender_name}} from BVTech here. "
                "Quick tip: {{industry}} businesses are the #1 target for ransomware in TX. "
                "We just published a free guide - want me to send it over? "
                "Reply STOP to opt out.",
    },
    "appointment": {
        "text": "Hi {{first_name}}, this is {{sender_name}} from BVTech. "
                "Thanks for your interest! I have openings this week for a quick 15-min call. "
                "Would Tuesday or Thursday work better for you? "
                "Reply STOP to opt out.",
    },
}


# ============================================================
# DIALPAD SMS CLIENT
# ============================================================
class DialPadSMSClient:
    """Send SMS via DialPad API v2."""

    BASE_URL = "https://dialpad.com/api/v2"

    def __init__(self, api_key, user_id):
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def send_sms(self, to_number, text, from_number=None):
        """
        Send SMS via DialPad API.
        Endpoint: POST /api/v2/sms
        Rate limit: 100/min (Tier 0) or 800/min (Tier 1)
        """
        payload = {
            "to_numbers": [to_number],
            "text": text,
            "user_id": int(self.user_id) if self.user_id.isdigit() else self.user_id,
        }

        try:
            response = self.session.post(
                f"{self.BASE_URL}/sms",
                json=payload,
                timeout=15,
            )

            if response.status_code == 200:
                return True, "Sent", response.json()
            elif response.status_code == 429:
                retry = response.headers.get("Retry-After", "60")
                return False, f"Rate limited. Retry after {retry}s", None
            elif response.status_code == 401:
                return False, "Authentication failed. Check API key.", None
            elif response.status_code == 403:
                return False, "Forbidden. Check API permissions/scopes.", None
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}", None

        except requests.exceptions.RequestException as e:
            return False, f"Request error: {str(e)}", None


# ============================================================
# SMS CAMPAIGN ENGINE
# ============================================================
class SMSCampaignEngine:
    """Orchestrates SMS campaign with TCPA compliance."""

    def __init__(self, config, dry_run=False, template_key="intro"):
        self.config = config
        self.dry_run = dry_run
        self.template_key = template_key
        self.logger = self._setup_logging()
        self.state = self._load_state()
        self.sent_today = 0
        self.opt_outs = set(self.state.get("opt_outs", []))

        if not dry_run:
            self.sms_client = DialPadSMSClient(
                config["api_key"],
                config["user_id"],
            )
        else:
            self.sms_client = None

    def _setup_logging(self):
        logger = logging.getLogger("sms_campaign")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
        fh = logging.FileHandler("sms_campaign.log")
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(fh)
        return logger

    def _load_state(self):
        state_file = Path(self.config["state_file"])
        if state_file.exists():
            return json.loads(state_file.read_text())
        return {"sent_sms": {}, "opt_outs": [], "total_sent": 0, "last_run_date": None}

    def _save_state(self):
        self.state["opt_outs"] = list(self.opt_outs)
        Path(self.config["state_file"]).write_text(json.dumps(self.state, indent=2))

    def _is_quiet_hours(self):
        """Check if current time is within TCPA quiet hours."""
        tz = ZoneInfo(self.config["timezone"])
        now = datetime.now(tz)
        hour = now.hour
        if hour < self.config["quiet_hours_start"] or hour >= self.config["quiet_hours_end"]:
            return True
        return False

    def _load_prospects(self):
        """Load opted-in SMS prospects."""
        prospects = []
        csv_path = Path(self.config["prospects_csv"])
        if not csv_path.exists():
            self.logger.error(f"Prospects CSV not found: {csv_path}")
            self.logger.info("Expected columns: phone,first_name,last_name,company,industry,city,opted_in_date")
            self.logger.warning("⚠️ ONLY include contacts who gave express written consent!")
            return []

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone = row.get("phone", "").strip()
                opted_in = row.get("opted_in_date", "").strip()

                if not phone:
                    continue
                if phone in self.opt_outs:
                    continue
                if not opted_in:
                    self.logger.warning(f"⚠️ Skipping {phone} — no opt-in date recorded (TCPA required)")
                    continue
                prospects.append(row)

        self.logger.info(f"Loaded {len(prospects)} opted-in prospects")
        return prospects

    def _fill_template(self, text, prospect):
        replacements = {
            "{{first_name}}": prospect.get("first_name", "there"),
            "{{company}}": prospect.get("company", "your company"),
            "{{city}}": prospect.get("city", "Texas"),
            "{{industry}}": prospect.get("industry", "business"),
            "{{sender_name}}": self.config["sender_name"],
        }
        result = text
        for key, value in replacements.items():
            result = result.replace(key, value)
        return result

    def _log_sent(self, prospect, template_key, success, detail=""):
        log_file = Path(self.config["sent_log"])
        write_header = not log_file.exists()
        with open(log_file, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["timestamp", "phone", "name", "company", "template", "status", "detail"])
            writer.writerow([
                datetime.now().isoformat(),
                prospect.get("phone"),
                f"{prospect.get('first_name')} {prospect.get('last_name')}",
                prospect.get("company"),
                template_key,
                "sent" if success else "failed",
                detail,
            ])

    def run(self):
        """Execute SMS campaign."""
        self.logger.info("=" * 60)
        self.logger.info("BVTech SMS Campaign Engine — Starting")
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.logger.info(f"Template: {self.template_key}")
        self.logger.info("=" * 60)

        # TCPA quiet hours check
        if self._is_quiet_hours():
            self.logger.error("🔇 TCPA Quiet Hours — Cannot send before 9AM or after 8PM local time.")
            self.logger.info("Schedule this to run during business hours (9AM-8PM CT).")
            return

        template = TEMPLATES.get(self.template_key)
        if not template:
            self.logger.error(f"Template '{self.template_key}' not found.")
            return

        prospects = self._load_prospects()
        if not prospects:
            return

        daily_limit = self.config["daily_limit"]
        self.logger.info(f"Daily limit: {daily_limit} messages")

        for prospect in prospects:
            if self.sent_today >= daily_limit:
                self.logger.info(f"✅ Daily limit reached ({daily_limit}). Stopping.")
                break

            phone = prospect.get("phone", "").strip()
            # Skip if already texted with this template
            sent_key = f"{phone}:{self.template_key}"
            if sent_key in self.state.get("sent_sms", {}):
                continue

            text = self._fill_template(template["text"], prospect)

            # Character count check (SMS = 160 chars per segment)
            segments = (len(text) + 159) // 160
            if segments > 2:
                self.logger.warning(f"⚠️ Message to {phone} is {len(text)} chars ({segments} segments). Consider shortening.")

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would send to {phone}: {text[:80]}...")
                self._log_sent(prospect, self.template_key, True, "dry_run")
                self.sent_today += 1
            else:
                success, detail, response = self.sms_client.send_sms(
                    to_number=phone,
                    text=text,
                )
                if success:
                    self.logger.info(f"💬 Sent [{self.template_key}] to {phone}")
                    self.sent_today += 1
                    self.state["total_sent"] += 1
                    if "sent_sms" not in self.state:
                        self.state["sent_sms"] = {}
                    self.state["sent_sms"][sent_key] = datetime.now().isoformat()
                else:
                    self.logger.warning(f"❌ Failed {phone}: {detail}")
                    if "429" in detail:
                        self.logger.info("Rate limited. Waiting 60s...")
                        time.sleep(60)
                        continue

                self._log_sent(prospect, self.template_key, success, detail)

            time.sleep(self.config["delay_between_sms"])

            if self.sent_today % 10 == 0:
                self._save_state()

        self._save_state()

        self.logger.info("=" * 60)
        self.logger.info(f"Session complete: {self.sent_today} SMS sent")
        self.logger.info(f"Total campaign: {self.state['total_sent']} messages")
        self.logger.info(f"Opt-outs: {len(self.opt_outs)}")
        self.logger.info("=" * 60)


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BVTech MSP SMS Campaign Engine")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--template", default="intro",
                        choices=list(TEMPLATES.keys()),
                        help="Template to use")
    args = parser.parse_args()

    engine = SMSCampaignEngine(
        config=CONFIG,
        dry_run=args.dry_run,
        template_key=args.template,
    )
    engine.run()


if __name__ == "__main__":
    main()
