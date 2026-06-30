#!/usr/bin/env python3
"""
BVTech MSP Marketing Automation — Program 3: Power Dialer
===========================================================
Auto-dials prospects through your DialPad desktop/web app.
You handle the conversation — the script handles the list.

HOW IT WORKS:
1. Loads your prospect list
2. Shows you the prospect info + call script
3. Triggers the call via DialPad API (rings your DialPad app)
4. You talk while reading the on-screen script
5. After call, you enter disposition + notes
6. Script auto-advances to the next prospect

REQUIREMENTS:
- DialPad desktop or web app must be open (autocallable device)
- DialPad API key with call initiate permission
- pip install requests rich --break-system-packages

USAGE:
    python3 power_dialer.py                    # Start dialing
    python3 power_dialer.py --market austin    # Filter by market
    python3 power_dialer.py --industry "Law"   # Filter by industry
    python3 power_dialer.py --skip 10          # Start from prospect #10
"""

import json
import csv
import time
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install: pip install requests --break-system-packages")
    sys.exit(1)

# Try rich for better terminal UI, fall back to plain
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich import box
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False


# ============================================================
# CONFIGURATION
# ============================================================
CONFIG = {
    "api_key": os.getenv("DIALPAD_API_KEY", "YOUR_DIALPAD_API_KEY"),
    "user_id": os.getenv("DIALPAD_USER_ID", "YOUR_DIALPAD_USER_ID"),

    "sender_name": os.getenv("SENDER_NAME", "Your Name"),

    # Files
    "prospects_csv": "prospects.csv",
    "call_log": "call_log.csv",
    "state_file": "dialer_state.json",

    # DialPad Call Initiate rate limit: 5/min
    "min_delay_between_calls": 12,  # seconds (5/min = 1 per 12 sec)
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
            if _gui.get("sender_name"): CONFIG["sender_name"] = _gui["sender_name"]
    except Exception:
        pass


# ============================================================
# CALL SCRIPTS
# ============================================================
SCRIPTS = {
    "opener": (
        "Hi, is this {first_name}? Great — this is {sender_name} from BVTech.\n"
        "I work with {industry} businesses in {city} to handle their IT so\n"
        "they can focus on growing their business. Do you have about 2 minutes?"
    ),
    "pitch": (
        "We're a managed IT company here in Texas. What we do differently\n"
        "is we act as your entire IT department — helpdesk, cybersecurity,\n"
        "cloud, backups — for a flat monthly fee.\n\n"
        "Most of our {industry} clients pay between $100-$150 per user\n"
        "per month and they get enterprise-level support."
    ),
    "qualifying": [
        "How many employees do you currently have?",
        "Who handles your IT right now — in-house, another MSP, or DIY?",
        "What's your biggest IT headache right now?",
        "Have you had any security incidents or close calls recently?",
        "Are you using Microsoft 365 or Google Workspace?",
    ],
    "objections": {
        "We already have IT": (
            "That's great — I'm not trying to replace anyone. A lot of our\n"
            "clients started as co-managed situations where we filled in gaps.\n"
            "Would it be worth comparing what you're getting vs. what we offer?"
        ),
        "Not interested": (
            "Totally understand. Before I let you go — are you at least\n"
            "confident your data is backed up and your team is protected from\n"
            "ransomware? Because if there's even a question mark there, our\n"
            "free security assessment could give you peace of mind."
        ),
        "Too expensive": (
            "I hear you. What most business owners don't realize is that one\n"
            "ransomware attack averages $200K for a small business. Our clients\n"
            "typically invest $1,500-$3,000/month and avoid six-figure disasters.\n"
            "Would it help to see the ROI breakdown?"
        ),
        "Send me info": (
            "Absolutely — what's the best email? I'll send over a quick\n"
            "one-pager and our case study from a {industry} client in {city}.\n"
            "When would be a good time to follow up — Thursday or Friday?"
        ),
        "Call back later": (
            "Of course. When works best for you? I'll put it on my calendar\n"
            "right now."
        ),
    },
    "closer": (
        "I'd love to set up a 15-minute demo where I can show you exactly\n"
        "what this looks like for {company}. Would Tuesday or Thursday work\n"
        "better for you?"
    ),
}

DISPOSITIONS = [
    "Interested",
    "Booked Meeting",
    "Not Interested",
    "Left Voicemail",
    "No Answer",
    "Call Back",
    "Wrong Number",
    "Gatekeeper",
    "DNC Request",
]


# ============================================================
# DIALPAD CALL CLIENT
# ============================================================
class DialPadCallClient:
    """Initiate calls via DialPad API."""

    BASE_URL = "https://dialpad.com/api/v2"

    def __init__(self, api_key, user_id):
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def initiate_call(self, phone_number):
        """
        Trigger outbound call via DialPad API.
        This rings the user's DialPad app and then dials the prospect.
        Rate limit: 5 per minute.
        """
        payload = {
            "phone_number": phone_number,
        }
        try:
            response = self.session.post(
                f"{self.BASE_URL}/users/{self.user_id}/initiate_call",
                json=payload,
                timeout=15,
            )
            if response.status_code == 200:
                return True, "Call initiated", response.json()
            elif response.status_code == 429:
                return False, "Rate limited. Wait 12+ seconds between calls.", None
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}", None
        except requests.exceptions.RequestException as e:
            return False, f"Request error: {str(e)}", None


# ============================================================
# POWER DIALER ENGINE
# ============================================================
class PowerDialer:
    """Interactive power dialer with on-screen scripts."""

    def __init__(self, config, market=None, industry=None, skip=0):
        self.config = config
        self.market_filter = market
        self.industry_filter = industry
        self.skip = skip
        self.state = self._load_state()
        self.session_stats = {
            "calls": 0, "connected": 0, "meetings": 0,
            "voicemails": 0, "no_answer": 0, "not_interested": 0,
            "total_duration": 0,
        }
        self.call_client = DialPadCallClient(config["api_key"], config["user_id"])

    def _load_state(self):
        state_file = Path(self.config["state_file"])
        if state_file.exists():
            return json.loads(state_file.read_text())
        return {"called": {}, "dnc": [], "total_calls": 0}

    def _save_state(self):
        Path(self.config["state_file"]).write_text(json.dumps(self.state, indent=2))

    def _load_prospects(self):
        prospects = []
        csv_path = Path(self.config["prospects_csv"])
        if not csv_path.exists():
            self._print_error(f"Prospects CSV not found: {csv_path}")
            return []

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone = row.get("phone", "").strip()
                if not phone or phone in self.state["dnc"]:
                    continue
                if self.market_filter and row.get("market", "").lower() != self.market_filter.lower():
                    if self.market_filter.lower() not in row.get("city", "").lower():
                        continue
                if self.industry_filter and self.industry_filter.lower() not in row.get("industry", "").lower():
                    continue
                prospects.append(row)

        return prospects[self.skip:]

    def _fill_script(self, text, prospect):
        return text.format(
            first_name=prospect.get("first_name", "there"),
            company=prospect.get("company", "your company"),
            city=prospect.get("city", "Texas"),
            industry=prospect.get("industry", "business"),
            sender_name=self.config["sender_name"],
        )

    def _log_call(self, prospect, disposition, duration, notes=""):
        log_file = Path(self.config["call_log"])
        write_header = not log_file.exists()
        with open(log_file, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["timestamp", "phone", "name", "company", "industry", "city",
                                 "disposition", "duration_sec", "notes"])
            writer.writerow([
                datetime.now().isoformat(),
                prospect.get("phone"),
                f"{prospect.get('first_name')} {prospect.get('last_name')}",
                prospect.get("company"),
                prospect.get("industry"),
                prospect.get("city"),
                disposition,
                duration,
                notes,
            ])

    def _print_header(self):
        if HAS_RICH:
            console.print(Panel(
                "[bold cyan]BVTech MSP Power Dialer[/bold cyan]\n"
                "[dim]Auto-calling system with live scripts[/dim]",
                box=box.DOUBLE, border_style="blue"
            ))
        else:
            print("=" * 60)
            print("  BVTech MSP Power Dialer")
            print("  Auto-calling system with live scripts")
            print("=" * 60)

    def _print_prospect(self, prospect, index, total):
        if HAS_RICH:
            table = Table(box=box.ROUNDED, border_style="blue", show_header=False)
            table.add_column("Field", style="dim", width=14)
            table.add_column("Value", style="bold")
            table.add_row("Prospect", f"#{index + 1} of {total}")
            table.add_row("Name", f"{prospect.get('first_name')} {prospect.get('last_name')}")
            table.add_row("Company", prospect.get("company", "N/A"))
            table.add_row("Industry", prospect.get("industry", "N/A"))
            table.add_row("City", f"{prospect.get('city', 'N/A')}, TX")
            table.add_row("Phone", prospect.get("phone", "N/A"))
            table.add_row("Employees", prospect.get("employees", "N/A"))
            table.add_row("Score", prospect.get("score", "N/A"))
            console.print(table)
        else:
            print(f"\n--- Prospect #{index + 1} of {total} ---")
            print(f"  Name:      {prospect.get('first_name')} {prospect.get('last_name')}")
            print(f"  Company:   {prospect.get('company')}")
            print(f"  Industry:  {prospect.get('industry')}")
            print(f"  City:      {prospect.get('city')}, TX")
            print(f"  Phone:     {prospect.get('phone')}")
            print(f"  Employees: {prospect.get('employees')}")

    def _print_script(self, prospect, section="opener"):
        if section == "opener":
            text = self._fill_script(SCRIPTS["opener"], prospect)
            label = "OPENING SCRIPT"
            color = "cyan"
        elif section == "pitch":
            text = self._fill_script(SCRIPTS["pitch"], prospect)
            label = "VALUE PITCH"
            color = "magenta"
        elif section == "qualifying":
            text = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(SCRIPTS["qualifying"]))
            label = "QUALIFYING QUESTIONS"
            color = "green"
        elif section == "objections":
            parts = []
            for obj, resp in SCRIPTS["objections"].items():
                parts.append(f'  "{obj}"\n  → {self._fill_script(resp, prospect)}\n')
            text = "\n".join(parts)
            label = "OBJECTION HANDLERS"
            color = "yellow"
        elif section == "closer":
            text = self._fill_script(SCRIPTS["closer"], prospect)
            label = "CLOSER"
            color = "red"
        else:
            return

        if HAS_RICH:
            console.print(Panel(text, title=f"[bold]{label}[/bold]", border_style=color))
        else:
            print(f"\n=== {label} ===")
            print(text)

    def _print_error(self, msg):
        if HAS_RICH:
            console.print(f"[bold red]ERROR:[/bold red] {msg}")
        else:
            print(f"ERROR: {msg}")

    def _print_stats(self):
        stats = self.session_stats
        if HAS_RICH:
            table = Table(title="Session Stats", box=box.SIMPLE, border_style="blue")
            table.add_column("Metric", style="dim")
            table.add_column("Value", justify="right", style="bold")
            table.add_row("Calls Made", str(stats["calls"]))
            table.add_row("Connected", str(stats["connected"]))
            table.add_row("Meetings Booked", f"[green]{stats['meetings']}[/green]")
            table.add_row("Voicemails", str(stats["voicemails"]))
            table.add_row("No Answer", str(stats["no_answer"]))
            table.add_row("Not Interested", str(stats["not_interested"]))
            avg = stats["total_duration"] // max(stats["connected"], 1)
            table.add_row("Avg Call Duration", f"{avg // 60}m {avg % 60}s")
            connect_rate = (stats["connected"] / max(stats["calls"], 1)) * 100
            table.add_row("Connect Rate", f"{connect_rate:.0f}%")
            console.print(table)
        else:
            print(f"\n--- Session Stats ---")
            print(f"  Calls: {stats['calls']}  Connected: {stats['connected']}  Meetings: {stats['meetings']}")
            print(f"  No Answer: {stats['no_answer']}  Not Interested: {stats['not_interested']}")

    def run(self):
        """Main dialer loop."""
        self._print_header()

        prospects = self._load_prospects()
        if not prospects:
            self._print_error("No prospects loaded. Check your CSV file.")
            return

        if HAS_RICH:
            console.print(f"\n[bold]Loaded {len(prospects)} prospects[/bold]")
            if self.market_filter:
                console.print(f"[dim]Filtered by market: {self.market_filter}[/dim]")
            if self.industry_filter:
                console.print(f"[dim]Filtered by industry: {self.industry_filter}[/dim]")
        else:
            print(f"\nLoaded {len(prospects)} prospects")

        for i, prospect in enumerate(prospects):
            print("\n" + "=" * 60)
            self._print_prospect(prospect, i, len(prospects))

            # Show opening script by default
            self._print_script(prospect, "opener")

            # Action prompt
            while True:
                if HAS_RICH:
                    action = Prompt.ask(
                        "\n[bold]Action[/bold]",
                        choices=["call", "skip", "script", "stats", "quit"],
                        default="call"
                    )
                else:
                    print("\nActions: [call] dial  [skip] next  [script] view scripts  [stats] see stats  [quit] exit")
                    action = input("Action (call): ").strip().lower() or "call"

                if action == "quit":
                    self._print_stats()
                    self._save_state()
                    print("\nSession ended. Call log saved.")
                    return

                elif action == "stats":
                    self._print_stats()
                    continue

                elif action == "skip":
                    break

                elif action == "script":
                    if HAS_RICH:
                        section = Prompt.ask(
                            "Script section",
                            choices=["opener", "pitch", "qualifying", "objections", "closer"],
                            default="pitch"
                        )
                    else:
                        section = input("Section (opener/pitch/qualifying/objections/closer): ").strip() or "pitch"
                    self._print_script(prospect, section)
                    continue

                elif action == "call":
                    phone = prospect.get("phone", "").strip()
                    if not phone:
                        self._print_error("No phone number!")
                        break

                    print(f"\n📞 Dialing {phone}...")
                    call_start = time.time()

                    success, detail, response = self.call_client.initiate_call(phone)
                    if success:
                        print("✅ Call initiated — your DialPad app should be ringing now.")
                        print("Speak with the prospect. Press Enter when the call ends.\n")

                        # Show all script sections for reference
                        self._print_script(prospect, "pitch")
                        self._print_script(prospect, "qualifying")

                        input("\n⏎ Press ENTER when the call is complete...")
                    else:
                        print(f"❌ Call failed: {detail}")
                        print("You can try manual dial or skip to next prospect.")

                    call_duration = int(time.time() - call_start)
                    self.session_stats["calls"] += 1
                    self.state["total_calls"] += 1

                    # Disposition
                    print("\nDisposition:")
                    for j, disp in enumerate(DISPOSITIONS):
                        print(f"  {j+1}. {disp}")

                    if HAS_RICH:
                        choice = Prompt.ask("Enter number", default="5")
                    else:
                        choice = input("Enter number (5=No Answer): ").strip() or "5"

                    try:
                        disp_index = int(choice) - 1
                        disposition = DISPOSITIONS[disp_index] if 0 <= disp_index < len(DISPOSITIONS) else "No Answer"
                    except ValueError:
                        disposition = "No Answer"

                    # Update stats
                    if disposition in ["Interested", "Booked Meeting", "Call Back", "Gatekeeper"]:
                        self.session_stats["connected"] += 1
                        self.session_stats["total_duration"] += call_duration
                    if disposition == "Booked Meeting":
                        self.session_stats["meetings"] += 1
                    if disposition == "No Answer":
                        self.session_stats["no_answer"] += 1
                    if disposition == "Left Voicemail":
                        self.session_stats["voicemails"] += 1
                    if disposition == "Not Interested":
                        self.session_stats["not_interested"] += 1
                    if disposition == "DNC Request":
                        self.state["dnc"].append(phone)

                    notes = input("Notes (optional): ").strip()
                    self._log_call(prospect, disposition, call_duration, notes)
                    self.state["called"][phone] = {
                        "disposition": disposition,
                        "date": datetime.now().isoformat(),
                    }
                    self._save_state()

                    print(f"\n✅ Logged: {disposition} ({call_duration}s)")

                    # Rate limit delay
                    time.sleep(self.config["min_delay_between_calls"])
                    break

        self._print_stats()
        self._save_state()
        print("\n🎉 All prospects called! Session complete.")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BVTech MSP Power Dialer")
    parser.add_argument("--market", help="Filter by market (austin/sanAntonio/houston)")
    parser.add_argument("--industry", help="Filter by industry keyword")
    parser.add_argument("--skip", type=int, default=0, help="Skip N prospects")
    args = parser.parse_args()

    dialer = PowerDialer(
        config=CONFIG,
        market=args.market,
        industry=args.industry,
        skip=args.skip,
    )
    dialer.run()


if __name__ == "__main__":
    main()
