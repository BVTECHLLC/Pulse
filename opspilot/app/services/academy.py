"""v1.2 Pulse Cyber Academy — gamified security-awareness training, built in.

The MSP pitch: security awareness is a per-seat product (KnowBe4 et al). Pulse
ships it native: every portal user (staff AND client employees) gets a
mobile-first trainer with XP, levels, daily streaks, badges, a leaderboard,
server-graded quizzes, and interactive games. Staff see who's actually trained.

Design rules:
  * Quiz/game ANSWERS never leave the server — the catalog/lesson endpoints
    strip them; grading happens in submit endpoints. No view-source cheating.
  * XP is awarded once per item (retakes re-grade but don't re-award).
  * Streaks count consecutive UTC days with at least one completion.
  * Leaderboard is tenant-isolated: client users compete within their company;
    staff see everyone.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import AcademyCompletion, AcademyProfile, User

# --------------------------------------------------------------------------- #
# Content. Answers live server-side only.
# --------------------------------------------------------------------------- #
LESSON_XP = 50
PERFECT_BONUS = 25
GAME_XP = 75

LEVELS = ["Rookie", "Analyst", "Defender", "Sentinel", "Guardian",
          "Hunter", "Ranger", "Warden", "Cyber Ninja", "Legend"]
LEVEL_XP = 250   # per level

BADGES = {
    "first_steps":  {"icon": "🐣", "name": "First Steps", "desc": "Complete your first lesson"},
    "quiz_perfect": {"icon": "💯", "name": "Perfectionist", "desc": "Ace a quiz with a perfect score"},
    "phish_master": {"icon": "🎣", "name": "Phish Master", "desc": "Perfect score on Phish or Legit?"},
    "lab_rat":      {"icon": "🧪", "name": "Lab Rat", "desc": "Forge an uncrackable passphrase in the Password Lab"},
    "streak_3":     {"icon": "🔥", "name": "On Fire", "desc": "3-day learning streak"},
    "streak_7":     {"icon": "🌋", "name": "Unstoppable", "desc": "7-day learning streak"},
    "half_way":     {"icon": "⛰️", "name": "Halfway Up", "desc": "Complete half of all lessons"},
    "all_lessons":  {"icon": "🎓", "name": "Graduate", "desc": "Complete every lesson"},
    "xp_500":       {"icon": "⚡", "name": "Charged Up", "desc": "Earn 500 XP"},
    # --- Cyber Range (hands-on labs) ---
    "first_flag":   {"icon": "🚩", "name": "First Blood", "desc": "Capture your first flag in the Cyber Range"},
    "range_5":      {"icon": "🎯", "name": "Range Regular", "desc": "Solve 5 Cyber Range labs"},
    "range_all":    {"icon": "🏴‍☠️", "name": "Range Master", "desc": "Capture every flag in the Cyber Range"},
    "l33t":         {"icon": "💀", "name": "l33t", "desc": "Solve a Hard-difficulty lab"},
}

MODULES = [
    {
        "id": "human-firewall", "title": "The Human Firewall", "icon": "🛡️",
        "blurb": "90% of breaches start with a person, not a machine. Make yourself the hardest target in the building.",
        "lessons": [
            {
                "id": "phishing-101", "title": "Spot the Phish", "minutes": 6, "icon": "🎣",
                "body": """
<p><b>Phishing is the #1 way companies get breached</b> — not elite hacking, just a
convincing email and one hurried click. The good news: phish almost always leak
the same five tells.</p>
<h4>The 5 tells</h4>
<ol>
<li><b>Urgency + fear.</b> "Your account will be closed in 24 hours." Real
companies don't threaten you on a timer; scammers do, because panic switches
your brain from thinking to reacting.</li>
<li><b>The sender doesn't match the name.</b> The display name says
"Microsoft Support" but the address is <code>helpdesk@micros0ft-verify.top</code>.
Always look at the actual address, on your phone too — tap the name to expand it.</li>
<li><b>Links that lie.</b> The text says <code>portal.office.com</code> but the
link goes somewhere else. <b>Hover before you click</b> (or long-press on
mobile) and read the real destination — right to left: the part just before the
first single "/" is the true domain.</li>
<li><b>Unexpected attachments.</b> Invoice you never ordered, "voicemail.html",
a zip from HR. If you didn't expect it, verify it in person or by phone first.</li>
<li><b>Generic greeting, weird grammar.</b> "Dear Costumer" from your own bank
is a costume, not a customer.</li>
</ol>
<h4>The 10-second habit</h4>
<p>Before acting on ANY email that asks you to click, pay, or log in:
<b>Stop → check the sender address → hover the link → ask "did I expect this?"</b>
If anything is off, report it to IT. Reporting a real email costs 30 seconds;
clicking a fake one can cost the company weeks.</p>
""",
                "quiz": [
                    {"q": "An email from 'IT Support <it-desk@yourc0mpany-support.net>' says your password expires in 2 hours. Best move?",
                     "choices": ["Click the link fast — passwords expiring is serious",
                                 "Reply asking if it's real",
                                 "Report it to IT and don't click — the domain is fake and the urgency is a pressure tactic",
                                 "Forward it to a coworker to ask what they think"],
                     "answer": 2,
                     "explain": "A look-alike domain (0 for o) plus a countdown is textbook phishing. Report it through your normal IT channel; never reply — you'd be talking to the attacker."},
                    {"q": "Where is the TRUE domain in https://login.microsoft.com.account-verify.top/reset ?",
                     "choices": ["microsoft.com", "login.microsoft.com", "account-verify.top", "reset"],
                     "answer": 2,
                     "explain": "Read right-to-left from the first single slash: the registrable domain is account-verify.top. Everything in front is decoration designed to fool you."},
                    {"q": "You DID click a phishing link and typed your password. What now?",
                     "choices": ["Delete the email and hope",
                                 "Change the password immediately AND tell IT right away",
                                 "Only change the password — no need to tell anyone",
                                 "Run antivirus and move on"],
                     "answer": 1,
                     "explain": "Speed matters twice: rotate the credential before it's used, and tell IT so they can check for logins you didn't make. Nobody good at security will blame you for reporting fast."},
                    {"q": "Which of these is the LEAST suspicious?",
                     "choices": ["An unexpected 'invoice.zip' from a vendor",
                                 "A DocuSign request you were told to expect on a call yesterday",
                                 "A voicemail notification as an .html attachment",
                                 "A password-reset email you never requested"],
                     "answer": 1,
                     "explain": "Expected + verified through another channel = the safe pattern. The other three are classic phishing payloads and pretexts."},
                ],
            },
            {
                "id": "passwords-mfa", "title": "Passwords & MFA That Actually Work", "minutes": 6, "icon": "🔐",
                "body": """
<p>Attackers don't guess passwords one by one — they try <b>billions per second</b>
against stolen databases, and they try your leaked password from one site on
every other site (that's "credential stuffing").</p>
<h4>Three rules cover 95% of it</h4>
<ol>
<li><b>Length beats complexity.</b> <code>Tr0ub4dor!</code> falls in hours;
<code>correct-horse-battery-staple</code> takes centuries. A 4-word random
passphrase is both stronger AND easier to remember than "P@ssw0rd2024!".</li>
<li><b>Never reuse across accounts.</b> One breach at a random forum shouldn't
unlock your email. Since nobody can memorize 80 unique passwords, use a
<b>password manager</b> — it remembers them, generates them, and (bonus) refuses
to autofill on fake look-alike sites.</li>
<li><b>Turn on MFA everywhere</b>, starting with email and banking. Even a
stolen password bounces off a second factor. Prefer an authenticator app or a
hardware key over SMS — SIM-swapping is real.</li>
</ol>
<h4>MFA fatigue — the new trick</h4>
<p>Attackers with your password will spam approval push notifications at 2am
hoping you tap "Approve" to make it stop. <b>An MFA prompt you didn't cause IS
the alarm</b> — deny it, and report it: someone has your password right now.</p>
<h4>Your email is the master key</h4>
<p>Every "forgot password" flow lands there. Give your email account your
longest passphrase and strongest MFA — protecting it protects everything else.</p>
""",
                "quiz": [
                    {"q": "Which password is strongest?",
                     "choices": ["P@ssw0rd2024!", "xK9#p", "maple-rocket-thursday-lantern", "CompanyName123!"],
                     "answer": 2,
                     "explain": "Four random words ≈ 44+ bits of entropy and climbing with each word. Short-but-symboly passwords fall to modern cracking rigs in hours."},
                    {"q": "You get an MFA push notification at 2am that you didn't trigger. What does it mean?",
                     "choices": ["A glitch — ignore it",
                                 "Approve it so the notifications stop",
                                 "Someone has your password and is trying to get in — deny and report, then change the password",
                                 "Your session expired"],
                     "answer": 2,
                     "explain": "The push only fires AFTER a correct password. Denying stops this attempt; reporting + rotating the password stops the next one. Never approve to silence it."},
                    {"q": "Why is reusing one strong password everywhere still dangerous?",
                     "choices": ["It isn't, if the password is strong",
                                 "Websites limit password length",
                                 "One breached site leaks it, then attackers replay it on your email, bank, and work accounts",
                                 "It's only risky for admins"],
                     "answer": 2,
                     "explain": "Credential stuffing is automated: leaked email+password combos are tried against hundreds of services within hours of a breach."},
                    {"q": "Which account deserves your strongest protection first?",
                     "choices": ["Streaming service", "Your primary email", "A news site login", "Wi-Fi password"],
                     "answer": 1,
                     "explain": "Email is the recovery hub for everything else — control someone's inbox and you can reset their whole life. Longest passphrase + strongest MFA go there first."},
                ],
            },
            {
                "id": "social-engineering", "title": "Social Engineering — Hacking Humans", "minutes": 7, "icon": "🎭",
                "body": """
<p>Why break through a firewall when you can just <b>ask someone to open the
door</b>? Social engineering attacks the wiring in your head: authority,
helpfulness, fear, and habit.</p>
<h4>The greatest hits</h4>
<ul>
<li><b>Pretexting:</b> a story that makes the request feel normal. "This is Dave
from the copier company, I need the Wi-Fi password to finish the install."</li>
<li><b>Vishing:</b> phishing by phone. "This is your bank's fraud department —
to verify your identity, read me the code we just texted you." (That code is
your MFA. The 'fraud department' is the fraud.)</li>
<li><b>Tailgating:</b> following an employee through a badge door, hands full
of coffee cups, counting on politeness.</li>
<li><b>Baiting:</b> a USB stick labeled "Layoffs Q3" in the parking lot.
Curiosity does the rest.</li>
<li><b>Quid pro quo:</b> "I'm from IT, I can fix your slow computer — just
install this remote-access tool."</li>
</ul>
<h4>The counter-move: verify out-of-band</h4>
<p>Whoever contacts YOU controls the channel. The fix is to <b>hang up and call
back on a number you already trust</b> — the number on the company website, the
extension in the directory, the coworker's known cell. Real banks, real IT, and
real vendors are never offended by a call-back. Scammers always are: they'll
pressure you to stay on the line. Pressure to skip verification IS the tell.</p>
<p><b>It's OK to be "rude."</b> Security beats politeness. Don't hold the badge
door for strangers, don't plug in found USB drives, and never read an MFA code
to anyone — no legitimate caller will ever ask.</p>
""",
                "quiz": [
                    {"q": "Your 'bank' calls about fraud and asks you to read back the 6-digit code they just texted you. That code is…",
                     "choices": ["A fraud-case number", "Your MFA code — reading it out hands the caller your account", "A survey PIN", "Harmless — banks do this"],
                     "answer": 1,
                     "explain": "The caller triggered a real login with your stolen password; the SMS is your MFA. No legitimate organization EVER asks you to read a security code aloud."},
                    {"q": "Best response to an unexpected caller claiming to be IT and requesting remote access?",
                     "choices": ["Give access — they said it's urgent",
                                 "Ask them technical questions to test them",
                                 "Hang up and call IT on the number you already know",
                                 "Ask for their employee ID and then comply"],
                     "answer": 2,
                     "explain": "Verify out-of-band, always. Scripts, IDs, and jargon are easy to fake; the phone number YOU dial is not."},
                    {"q": "You find a USB drive labeled 'Payroll 2026' by the entrance. What do you do?",
                     "choices": ["Plug it in to identify the owner", "Hand it to IT/security without plugging it in", "Take it home to check safely", "Leave it there"],
                     "answer": 1,
                     "explain": "Bait drives auto-run malware the moment they mount. Let IT handle it in an isolated environment — that label is chosen to make you curious."},
                    {"q": "Someone in a delivery uniform, arms full of boxes, waits for you to badge in. Security-correct move?",
                     "choices": ["Hold the door — it's polite",
                                 "Let them in but watch where they go",
                                 "Direct them to reception/front desk to sign in",
                                 "Ask them to badge in themselves once your door closes"],
                     "answer": 2,
                     "explain": "Tailgating exploits courtesy. Everyone enters through the process — reception exists exactly for this. A real courier expects it."},
                ],
            },
            {
                "id": "safe-browsing", "title": "Browsing & Downloads Without Regrets", "minutes": 5, "icon": "🌐",
                "body": """
<p>Most malware doesn't force its way in — <b>it's invited</b>, wearing the
costume of something you wanted: a free PDF converter, a cracked game, a
"required browser update".</p>
<h4>Download rules</h4>
<ul>
<li><b>Only from the source.</b> Get software from the vendor's real site or
your company's approved catalog — not the first ad in the search results.
Attackers BUY those ad slots for fake installer sites.</li>
<li><b>"Your Flash Player is out of date" is a scam</b> in 100% of cases —
browsers update themselves. A webpage telling you to install an update is a
webpage handing you malware.</li>
<li><b>Extensions are software too.</b> Every browser extension can read what
you type on every page. Install the minimum, from official stores only.</li>
</ul>
<h4>Reading the address bar (the padlock lie)</h4>
<p>The padlock means the connection is <i>encrypted</i> — NOT that the site is
<i>honest</i>. Phishing sites have padlocks too; certificates are free. What
matters is the <b>domain</b>: <code>micros0ft-login.top</code> with a padlock is
still a trap. Trust the name, not the lock.</p>
<h4>Pop-up "virus alerts"</h4>
<p>A webpage screaming YOUR COMPUTER IS INFECTED with a phone number is tech
support fraud. Real antivirus never asks you to call a number. Close the tab
(Ctrl+W / swipe it away); if it fights you, close the whole browser. Nothing
was actually scanning your machine.</p>
""",
                "quiz": [
                    {"q": "A download site's ad appears above the real vendor in search results. Why is that risky?",
                     "choices": ["Ads are slower", "Attackers buy ad slots to serve fake installers wrapped in malware", "It costs money", "It isn't risky — Google verifies ads"],
                     "answer": 1,
                     "explain": "Malvertising is a top infection vector: the fake site looks identical and the installer even works — with a payload alongside. Skip ads; go to the vendor's real domain."},
                    {"q": "A webpage says your browser is outdated and offers an update button. You should…",
                     "choices": ["Install it — updates are important", "Close the page; browsers update themselves from inside the browser", "Check the file with antivirus first, then run", "Update later"],
                     "answer": 1,
                     "explain": "'Browser update' pages are a classic malware costume. Real updates happen in the browser's own settings menu, never via a webpage prompt."},
                    {"q": "What does the padlock in the address bar actually guarantee?",
                     "choices": ["The site is legitimate", "The site has no malware", "The connection is encrypted — nothing about who's on the other end", "The site passed a security audit"],
                     "answer": 2,
                     "explain": "Certificates are free and automatic — most phishing sites have them. Encryption to a criminal is still a conversation with a criminal. Judge the domain."},
                    {"q": "A full-screen alert says you're infected and to call 'Microsoft' at a phone number. Real next step?",
                     "choices": ["Call — better safe than sorry", "Pay for the cleanup tool it offers", "Close the tab/browser; it's tech-support fraud", "Unplug the computer immediately"],
                     "answer": 2,
                     "explain": "No real security product shows a phone number in a browser popup. The 'technician' will install remote access and charge you to fix nothing — or worse."},
                ],
            },
        ],
    },
    {
        "id": "defend-business", "title": "Defend the Business", "icon": "🏢",
        "blurb": "The scams that empty company bank accounts and the response skills that stop a bad day becoming a bad month.",
        "lessons": [
            {
                "id": "bec", "title": "Business Email Compromise — the Billion-Dollar Scam", "minutes": 6, "icon": "💸",
                "body": """
<p>BEC is the most expensive cybercrime on earth — <b>more money lost than
ransomware</b> — and it needs zero malware. Just an email that convinces
someone to send money to the wrong place.</p>
<h4>The three costumes</h4>
<ul>
<li><b>The CEO in a hurry:</b> "I'm in meetings all day — need you to buy gift
cards for a client. Keep it between us." Spoofed or look-alike sender, urgency,
secrecy: the trifecta.</li>
<li><b>The vendor's new bank account:</b> a real-looking invoice with "we've
updated our banking details." Sometimes it comes from the vendor's REAL mailbox
— because the vendor got phished first.</li>
<li><b>The payroll switch:</b> "HR, please update my direct deposit" from an
employee's look-alike address.</li>
</ul>
<h4>The one control that defeats all of it</h4>
<p><b>Verify payment changes by voice, on a known number, every time.</b> Any
request to move money, change bank details, or buy gift cards gets a phone call
to the requester at the number you already have on file — never the number in
the email signature (the scammer wrote that too). No exceptions for urgency;
<i>urgency is the attack</i>.</p>
<p>💡 Gift cards are never a legitimate business payment. Any request to pay
anything with gift cards is fraud, full stop — it's untraceable cash for scammers.</p>
""",
                "quiz": [
                    {"q": "Your 'CFO' emails: urgent wire, new vendor account, keep it confidential. The correct process is…",
                     "choices": ["Wire it — the CFO outranks the process",
                                 "Reply asking for confirmation",
                                 "Call the CFO on their known number to verify before anything moves",
                                 "Wire half as a compromise"],
                     "answer": 2,
                     "explain": "Replying just reaches the attacker. Voice verification on a number you already have defeats spoofed AND compromised mailboxes. Real executives thank people who verify."},
                    {"q": "A long-time vendor emails new banking details from their genuine email address. Why still verify by phone?",
                     "choices": ["No need — the address is real",
                                 "Their mailbox may be compromised; the email being real doesn't mean the request is",
                                 "Banks verify transfers anyway",
                                 "Only new vendors are risky"],
                     "answer": 1,
                     "explain": "Vendor-mailbox takeover is exactly how the biggest BEC losses happen: attackers lurk in the real inbox and send the switch at invoice time. Call the contact you know."},
                    {"q": "Any request to pay a business expense in gift cards is…",
                     "choices": ["Normal for client appreciation", "OK if under $500", "Fraud, always — no legitimate business pays in gift cards", "Fine if the CEO asks"],
                     "answer": 2,
                     "explain": "Gift card codes are anonymous, instant, and unrecoverable — criminal cash. This request pattern has a 100% fraud rate."},
                    {"q": "What makes 'urgency + secrecy' such a strong warning combination?",
                     "choices": ["Executives are never busy",
                                 "It's designed to stop you from doing the one thing that kills the scam: checking with someone",
                                 "Secret projects are illegal",
                                 "It violates email etiquette"],
                     "answer": 1,
                     "explain": "Every step of BEC is engineered to isolate you and rush you. The verification call they're trying to prevent is precisely the move that saves the money."},
                ],
            },
            {
                "id": "ransomware", "title": "Ransomware — Before, During, After", "minutes": 6, "icon": "🔒",
                "body": """
<p>Ransomware encrypts every file it can reach, then charges for the key — and
modern crews <b>steal a copy first</b> so they can threaten to leak it too.
Understanding the timeline is your defense.</p>
<h4>BEFORE (where you have power)</h4>
<ul>
<li>It arrives like everything else: phishing attachments, fake updates,
stolen passwords. Every lesson in this academy is ransomware prevention.</li>
<li><b>Updates matter:</b> those "restart to install updates" nags patch the
exact holes ransomware uses to spread. Restart the machine.</li>
<li><b>Backups are the ultimate uno-reverse</b> — but only offline/immutable
ones. Ransomware hunts and encrypts backup drives that stay connected.</li>
</ul>
<h4>DURING (minutes matter)</h4>
<ol>
<li>Files won't open, extensions look weird, a ransom note appears, the fan
screams: <b>disconnect from the network immediately</b> — pull the cable,
kill the Wi-Fi. Encryption spreads to shared drives fast.</li>
<li><b>Don't power off</b> unless told to — memory can hold recovery keys that
responders need.</li>
<li><b>Call IT/your MSP now.</b> Phone beats email — email may be compromised
or down.</li>
</ol>
<h4>AFTER</h4>
<p>Don't negotiate or pay on your own — that's an executive + insurance + legal
decision. Recovery happens from backups on rebuilt machines. And the honest
truth: paying gets a working key only ~half the time.</p>
""",
                "quiz": [
                    {"q": "Your files stop opening and a README_DECRYPT note appears. FIRST move?",
                     "choices": ["Power off immediately", "Disconnect from the network (cable/Wi-Fi), leave it on, call IT", "Pay quickly for the discount", "Reboot to see if it clears"],
                     "answer": 1,
                     "explain": "Isolation stops it spreading to shared drives and other machines. Staying powered on preserves memory that may hold keys. Then humans-who-do-this-daily take over."},
                    {"q": "Why must at least one backup be offline or immutable?",
                     "choices": ["Cloud storage is expensive", "Ransomware deliberately finds and encrypts connected backups first", "Tapes are faster", "Compliance paperwork"],
                     "answer": 1,
                     "explain": "Crews know backups kill their leverage — encrypting or deleting them is step one of the playbook. A copy nothing can write to is the copy that saves you."},
                    {"q": "How do most ransomware infections actually begin?",
                     "choices": ["Sophisticated zero-day exploits", "Phishing, stolen passwords, and unpatched systems", "Infected hardware from the factory", "Bluetooth attacks"],
                     "answer": 1,
                     "explain": "The boring answer is the true one: the same human-targeted tricks in your earlier lessons. That's why awareness training IS ransomware defense."},
                    {"q": "Modern ransomware crews steal data before encrypting so they can…",
                     "choices": ["Sell your storage back", "Extort twice: pay for the key AND pay to prevent a public leak", "Train AI models", "Frame someone else"],
                     "answer": 1,
                     "explain": "'Double extortion' means even perfect backups don't erase the leak threat — which is why prevention and fast reporting beat any recovery plan."},
                ],
            },
            {
                "id": "data-handling", "title": "Data Handling — Loose Files Sink Companies", "minutes": 5, "icon": "📁",
                "body": """
<p>Not every breach is a hack. A spreadsheet emailed to the wrong "Steve", a
client list synced to a personal Dropbox, a laptop on a train — <b>data walks
out the door through everyday convenience</b>.</p>
<h4>Know your data classes</h4>
<ul>
<li><b>Public:</b> marketing site content. Share freely.</li>
<li><b>Internal:</b> org charts, processes, pricing. Keep inside company systems.</li>
<li><b>Confidential:</b> client data, contracts, credentials, health/financial
records. Named people only, encrypted in transit, never on personal accounts.</li>
</ul>
<h4>The habits that prevent 90% of leaks</h4>
<ol>
<li><b>Check the recipient twice</b> — autocomplete loves sending payroll to
the wrong Steve. For anything sensitive, pause on the To: line.</li>
<li><b>Company data lives in company systems.</b> Personal email, personal
cloud drives, and random "free PDF tools" are data exfiltration you did to
yourself. (That free converter keeps a copy.)</li>
<li><b>Share links with limits:</b> specific people, expiry dates — not
"anyone with the link" for a client contract.</li>
<li><b>Screens travel:</b> lock your machine (Win+L / Ctrl+Cmd+Q) every time
you stand up; mind who reads over your shoulder on planes.</li>
<li><b>When someone leaves,</b> access leaves with them — offboarding is a
security event, tell IT the same day.</li>
</ol>
""",
                "quiz": [
                    {"q": "You need to work on a client spreadsheet at home tonight. Safe route?",
                     "choices": ["Email it to your personal Gmail", "Upload to your personal Dropbox", "Use the company's approved remote access / cloud drive", "USB stick in your pocket"],
                     "answer": 2,
                     "explain": "Personal accounts have no company protection, no audit trail, and outlive your employment. Company channels exist exactly for this — and they're usually just as convenient."},
                    {"q": "Fastest way to leak payroll data, statistically?",
                     "choices": ["Nation-state hackers", "Email autocomplete picking the wrong recipient", "Database exploits", "Dumpster diving"],
                     "answer": 1,
                     "explain": "Misdirected email is the most common data-loss incident in almost every industry's stats. The two-second To:-line check is the highest-ROI habit in this course."},
                    {"q": "A free online 'PDF to Word' tool for a confidential contract is risky because…",
                     "choices": ["Conversion may have typos", "You upload the document to an unknown server that may keep and mine it", "It's slower than Word", "The formatting might break"],
                     "answer": 1,
                     "explain": "'Free' converters are fed by the documents themselves. Your confidential contract just became someone's dataset. Use licensed company tools."},
                    {"q": "'Anyone with the link can view' on a client contract share is…",
                     "choices": ["Fine — the link is long and random", "A leak waiting to happen: links get forwarded, indexed, and pasted into chats", "Required for external sharing", "Safe if you delete it in a month"],
                     "answer": 1,
                     "explain": "Unrestricted links escape: chat logs, forwarded threads, browser history, even search indexes. Name the recipients and set an expiry — modern share dialogs make it one click."},
                ],
            },
            {
                "id": "incident-response", "title": "See Something, Say Something — Fast", "minutes": 5, "icon": "🚨",
                "body": """
<p>Here's a security secret: <b>the difference between a near-miss and a
disaster is usually reporting speed</b>, not technical genius. Attackers need
hours to turn a foothold into damage. Every minute between "that was weird" and
"I told IT" belongs to them.</p>
<h4>Report these immediately (even if you're not sure)</h4>
<ul>
<li>You clicked a link or opened an attachment, then got a bad feeling</li>
<li>You typed a password on a page that didn't log you in properly</li>
<li>An MFA prompt you didn't cause</li>
<li>Your browser has a new toolbar/extension you didn't add, or your
homepage changed</li>
<li>Files renamed, encrypted, or missing; a coworker "acting weird" on chat
asking for money/credentials</li>
<li>A lost or stolen laptop or phone — <b>this one is a race</b></li>
</ul>
<h4>Why people report late (and why they shouldn't)</h4>
<p>Embarrassment. "Maybe it's nothing." "I'll get in trouble." Flip it: security
teams <b>love</b> early reporters — you're the sensor network. The person who
reports a click within 5 minutes is a hero; the click itself is Tuesday. A good
company treats fast reporting as the win it is, and blame as the security hole
it creates.</p>
<h4>How to report well</h4>
<p><b>What you saw → what you did → when.</b> "Got an invoice email at 2:14, I
clicked the link and entered my password, realized at 2:20, reporting now." is
a perfect report. Don't forward the phish to coworkers to crowd-source opinions
— that just spreads live bait. Report through your IT/MSP channel.</p>
""",
                "quiz": [
                    {"q": "You entered your password on a site that then just... didn't work. It's probably nothing. You should…",
                     "choices": ["Move on — it was a glitch", "Try a different browser", "Report it now and change the password — 'login that goes nowhere' is THE credential-theft signature", "Wait to see if anything odd happens"],
                     "answer": 2,
                     "explain": "Phishing pages take your password then error out or redirect to the real site. The awkward report beats explaining next week why the attacker had a 5-day head start."},
                    {"q": "Which detail matters MOST in an incident report?",
                     "choices": ["Perfect grammar", "The time things happened and what you did, even the embarrassing parts", "Who else might be to blame", "Screenshots in a nice document"],
                     "answer": 1,
                     "explain": "Responders reconstruct a timeline: what/when/did-you-act tells them exactly where to look and what to lock. Honesty about the click is what makes the report useful."},
                    {"q": "Why is forwarding a suspicious email to coworkers ('is this legit?') a bad idea?",
                     "choices": ["It clutters inboxes", "You just distributed live phishing bait — someone else may click it", "IT prefers tickets", "It ruins the evidence"],
                     "answer": 1,
                     "explain": "Every forward multiplies the chance of a click. One report to IT protects everyone at once — they can purge it from all mailboxes centrally."},
                    {"q": "A company laptop disappears from your car. When do you report it?",
                     "choices": ["After checking with the police first", "Tomorrow at the office", "Immediately, day or night — remote lock/wipe is a race against whoever has it", "After trying Find My Device yourself"],
                     "answer": 2,
                     "explain": "IT can lock, wipe, and rotate credentials remotely — but only before the data is extracted. This is one of the few genuine call-someone-at-night events."},
                ],
            },
        ],
    },
    {
        "id": "everywhere-security", "title": "Security Everywhere", "icon": "📱",
        "blurb": "Coffee shops, airports, your couch, your pocket — the office has no walls anymore.",
        "lessons": [
            {
                "id": "wifi-travel", "title": "Public Wi-Fi, Travel & Remote Work", "minutes": 5, "icon": "✈️",
                "body": """
<p>The network name says "Airport_Free_WiFi". Who runs it? <b>You have no
idea</b> — and anyone can broadcast any network name from a laptop in a
backpack ("evil twin" attacks are point-and-click easy).</p>
<h4>Public network rules</h4>
<ul>
<li><b>Prefer your phone's hotspot</b> — LTE/5G beats coffee-shop Wi-Fi for
anything sensitive. It's the simplest upgrade you can make.</li>
<li><b>Use the company VPN</b> when on any network you don't control. It wraps
everything in encryption the network owner can't peek through.</li>
<li><b>No sensitive logins on captive portals.</b> That "log in with your email
password for free Wi-Fi" page? Never. Free Wi-Fi doesn't need your email
password — harvesters do.</li>
<li><b>Turn off auto-join.</b> Your phone happily reconnects to any network
named like one it remembers ("attwifi" anyone?). Forget public networks after
using them.</li>
</ul>
<h4>Physical side of travel</h4>
<ul>
<li><b>Shoulder surfing is the oldest attack:</b> privacy screens cost $30;
the seat next to you on a flight reads at zero cost.</li>
<li><b>USB charging ports at airports</b> can be data ports. Charge from your
own wall adapter, or use a data-blocker plug ("USB condom" — yes, really).</li>
<li><b>Hotel safes beat hotel desks;</b> your bag NEVER holds the only copy
of anything.</li>
</ul>
""",
                "quiz": [
                    {"q": "What's an 'evil twin' network?",
                     "choices": ["Two routers from one ISP", "An attacker's hotspot broadcasting a trusted name ('Airport_WiFi') so devices connect through them", "A mesh network extender", "A backup network"],
                     "answer": 1,
                     "explain": "Network names are just labels anyone can broadcast — your device can't tell real from fake. That's why VPN/hotspot habits matter more than picking the 'right' free Wi-Fi."},
                    {"q": "Best option for checking company email at a coffee shop?",
                     "choices": ["The shop's Wi-Fi, quickly", "Your phone's hotspot (or shop Wi-Fi + company VPN)", "Ask staff for the 'secure' network", "Neighboring store's Wi-Fi"],
                     "answer": 1,
                     "explain": "Cellular data bypasses the untrusted network entirely; a VPN encrypts through it. Either works — raw public Wi-Fi for work does not."},
                    {"q": "A captive portal offers free Wi-Fi if you log in with your email address AND email password. That's…",
                     "choices": ["Standard practice", "A credential harvest — no Wi-Fi system needs your email PASSWORD", "Required by law for identification", "Fine if the site has a padlock"],
                     "answer": 1,
                     "explain": "Wi-Fi portals may ask for an email ADDRESS for marketing; the password field is the scam. That's your inbox — the master key from Lesson 2 — being phished."},
                    {"q": "Why prefer your own wall charger over public USB ports?",
                     "choices": ["Public ports charge slower", "USB carries data as well as power — a rigged port can access the device ('juice jacking')", "Public power is unstable", "Cable hygiene"],
                     "answer": 1,
                     "explain": "The same cable that charges can sync. Wall power (or a data-blocker adapter) removes the risk entirely for the price of a keychain."},
                ],
            },
            {
                "id": "mobile-devices", "title": "Your Phone Is a Computer (Attackers Know)", "minutes": 5, "icon": "📲",
                "body": """
<p>Your phone holds your email, MFA codes, banking, company chat, and a
microphone — <b>it's the most valuable computer you own</b>, and it rides
around in your pocket getting texted by strangers.</p>
<h4>Smishing — phishing by text</h4>
<p>"USPS: your package needs a $0.30 redelivery fee", "Your bank: verify this
$900 charge", "Hi, is this Sarah? …wrong number" (that one plays the long
game). Texts get 10× the click rate of email because we trust the channel.
Same rules apply: <b>don't tap links in unexpected texts</b> — open the app or
site directly.</p>
<h4>Phone hygiene, the short list</h4>
<ol>
<li><b>Updates: install them.</b> Mobile exploits are patched in those boring
OS updates; "remind me later" forever means exploitable forever.</li>
<li><b>Apps from official stores only,</b> and check the permissions — a
flashlight app doesn't need your contacts. On Android, "sideloading" a
requested APK from a text/website is how banking trojans arrive.</li>
<li><b>Lock screen = 6-digit PIN or biometrics,</b> auto-lock ≤ 1 minute.
Face/fingerprint is both safer and faster than a 4-digit PIN.</li>
<li><b>Enable Find My / remote wipe NOW</b> — it only works if set up before
the phone disappears.</li>
<li><b>Bluetooth/AirDrop:</b> set AirDrop to Contacts Only — airport strangers
don't need to send you files.</li>
</ol>
<p>💡 One more: those "wrong number" texts that turn friendly? Romance/crypto
scam pipelines ("pig butchering"). Block, delete, don't be lonely-polite.</p>
""",
                "quiz": [
                    {"q": "Text from 'USPS': package held, tap link, pay $0.30. What's the play?",
                     "choices": ["Pay — it's only 30 cents", "Tap to check, pay nothing", "Delete/report; track packages only via the official app or site typed directly", "Reply STOP"],
                     "answer": 2,
                     "explain": "The 30 cents is bait for your card number. Carriers don't collect micro-fees by text. Replying (even STOP) confirms your number is live and gets you more scams."},
                    {"q": "Why do attackers love SMS more than email lately?",
                     "choices": ["Texts are cheaper to send", "People trust and act on texts far more, and phones hide sender details", "Emails are illegal to spoof", "SMS supports images"],
                     "answer": 1,
                     "explain": "Smishing click-rates dwarf email because the channel feels personal and the small screen hides the tells you learned to spot in email."},
                    {"q": "A website (not the app store) asks you to download and install its Android app (APK) to 'verify your account'. This is…",
                     "choices": ["Normal for smaller companies", "The standard delivery method for mobile banking trojans — refuse", "Safe if the site has HTTPS", "Fine after antivirus scan"],
                     "answer": 1,
                     "explain": "Sideloaded APKs skip every store protection and can overlay fake login screens on your real banking apps. Official stores only, always."},
                    {"q": "Which setup actually protects a lost phone's data?",
                     "choices": ["A clever wallpaper with your contact info", "Strong lock screen + Find My/remote wipe enabled BEFORE it was lost", "Keeping it in a case", "Insurance"],
                     "answer": 1,
                     "explain": "Biometric/PIN lock keeps the finder out; remote wipe ends the story. Neither can be added after the phone is gone — set them up today."},
                ],
            },
        ],
    },
    {
        "id": "cloud-identity", "title": "Cloud & Identity", "icon": "☁️",
        "blurb": "Your data doesn't live in a server closet anymore — it lives in Microsoft 365, Google, and a dozen SaaS apps. The keys to all of it are your identity. Learn to guard it.",
        "lessons": [
            {
                "id": "m365-security", "title": "Locking Down Microsoft 365 & Google Workspace", "minutes": 6, "icon": "🗄️",
                "body": """
<p>For most small businesses, <b>Microsoft 365 (or Google Workspace) IS the company</b> —
email, files, calendars, Teams/Meet, the works. Break into that one account and an
attacker has everything. The good news: a handful of settings stop the vast majority of
account takeovers.</p>
<h4>What attackers do once they're in your mailbox</h4>
<ol>
<li><b>Set a hidden forwarding rule</b> so a copy of every email silently goes to them —
they'll watch for invoices and wire instructions for weeks.</li>
<li><b>Reset passwords</b> on your other services (they all email <i>you</i> the reset link).</li>
<li><b>Email your contacts</b> from the real you, asking for payments or credentials —
and people trust it, because it's genuinely your address.</li>
</ol>
<h4>The settings that stop them</h4>
<ol>
<li><b>MFA on every account, no exceptions</b> — especially admins. A stolen password
alone becomes useless.</li>
<li><b>Block legacy authentication.</b> Old protocols (IMAP/POP/SMTP basic auth) skip MFA
entirely — attackers love them. Your admin should turn them off.</li>
<li><b>Alert on new forwarding rules and impossible travel</b> (a login from Texas and
Nigeria 10 minutes apart). These are the earliest signs of a takeover.</li>
<li><b>Review "enterprise apps" / OAuth grants</b> — a consent you clicked once can keep
reading your mail forever (next lesson).</li>
</ol>
<p>💡 If you're ever locked out or see mail you didn't send: <b>change the password, revoke
sessions, and check forwarding rules</b> — in that order — then call IT.</p>
""",
                "quiz": [
                    {"q": "An attacker gets into your M365 mailbox. What's the FIRST quiet thing they usually set up?",
                     "choices": ["A new company logo", "A hidden inbox-forwarding rule copying your mail to them",
                                 "An out-of-office reply", "A calendar invite"],
                     "answer": 1,
                     "explain": "Silent forwarding rules let them watch for invoices and wire details for weeks without you noticing. Check your rules if anything feels off."},
                    {"q": "Why does 'blocking legacy authentication' matter so much?",
                     "choices": ["It speeds up email", "Old mail protocols bypass MFA entirely, so attackers use them to skip your second factor",
                                 "It's required by law", "It saves storage"],
                     "answer": 1,
                     "explain": "IMAP/POP/SMTP basic auth predate MFA and ignore it. Turning them off closes the door attackers use to render your MFA irrelevant."},
                    {"q": "Which account most deserves the strongest protection?",
                     "choices": ["A shared info@ mailbox", "The Global Admin account", "A new hire's account", "The printer's account"],
                     "answer": 1,
                     "explain": "The admin can reset anyone, read anything, and disable protections. Admins should have MFA, no email in the admin account, and separate day-to-day logins."},
                ],
            },
            {
                "id": "oauth-consent", "title": "The Permission You Clicked 'Allow' On", "minutes": 5, "icon": "🔓",
                "body": """
<p>You've seen the screen: <i>"[Some App] wants to read your email and access your files —
Allow / Deny."</i> That's <b>OAuth consent</b>, and it's how modern apps connect without
your password. It's also a favorite attack: <b>consent phishing</b>.</p>
<h4>How the trap works</h4>
<p>An attacker sends a link to a real Microsoft/Google login page — nothing fake about it.
After you sign in, a permission screen asks you to "Allow" an app (often with a trustworthy
name like "Office365 Sync" or "Adobe Reader"). Tap Allow, and the app now has a <b>token</b>
that reads your mail and files — <b>even after you change your password</b>, and often <b>even
with MFA on</b>, because you already passed both. No password was stolen; you handed over a key.</p>
<h4>How to not get caught</h4>
<ol>
<li><b>Read the permissions, not the name.</b> Why does a PDF viewer need "read and send mail
as you" or "read all files"? That mismatch is the tell.</li>
<li><b>Check the publisher.</b> "Unverified publisher" on something asking for broad access = stop.</li>
<li><b>Only consent to apps you sought out</b> and expected to connect. Consent that arrives
via a link someone sent you is the whole scam.</li>
</ol>
<p>💡 Recovery is different here: changing your password does <b>not</b> revoke a granted app.
You (or your admin) must remove it under <b>My Apps → app permissions</b> (Microsoft) or
<b>myaccount.google.com → Security → Third-party access</b>.</p>
""",
                "quiz": [
                    {"q": "Why is consent phishing dangerous even with MFA enabled and a strong password?",
                     "choices": ["It isn't — MFA blocks it", "You pass MFA yourself, then hand the app a long-lived token that survives password changes",
                                 "It only works on admins", "MFA apps are immune"],
                     "answer": 1,
                     "explain": "The attack doesn't steal your password — it gets you to grant an app access AFTER you authenticate. The token keeps working until the app grant is removed."},
                    {"q": "An app named 'Adobe Document Cloud' asks to 'Read and send mail as you' and 'Read all files'. Best move?",
                     "choices": ["Allow — Adobe is trustworthy", "Deny — a document viewer has no business sending your mail; the permissions don't match the name",
                                 "Allow, then change your password", "Allow just the file access"],
                     "answer": 1,
                     "explain": "Judge the request by the permissions, not the friendly name. Broad mail/file access for a viewer is the signature of consent phishing."},
                    {"q": "You realize you granted a shady app last week. What actually stops it?",
                     "choices": ["Changing your password", "Running antivirus", "Removing the app's grant in your account's app-permissions page",
                                 "Deleting the original email"],
                     "answer": 2,
                     "explain": "Only revoking the grant kills the token. Password changes and antivirus don't touch an OAuth consent you already gave."},
                ],
            },
            {
                "id": "shadow-it", "title": "Shadow IT — the Apps Nobody Approved", "minutes": 5, "icon": "🌓",
                "body": """
<p><b>Shadow IT</b> is any app, account, or device people use for work that IT doesn't know
about: a free file-converter site, a personal Dropbox for "just this one big file," a
sign-up-with-Google to a random SaaS trial, an AI tool you pasted a client list into.</p>
<h4>Why well-meaning shortcuts hurt</h4>
<ol>
<li><b>Company data lands in accounts nobody controls.</b> When that employee leaves — or that
free service gets breached — your data goes with it, and you may never know it was there.</li>
<li><b>No MFA, no backups, no oversight.</b> Free tools rarely have the protections your
sanctioned apps do.</li>
<li><b>You can't protect what you can't see.</b> A breach of a tool IT doesn't know exists is a
breach you can't detect or contain.</li>
</ol>
<h4>The right instinct</h4>
<p>The goal isn't "never use new tools" — it's <b>ask first</b>. If a sanctioned tool is
missing or clunky, tell IT what you're trying to do; there's almost always an approved way, and
if not, they can vet the new one. <b>Never paste customer data, credentials, or internal
documents into a free online tool</b> to get a quick result — that "quick" convert/summarize/format
can permanently expose the data.</p>
<p>💡 Rule of thumb: if losing an account or app would leak company data, it needs to be known,
backed up, and MFA-protected — which means IT needs to know it exists.</p>
""",
                "quiz": [
                    {"q": "You need to compress a big client PDF fast and find a free website that does it. What's the risk?",
                     "choices": ["None, it's just a PDF", "You may be uploading client data to an unknown third party with no controls over what they keep",
                                 "It's slow", "The file gets bigger"],
                     "answer": 1,
                     "explain": "Free online tools often retain uploads. That 'quick' convert can hand a client document to a stranger. Use an approved tool or ask IT."},
                    {"q": "What's the core problem with Shadow IT from a security standpoint?",
                     "choices": ["It costs money", "You can't protect, back up, or monitor data in apps IT doesn't know exist",
                                 "It's against the rules for no reason", "It uses too much bandwidth"],
                     "answer": 1,
                     "explain": "Invisible tools can't be secured or watched. A breach there is one you can't detect or contain — the data is simply gone."},
                    {"q": "The best response when an approved tool is missing a feature you need?",
                     "choices": ["Quietly use a free alternative", "Ask IT what the approved way is — they can vet a new tool or point you to an existing one",
                                 "Do without and complain", "Use your personal accounts"],
                     "answer": 1,
                     "explain": "Asking first keeps data in controlled, backed-up, MFA-protected places. IT would rather approve a tool than discover it during a breach."},
                ],
            },
            {
                "id": "session-tokens", "title": "Cookie Theft — When MFA Isn't Enough", "minutes": 6, "icon": "🍪",
                "body": """
<p>You did everything right: strong password, MFA on. So how do attackers still get in? Often
they skip the login entirely and steal your <b>session cookie</b> — the little token your
browser holds <i>after</i> you sign in that says "this person is already authenticated."</p>
<h4>How the token gets stolen</h4>
<ol>
<li><b>Infostealer malware</b> (from a cracked app, a fake installer, a malicious ad) copies
the cookies out of your browser and ships them to the attacker.</li>
<li><b>The attacker imports your cookie</b> into their browser and is now "you" — logged in,
past MFA, no password needed.</li>
</ol>
<h4>How you shrink the risk</h4>
<ol>
<li><b>Don't run software from sketchy sources.</b> Cracked apps, "free" premium tools, and
fake update pop-ups are the #1 infostealer delivery.</li>
<li><b>Keep the browser and OS patched</b> — many token thefts ride known, already-fixed bugs.</li>
<li><b>Sign out of sensitive sites</b> when done on shared/public machines; closing the tab
isn't the same as ending the session.</li>
<li><b>Report a suddenly-signed-out or "new device" alert</b> — it can mean your session was
hijacked. IT can revoke all sessions, which invalidates the stolen cookie.</li>
</ol>
<p>💡 This is why "revoke sessions" / "sign out everywhere" exists and why device-compliance
policies (only healthy, managed devices may hold a session) are powerful — they make a stolen
cookie worthless on the attacker's machine.</p>
""",
                "quiz": [
                    {"q": "How can an attacker access your account without your password OR your MFA code?",
                     "choices": ["They can't", "By stealing your post-login session cookie and importing it into their browser",
                                 "By guessing faster", "By calling you"],
                     "answer": 1,
                     "explain": "A session cookie proves you already authenticated. Steal it and the attacker rides your existing session — no password, no MFA prompt."},
                    {"q": "What's the most common way session cookies get stolen?",
                     "choices": ["Someone reads them over your shoulder", "Infostealer malware from cracked/fake software copies them out of your browser",
                                 "Through the printer", "Public Wi-Fi always steals them"],
                     "answer": 1,
                     "explain": "Infostealers delivered by cracked apps and fake installers are the dominant source. Don't run software from untrusted sources."},
                    {"q": "You get a 'new device signed in' alert and were suddenly logged out. Best response?",
                     "choices": ["Ignore it, probably a glitch", "Just log back in", "Report to IT so they can revoke all sessions — a stolen cookie becomes useless once sessions are invalidated",
                                 "Turn off MFA to make logging in easier"],
                     "answer": 2,
                     "explain": "Revoking sessions kills the hijacked cookie. A sudden sign-out plus a new-device alert is a classic hijack signature worth reporting fast."},
                ],
            },
            {
                "id": "conditional-access", "title": "Why the Portal Asks Extra Questions", "minutes": 5, "icon": "🧭",
                "body": """
<p>Sometimes signing in is instant; other times you're asked for MFA again, or told "you can't
sign in from this device." That's <b>conditional access</b> (a.k.a. zero-trust sign-in): the
system weighs <i>who</i> you are, <i>where</i> you are, <i>what device</i> you're on, and
<i>how risky</i> the attempt looks — then decides allow, challenge, or block. It's friction on
purpose, and it's protecting you.</p>
<h4>What it's checking</h4>
<ol>
<li><b>Device health:</b> is this a known, patched, managed device — or a random PC?</li>
<li><b>Location & risk:</b> a login from an unusual country, or right after one somewhere else
("impossible travel"), gets challenged or blocked.</li>
<li><b>Sensitivity:</b> reading the menu is low-risk; changing bank details or admin settings
should demand fresh proof.</li>
</ol>
<h4>Your part</h4>
<ol>
<li><b>Don't try to route around it</b> — using a personal device or a VPN to dodge a block
defeats a control that's stopping attackers with your password.</li>
<li><b>Expect a re-prompt for sensitive actions.</b> Being asked to reauthenticate before a big
change is a feature, not a bug.</li>
<li><b>If you're wrongly blocked, tell IT</b> rather than finding a workaround — they can add a
legitimate device or location safely.</li>
</ol>
<p>💡 The principle behind all of it: <b>never trust, always verify</b>. Every request earns
access based on current signals — not on "you logged in once this morning."</p>
""",
                "quiz": [
                    {"q": "The portal asks you to re-verify with MFA right before you change payroll bank details. Why?",
                     "choices": ["A glitch", "Sensitive actions deserve fresh proof of identity — it's conditional access protecting a high-risk change",
                                 "To annoy you", "Because your password expired"],
                     "answer": 1,
                     "explain": "Step-up authentication on risky actions means a hijacked session still can't quietly redirect your payroll. Friction where it counts."},
                    {"q": "You're blocked from signing in on your personal laptop. The safe response is to…",
                     "choices": ["Use a VPN to appear elsewhere", "Borrow a coworker's login", "Ask IT to enroll a legitimate device — don't route around the control",
                                 "Turn off MFA"],
                     "answer": 2,
                     "explain": "The block is a control doing its job. Working around it (VPN, shared logins) is exactly what an attacker would do; ask IT for a sanctioned path."},
                    {"q": "What idea is conditional access / zero-trust built on?",
                     "choices": ["Trust anyone inside the network", "Never trust, always verify — evaluate each request by current signals",
                                 "One login lasts all day everywhere", "Passwords are enough"],
                     "answer": 1,
                     "explain": "Zero-trust grants access per-request based on identity, device, location, and risk — not on a single earlier login."},
                ],
            },
        ],
    },
    {
        "id": "compliance-privacy", "title": "Compliance, Privacy & New Threats", "icon": "📋",
        "blurb": "Rules like HIPAA, PCI, and NIST aren't red tape — they're the floor for keeping data safe and staying in business. Plus the newest tricks: AI voices, deepfakes, and QR scams.",
        "lessons": [
            {
                "id": "nist-csf", "title": "The NIST Cybersecurity Framework in Plain English", "minutes": 6, "icon": "🏛️",
                "body": """
<p>The <b>NIST Cybersecurity Framework (CSF)</b> is the most widely used map of "what good
security looks like." You don't need to memorize it — but understanding its <b>six functions</b>
tells you why your company does what it does, and where the gaps usually hide.</p>
<h4>The six functions</h4>
<ol>
<li><b>Govern</b> — someone owns security; there are policies, roles, and risk decisions. (Added
in CSF 2.0 and wrapped around the rest.)</li>
<li><b>Identify</b> — know what you have: devices, data, accounts, vendors. You can't protect
what you haven't inventoried.</li>
<li><b>Protect</b> — the guardrails: MFA, patching, least-privilege access, encryption, training
(like this).</li>
<li><b>Detect</b> — spot trouble fast: monitoring, alerts, EDR, "impossible travel" flags.</li>
<li><b>Respond</b> — a plan for when something happens: who to call, how to contain, what to say.</li>
<li><b>Recover</b> — get back to normal: tested backups, restoration steps, lessons learned.</li>
</ol>
<h4>Why it matters to you</h4>
<p>Every control you meet — MFA prompts, patch reminders, this training, the incident-report
button — slots into one of these. Security isn't random hoops; it's a balanced program. And the
most common failure isn't a fancy hack — it's a missing basic in <b>Identify</b> or <b>Protect</b>:
an unknown device, a stale admin account, an un-patched server.</p>
<p>💡 A memory hook: <b>G‑I‑P‑D‑R‑R</b> — Govern, Identify, Protect, Detect, Respond, Recover.
Prevention (Protect) matters, but so does assuming something will get through (Detect/Respond/Recover).</p>
""",
                "quiz": [
                    {"q": "A company only invests in prevention (firewalls, MFA) and ignores Detect/Respond/Recover. What's the flaw?",
                     "choices": ["Nothing — prevention is enough", "No plan or backups for when something inevitably gets through, so a breach becomes a catastrophe",
                                 "It's too expensive", "Firewalls are useless"],
                     "answer": 1,
                     "explain": "A mature program assumes some attacks succeed. Without detection, response, and tested recovery, one slip becomes an extinction event."},
                    {"q": "Which NIST function covers keeping a current inventory of devices, data, and accounts?",
                     "choices": ["Recover", "Identify", "Respond", "Detect"],
                     "answer": 1,
                     "explain": "Identify is knowing what you have. You can't protect, monitor, or recover assets you never inventoried — it's where many gaps begin."},
                    {"q": "Where does security-awareness training (like this) fit in the framework?",
                     "choices": ["Recover", "It doesn't", "Protect — reducing the chance an attack succeeds", "Govern only"],
                     "answer": 2,
                     "explain": "Training is a Protect control — it hardens the human layer, the most-attacked part of any organization."},
                ],
            },
            {
                "id": "hipaa-basics", "title": "HIPAA & Protected Health Info — the SMB Version", "minutes": 6, "icon": "⚕️",
                "body": """
<p>If your company touches health information — a clinic, a dental office, or a business that
<i>serves</i> them — <b>HIPAA</b> applies, and the penalties are real. You don't need to be a
compliance officer; you need to recognize <b>PHI</b> and handle it right.</p>
<h4>What counts as PHI (Protected Health Information)</h4>
<p>Health info tied to a person: diagnoses, treatments, appointment records, insurance details —
plus the identifiers attached (name, address, DOB, SSN, medical record numbers, even a face photo).
A spreadsheet of "patients who came in Tuesday" is PHI.</p>
<h4>The handling rules that matter day to day</h4>
<ol>
<li><b>Minimum necessary.</b> Only access and share the PHI needed for the task — not the whole
record because it's easier.</li>
<li><b>Encrypt it in motion and at rest.</b> PHI in a plain email or on an unencrypted laptop/USB
is a reportable breach waiting to happen. Use approved secure channels.</li>
<li><b>Never text/email PHI to personal accounts</b> or paste it into consumer AI tools.</li>
<li><b>Business Associate Agreements (BAAs):</b> any vendor that handles PHI for you (including
your IT provider and cloud apps) must have a signed BAA. No BAA, no PHI.</li>
</ol>
<h4>If PHI is exposed</h4>
<p>A lost laptop, a misdirected email, a ransomware hit — report it <b>immediately</b>. HIPAA has
strict breach-notification timelines, and fast internal reporting is what keeps a mistake from
becoming a fine. Hiding it is far worse than the original error.</p>
<p>💡 The safe instinct: treat every piece of health info like it's about someone you love —
because to someone, it is.</p>
""",
                "quiz": [
                    {"q": "Which of these is Protected Health Information (PHI)?",
                     "choices": ["A public flyer about flu season", "A list of patients seen Tuesday with their appointment reasons",
                                 "The clinic's business hours", "A generic health tip blog"],
                     "answer": 1,
                     "explain": "PHI is health info tied to identifiable people. A patient visit list with reasons is textbook PHI and must be protected accordingly."},
                    {"q": "What does 'minimum necessary' mean under HIPAA?",
                     "choices": ["Keep records as short as possible", "Only access/share the PHI actually needed for the task at hand",
                                 "Minimum staff", "Delete records monthly"],
                     "answer": 1,
                     "explain": "Minimum necessary limits exposure — you pull only the PHI the job requires, not the full record for convenience."},
                    {"q": "A vendor will store your patients' records. What must be in place first?",
                     "choices": ["A verbal promise", "A signed Business Associate Agreement (BAA)", "Nothing, if they're reputable", "A five-star review"],
                     "answer": 1,
                     "explain": "Any vendor handling PHI on your behalf needs a signed BAA making them legally accountable. No BAA means they must not touch PHI."},
                ],
            },
            {
                "id": "pci-basics", "title": "Handling Card Payments Without Getting Burned", "minutes": 5, "icon": "💳",
                "body": """
<p>If your business accepts credit cards, <b>PCI DSS</b> (the card industry's security standard)
applies. The single most powerful idea in it: <b>the safest card data is the card data you never
store.</b></p>
<h4>The rules that keep you out of trouble</h4>
<ol>
<li><b>Never store the full card number, and NEVER the CVV</b> (the 3–4 digit code). Storing the
CVV is flatly prohibited — no exceptions.</li>
<li><b>Don't take card numbers by email, chat, or sticky note.</b> If a customer emails you their
card, don't act on it in email — delete it and collect payment through your approved processor.</li>
<li><b>Use the payment terminal / processor's secure page.</b> Modern setups "tokenize" the card
so your systems only ever see a meaningless token, not the real number — that's the goal.</li>
<li><b>Watch for skimmers and tampering</b> on physical terminals, and only enter card data on the
real, approved device or page.</li>
</ol>
<h4>Why it's worth caring</h4>
<p>A card breach means fines, forensic audits, losing the ability to take cards, and shattered
customer trust — a genuine business-ender for a small shop. The less card data flows through your
people and systems, the smaller your risk and your compliance burden both get.</p>
<p>💡 If someone hands you card data through a channel that shouldn't have it (email, text, a form),
the right move is to <b>stop, not store it, and route them to the secure method</b> — then delete
the exposed copy.</p>
""",
                "quiz": [
                    {"q": "A customer emails you their full card number and CVV to 'make it easy.' What do you do?",
                     "choices": ["Save it to process later", "Store just the CVV for convenience", "Don't process it from email — collect payment via the approved processor, then delete the email",
                                 "Forward it to accounting"],
                     "answer": 2,
                     "explain": "Card data in email is a breach risk, and storing the CVV is prohibited outright. Take payment through the secure channel and delete the exposed copy."},
                    {"q": "What is the one piece of card data you must NEVER store, period?",
                     "choices": ["The cardholder name", "The expiration date", "The CVV / security code", "The billing ZIP"],
                     "answer": 2,
                     "explain": "PCI DSS flatly prohibits storing the CVV after authorization. It exists to prove card presence and must never be retained."},
                    {"q": "What does 'tokenization' do for card security?",
                     "choices": ["Encrypts your Wi-Fi", "Replaces the real card number with a meaningless token so your systems never hold the actual number",
                                 "Speeds up checkout only", "Prints receipts"],
                     "answer": 1,
                     "explain": "Tokenization means the real number lives only with the processor; your systems handle a useless token — shrinking both risk and PCI scope."},
                ],
            },
            {
                "id": "ai-deepfakes", "title": "AI Voices, Deepfakes & the New Social Engineering", "minutes": 6, "icon": "🤖",
                "body": """
<p>The oldest attack — <b>tricking a human</b> — just got a terrifying upgrade. Attackers now use
AI to <b>clone voices from a few seconds of audio</b>, generate <b>video deepfakes</b> of
executives, and write flawless, personalized phishing at scale. The old tells (bad grammar, weird
phrasing) are fading. New defenses are needed.</p>
<h4>What's actually happening in the wild</h4>
<ol>
<li><b>Voice-clone calls:</b> "It's the CEO — I need you to approve this wire, I'm about to board
a flight." The voice sounds exactly right, because it is — cloned from a podcast or earnings call.</li>
<li><b>Deepfake video meetings:</b> employees have wired millions after a "video call" with what
looked like their CFO and colleagues — all synthetic.</li>
<li><b>AI-written spear phishing:</b> perfect tone, your real projects and coworkers referenced,
no typos.</li>
</ol>
<h4>Defenses that still work</h4>
<ol>
<li><b>Verify through a second, known channel.</b> Unusual request from "the boss"? Hang up and
call the number you already have. A real leader will thank you.</li>
<li><b>Use a code word / callback rule for money and credentials.</b> Any urgent wire or gift-card
or password request must pass an out-of-band check — no exceptions, no matter how real it sounds.</li>
<li><b>Slow down on urgency + secrecy.</b> That combo is the constant across every version of this
scam, AI or not.</li>
<li><b>Be stingy with your voice/video online?</b> You can't be — so lean on process, not on
detecting the fake.</li>
</ol>
<p>💡 The lesson isn't "learn to spot deepfakes" — soon you won't be able to. It's "<b>verify
important requests out-of-band, every time</b>," which works no matter how convincing the fake is.</p>
""",
                "quiz": [
                    {"q": "You get a call in your CEO's exact voice urgently asking you to wire funds before a flight. Best response?",
                     "choices": ["Wire it — the voice is unmistakable", "Call back on the CEO's known number to verify before doing anything",
                                 "Reply-all to the team", "Wire a smaller amount to be safe"],
                     "answer": 1,
                     "explain": "Voice cloning makes 'it sounded exactly like them' meaningless. An out-of-band callback on a known number defeats the fake regardless of quality."},
                    {"q": "Why is 'learn to spot the deepfake' a losing long-term strategy?",
                     "choices": ["Deepfakes are easy to spot", "The fakes are getting good enough that detection by eye/ear becomes unreliable — process beats perception",
                                 "Only movies use deepfakes", "AI can't clone voices"],
                     "answer": 1,
                     "explain": "As synthetic media improves, human detection fails. Verification processes (callbacks, code words) work no matter how convincing the fake is."},
                    {"q": "What single factor is constant across CEO-fraud, voice-clone, and deepfake scams?",
                     "choices": ["Bad grammar", "A request pushing urgency + secrecy around money or credentials",
                                 "They come on weekends", "They use fax machines"],
                     "answer": 1,
                     "explain": "Urgency plus secrecy around money or access is the timeless core. Feel that pressure? That's your cue to slow down and verify."},
                ],
            },
            {
                "id": "qr-and-quishing", "title": "QR Codes, 'Quishing' & Everyday Physical Tricks", "minutes": 5, "icon": "🔳",
                "body": """
<p>Attacks aren't only in your inbox. A growing wave hides in the physical world and in the little
squares we scan without thinking.</p>
<h4>QR-code phishing ("quishing")</h4>
<p>A QR code is just a link you can't read. Attackers <b>slap fake QR stickers</b> over real ones on
parking meters, restaurant tables, and posters — or email you a QR "to log in / view the document."
You scan, land on a look-alike login page, and hand over your credentials. Because you scanned with
your <b>phone</b>, you skipped the desktop protections and the URL is easy to overlook.</p>
<ul>
<li><b>Preview the URL</b> your phone shows before opening it; if it's not the domain you expect,
stop.</li>
<li><b>Be suspicious of QR codes that lead to a login</b> — type known sites yourself instead.</li>
<li><b>Check for a sticker over a sticker</b> on physical codes.</li>
</ul>
<h4>The physical classics still work</h4>
<ol>
<li><b>Tailgating:</b> someone with full hands follows you through the secure door. Politeness is
the exploit. It's OK to ask "can I see your badge?" or direct them to reception.</li>
<li><b>Dropped USB drives:</b> a "found" USB in the parking lot is bait — plugging it in can install
malware instantly. Hand it to IT; never plug in unknown drives.</li>
<li><b>Shoulder surfing & clean desk:</b> lock your screen when you walk away (Win+L), and don't
leave passwords or sensitive printouts in the open.</li>
</ol>
<p>💡 The mindset: a link you can't read (QR), a stranger you can't verify (tailgater), and a device
you didn't buy (USB) all deserve the same pause you'd give a suspicious email.</p>
""",
                "quiz": [
                    {"q": "You find a USB drive labeled 'Payroll Q3' in the parking lot. What do you do?",
                     "choices": ["Plug it in to find the owner", "Plug it in at home instead", "Hand it to IT — never plug in unknown drives; that's a classic malware drop",
                                 "Keep it for storage"],
                     "answer": 2,
                     "explain": "'Lost' USBs are deliberate bait — an enticing label makes you curious enough to infect your own machine. IT can handle it safely."},
                    {"q": "A QR code on a poster says 'Scan to log in and claim your reward.' The main risk is…",
                     "choices": ["It wastes data", "It can send you to a look-alike login page to steal your credentials, and the real URL is hard to see on a phone",
                                 "QR codes can't contain links", "Your camera breaks"],
                     "answer": 1,
                     "explain": "'Quishing' hides a malicious link in a square you can't read. Preview the URL, and never trust a QR that leads to a login — type the site yourself."},
                    {"q": "Someone with an armful of boxes follows you toward the badge-only door. The secure move?",
                     "choices": ["Hold it open — it's polite", "Ask to see their badge or direct them to reception; don't let politeness bypass access control",
                                 "Ignore them", "Prop the door open for others too"],
                     "answer": 1,
                     "explain": "Tailgating weaponizes courtesy. Verifying a badge or routing them to reception is normal and expected — not rude."},
                ],
            },
        ],
    },
]

GAMES = [
    {
        "id": "phish-or-legit", "title": "Phish or Legit?", "icon": "🎣",
        "blurb": "8 real-world emails. Your inbox, your call. Can you go 8 for 8?",
        "kind": "phish",
        "items": [
            {"from_name": "Microsoft 365", "from_addr": "no-reply@micr0soft-secure.top",
             "subject": "Action required: your mailbox will be suspended in 24 hours",
             "body": "We detected unusual sign-in activity. Verify your account within 24 hours to avoid suspension. → VERIFY NOW",
             "is_phish": True,
             "explain": "Look-alike domain (micr0soft with a zero, .top TLD), countdown threat, and a verify-now button. Three tells in one email."},
            {"from_name": "Sarah Kim (HR)", "from_addr": "sarah.kim@yourcompany.com",
             "subject": "Updated holiday calendar for Q3",
             "body": "Hi all — the Q3 holiday calendar is now on the intranet under HR > Calendars. No action needed, just FYI for planning.",
             "is_phish": False,
             "explain": "Internal domain, no link to click, no urgency, no credential ask, and it points to a place you already know. Informational emails like this are the normal baseline."},
            {"from_name": "IT Helpdesk", "from_addr": "helpdesk@yourcompany-support.net",
             "subject": "Mandatory: install new VPN client today",
             "body": "All staff must install the attached VPN client (VPN_setup.zip) by EOD or lose remote access. This is mandatory.",
             "is_phish": True,
             "explain": "The domain is yourcompany-SUPPORT.NET — not your real domain. Software arrives via IT-managed channels, not zip attachments with a deadline."},
            {"from_name": "DocuSign", "from_addr": "dse@docusign.net",
             "subject": "Jordan Polasek sent you the MSA for countersignature",
             "body": "Your document is ready: 'BVTech MSA — final'. You discussed this contract on yesterday's call. Review and sign via your DocuSign account.",
             "is_phish": False,
             "explain": "Real DocuSign sending domain AND — the key part — you expected this document from a call yesterday. Expected + verifiable = the legit pattern. (When unsure, open docusign.com directly instead of clicking.)"},
            {"from_name": "Amazon Business", "from_addr": "order-update@amazon-billing-center.com",
             "subject": "Invoice #8837 — payment method declined",
             "body": "Your payment for order #8837 was declined. Update your payment information within 48 hours to avoid order cancellation. → UPDATE PAYMENT",
             "is_phish": True,
             "explain": "amazon-billing-center.com is not amazon.com — dashes and extra words are domain forgery. Also: were you expecting order #8837? Check the app, never the link."},
            {"from_name": "Chase Fraud Alerts", "from_addr": "alerts@chase-verify.info",
             "subject": "⚠️ $947.20 charge flagged — confirm identity",
             "body": "We blocked a suspicious charge. To restore card access, confirm your identity: card number, SSN and online banking password. Reply or click within 1 hour.",
             "is_phish": True,
             "explain": "No bank EVER asks for your password or SSN by email — that request alone is a 100% fraud signature, before you even notice the fake .info domain and the 1-hour timer."},
            {"from_name": "Marcus Webb", "from_addr": "m.webb@vendorpartner.com",
             "subject": "RE: RE: Server maintenance window — confirming Saturday",
             "body": "Following up our thread — confirming Saturday 10pm start for the maintenance window we scheduled. Same scope as the SOW. Call me if anything changed.",
             "is_phish": False,
             "explain": "Ongoing thread, established contact, references shared context (the SOW), offers a phone call, asks for nothing sensitive. This is what real business email looks like."},
            {"from_name": "CEO — Jordan", "from_addr": "jordan.polasek@gmail.com",
             "subject": "Quick favor - are you at your desk?",
             "body": "I'm stuck in back-to-back meetings and need something handled discreetly. Reply here when you see this. Sent from my iPhone",
             "is_phish": True,
             "explain": "The 'CEO' writing from a personal Gmail with vague urgency + secrecy is the gift-card scam's opening move. Verify on the CEO's known number; never just reply."},
        ],
    },
    {
        "id": "password-lab", "title": "Password Lab", "icon": "🧪",
        "blurb": "Watch crack-times change live as you build. Forge a passphrase the lab rates UNCRACKABLE to win.",
        "kind": "lab",
        "items": [],
    },
]

# --------------------------------------------------------------------------- #
# CYBER RANGE — hands-on, "hack-this-site"-style labs. Each lab emulates a
# vulnerable behavior on the box (via a SAFE, hardcoded probe simulator — never
# real code execution or a real backend) and is graded by a server-side flag
# check the client never sees. Difficulty sets the XP. This lives inside the
# Academy so labs share the same XP / streak / badge / leaderboard system.
# --------------------------------------------------------------------------- #
import base64 as _b64
import hashlib as _hashlib

DIFF_XP = {"Easy": 100, "Medium": 175, "Hard": 275}

LABS = [
    {
        "id": "recon-source", "title": "Hidden in Plain Sight", "icon": "🔍",
        "difficulty": "Easy", "category": "Recon", "points": DIFF_XP["Easy"],
        "brief": "Developers leave secrets in the last place they think anyone looks: "
                 "the page source. Read the HTML below and capture the flag.",
        "target": {"kind": "source", "html":
                   "<div class=\"login\">\n"
                   "  <h1>Vertex Dental Portal</h1>\n"
                   "  <!-- TODO: remove debug flag before launch — FLAG{view_source_is_recon_101} -->\n"
                   "  <form action=\"/auth\" method=\"post\">\n"
                   "    <input name=\"user\" placeholder=\"username\">\n"
                   "    <input name=\"pass\" type=\"password\">\n"
                   "  </form>\n</div>"},
        "hints": ["HTML comments start with <!-- and end with -->.",
                  "The flag format is FLAG{...}. Copy exactly what's inside a comment."],
        "check": ("exact", "FLAG{view_source_is_recon_101}"),
        "teaches": "Attackers read your source before anything else. Never ship "
                   "credentials, keys, or debug flags in client-side code or comments.",
    },
    {
        "id": "robots-recon", "title": "What robots.txt Reveals", "icon": "🤖",
        "difficulty": "Easy", "category": "Recon", "points": DIFF_XP["Easy"],
        "brief": "robots.txt tells search engines what to skip — and tells attackers "
                 "exactly where the interesting stuff is. Probe the site's robots.txt, "
                 "follow what it's hiding, and grab the flag.",
        "target": {"kind": "probe",
                   "instructions": "GET the paths below. Start with /robots.txt.",
                   "examples": ["/robots.txt", "/<the disallowed path>"]},
        "hints": ["Probe path=/robots.txt first.",
                  "It Disallows a folder. Probe that exact path next."],
        "check": ("exact", "FLAG{robots_txt_is_a_treasure_map}"),
        "teaches": "robots.txt is public. Never use it to 'hide' admin or backup "
                   "paths — it advertises them. Protect with auth, not obscurity.",
    },
    {
        "id": "cookie-tamper", "title": "Cookie Monster", "icon": "🍪",
        "difficulty": "Easy", "category": "Web", "points": DIFF_XP["Easy"],
        "brief": "This app decides who's an admin using a cookie it trusts blindly. "
                 "Your session cookie is a base64 JSON blob. Decode it, promote "
                 "yourself to admin, and submit the forged cookie value.",
        "target": {"kind": "data",
                   "cookie": _b64.b64encode(b'{"user":"guest","role":"user","admin":false}').decode(),
                   "note": "Submit a new base64 value that makes you admin."},
        "hints": ["base64-decode the cookie to see the JSON.",
                  "Set admin to true (and/or role to admin), then base64-encode it "
                  "again and submit that string."],
        "check": ("cookie_admin", ""),
        "teaches": "Never trust client-side state for authorization. Sign your "
                   "session tokens server-side (or store the session server-side) so "
                   "a tampered cookie is rejected, not obeyed.",
    },
    {
        "id": "idor-invoice", "title": "The Invoice Next Door", "icon": "🔢",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "You're viewing YOUR invoice at id=4021. The app never checks that "
                 "an invoice actually belongs to you (an IDOR bug). Probe nearby ids "
                 "until you find the one holding the flag.",
        "target": {"kind": "probe",
                   "instructions": "Probe id=4021 (yours), then try neighboring ids.",
                   "examples": ["?id=4021", "?id=4020", "?id=4019"]},
        "hints": ["Change the id parameter. Try the ones just below 4021.",
                  "One nearby invoice belongs to another customer and shows the flag."],
        "check": ("exact", "FLAG{idor_means_check_the_owner}"),
        "teaches": "Insecure Direct Object Reference: always verify the logged-in "
                   "user OWNS the record they request. Sequential IDs make this trivial "
                   "to exploit — authorize every object access on the server.",
    },
    {
        "id": "sqli-login", "title": "The Login That Trusts Too Much", "icon": "💉",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "This login builds its SQL by gluing your input straight into the "
                 "query. Log in as admin WITHOUT knowing the password by making the "
                 "WHERE clause always true. Probe the login with your payload.",
        "target": {"kind": "probe",
                   "instructions": "Probe with user=admin and a password payload. "
                                   "The backend runs: SELECT * FROM users WHERE "
                                   "user='<user>' AND pass='<pass>'",
                   "examples": ["?user=admin&pass=hunter2 (fails)",
                                "?user=admin&pass=<your injection>"]},
        "hints": ["Close the quote and add an always-true condition.",
                  "Classic tautology: ' OR '1'='1  — or comment out the rest with --."],
        "check": ("sqli", ""),
        "teaches": "SQL injection. The fix is never 'filter bad words' — it's "
                   "PARAMETERIZED QUERIES (bound parameters), so user input can never "
                   "change the query's structure.",
    },
    {
        "id": "jwt-none", "title": "The Token That Signs Itself", "icon": "🎫",
        "difficulty": "Hard", "category": "Auth", "points": DIFF_XP["Hard"],
        "brief": "Here's your JWT — role 'user', signed HS256. This server foolishly "
                 "accepts the 'none' algorithm (unsigned tokens). Forge a token with "
                 "alg=none and role=admin and submit it.",
        "target": {"kind": "data",
                   "jwt": (_b64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
                           + "." + _b64.urlsafe_b64encode(b'{"user":"guest","role":"user"}').decode().rstrip("=")
                           + ".c2lnbmF0dXJl"),
                   "note": "A JWT is three base64url parts joined by dots: header.payload.signature"},
        "hints": ["Base64url-decode the header and payload (the first two parts).",
                  "Make a new header {\"alg\":\"none\",\"typ\":\"JWT\"} and payload with "
                  "\"role\":\"admin\". Base64url-encode each, join with dots. With alg "
                  "'none' the signature is empty — end the token with a trailing dot."],
        "check": ("jwt_none", ""),
        "teaches": "The JWT 'alg:none' / algorithm-confusion attack. Always pin the "
                   "expected algorithm server-side and REJECT 'none'. A token's own "
                   "header must never be allowed to choose how it's verified.",
    },
    {
        "id": "hash-crack", "title": "Crack the Hash", "icon": "🔓",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "A breach dump leaked this MD5 password hash. MD5 is fast and "
                 "unsalted — a gift to crackers. Recover the plaintext password and "
                 "submit it.\n\nMD5: 5f4dcc3b5aa765d61d8327deb882cf99",
        "target": {"kind": "data", "hash": "5f4dcc3b5aa765d61d8327deb882cf99",
                   "note": "It's one of the most common passwords ever leaked. "
                           "A wordlist cracks it in milliseconds."},
        "hints": ["It's a 5-letter dictionary word — the #1 password in every breach list.",
                  "Try hashing 'password' with MD5. Submit the plaintext, not the hash."],
        "check": ("md5", "5f4dcc3b5aa765d61d8327deb882cf99"),
        "teaches": "Never store passwords as fast/unsalted hashes. Use a slow, salted "
                   "algorithm (bcrypt, scrypt, Argon2) so a stolen database can't be "
                   "reversed with a wordlist.",
    },
    {
        "id": "base64-onion", "title": "Layers of Obfuscation", "icon": "🧅",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "Malware hides its payload under layers of encoding. This blob is "
                 "base64 wrapped around ROT13. Peel both layers to reveal the flag.\n\n"
                 + _b64.b64encode("SYNT{rapbqvat_vf_abg_rapelcgvba}".encode()).decode(),
        "target": {"kind": "data",
                   "blob": _b64.b64encode("SYNT{rapbqvat_vf_abg_rapelcgvba}".encode()).decode(),
                   "note": "Step 1: base64-decode. Step 2: ROT13 the result."},
        "hints": ["base64-decode the blob first — you'll get scrambled-looking text.",
                  "That text is ROT13. Rotate letters 13 places (SYNT -> FLAG)."],
        "check": ("exact", "FLAG{encoding_is_not_encryption}"),
        "teaches": "Encoding (base64, ROT13, hex) is NOT encryption — it hides nothing "
                   "from anyone. Real confidentiality needs actual cryptography with keys.",
    },
    {
        "id": "path-traversal", "title": "Escape the Folder", "icon": "📂",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "This file viewer serves docs from /var/www/files/ and pastes your "
                 "filename straight into the path. Break OUT of that folder to read a "
                 "system file the app never meant to expose. Probe with a filename.",
        "target": {"kind": "probe",
                   "instructions": "Probe file=welcome.txt (works). Then try to reach "
                                   "the system password file outside the web root.",
                   "examples": ["?file=welcome.txt", "?file=../../../../etc/passwd"]},
        "hints": ["Use ../ to climb directories out of /var/www/files/.",
                  "The classic target is etc/passwd — climb enough levels with ../ "
                  "to reach it. The flag is planted in that file."],
        "check": ("exact", "FLAG{never_trust_a_filename_from_a_user}"),
        "teaches": "Path/Directory Traversal. Never build file paths from user input. "
                   "Resolve to a canonical path and confirm it stays inside the allowed "
                   "directory; reject any '..' sequences.",
    },
    {
        "id": "email-forensics", "title": "Read the Headers", "icon": "🕵️",
        "difficulty": "Medium", "category": "Email", "points": DIFF_XP["Medium"],
        "brief": "A 'CEO' email asked accounting to wire funds. The body looks fine — "
                 "but email headers don't lie. Inspect the raw headers and submit the "
                 "IP address the message ACTUALLY originated from (the one that failed "
                 "SPF).",
        "target": {"kind": "data", "headers":
                   "Delivered-To: ap@vertexdental.com\n"
                   "Received: from mail.vertexdental.com (10.0.0.5)\n"
                   "Received: from unknown (HELO cheap-vps.ru) (185.220.101.44)\n"
                   "        by mx.vertexdental.com; Tue, 29 Jul 2026 01:12:04\n"
                   "Authentication-Results: mx.vertexdental.com;\n"
                   "        spf=fail (sender IP is 185.220.101.44) smtp.mailfrom=ceo@vertexdental.com;\n"
                   "        dkim=none; dmarc=fail\n"
                   "From: \"Jordan CEO\" <ceo@vertexdental.com>\n"
                   "Subject: Urgent wire needed before noon"},
        "hints": ["Read the Received: lines from the BOTTOM up — the earliest hop is "
                  "the true origin.", "The Authentication-Results line names the IP that "
                  "failed SPF. Submit just that IP address."],
        "check": ("exact", "185.220.101.44"),
        "teaches": "Email headers reveal the true path. spf=fail + dkim=none + "
                   "dmarc=fail on a 'CEO wire' request is textbook business email "
                   "compromise. This is why DMARC enforcement matters.",
    },
    # ------------------------------------------------------------------ #
    # Wave 2 — crypto, forensics, recon, more web, and a coding lab.
    # ------------------------------------------------------------------ #
    {
        "id": "caesar-cipher", "title": "Wheel of Misfortune", "icon": "🎡",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "Julius Caesar shifted every letter by 3. This message is shifted by "
                 "13 (a.k.a. ROT13). Rotate it back and read the flag.",
        "target": {"kind": "data",
                   "cipher": "SYNT{rg_gh_oehgr_guvf_vf_ebg13}",
                   "note": "Each letter is rotated 13 places. Rotating 13 more brings it "
                           "home (A<->N, B<->O ...). Digits and punctuation don't move."},
        "hints": ["ROT13 is its own inverse — apply ROT13 again to decode.",
                  "SYNT decodes to FLAG. Rotate the rest the same way."],
        "check": ("exact", "FLAG{et_tu_brute_this_is_rot13}"),
        "teaches": "Caesar/ROT ciphers are substitution with a fixed shift — trivially "
                   "broken by trying all 25 shifts. Classical ciphers are history "
                   "lessons, not security. Real confidentiality needs modern crypto.",
    },
    {
        "id": "xor-key", "title": "One Byte to Rule Them All", "icon": "⊕",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "This flag was XOR-encrypted with a single repeating byte, then shown "
                 "as hex. Find the key (a printable ASCII byte) and XOR it back.",
        "target": {"kind": "data",
                   "hex": "6c666b6d515245587543597544455e754f444958535a5e434544754f435e424f5857",
                   "note": "Single-byte XOR: every byte was XORed with the same key. XOR "
                           "is reversible — cipher XOR key = plaintext. Try keys 32-126."},
        "hints": ["Brute-force all 95 printable keys; the right one yields text starting "
                  "with 'FLAG{'.", "The key is the byte 0x2A (the '*' character)."],
        "check": ("exact", "FLAG{xor_is_not_encryption_either}"),
        "teaches": "Single-byte (and short-key) XOR is broken instantly by brute force or "
                   "frequency analysis. XOR is a building block of real ciphers, but XOR "
                   "with a tiny reused key is obfuscation, not encryption.",
    },
    {
        "id": "hash-crack-sha1", "title": "Rainbow's End", "icon": "🌈",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "A leaked database stored passwords as unsalted SHA-1. Here's one hash. "
                 "Crack it and submit the original password.",
        "target": {"kind": "data",
                   "hash": "8d6e34f987851aa599257d3831a1af040886842f",
                   "algo": "SHA-1 (unsalted)",
                   "note": "Unsalted fast hashes fall to wordlists. This one is a common "
                           "password from every leak list."},
        "hints": ["It's a single dictionary word — think 'rockyou' top-100.",
                  "A warm, weather word. Rhymes with 'sunshine' because it IS sunshine."],
        "check": ("sha1", "8d6e34f987851aa599257d3831a1af040886842f"),
        "teaches": "Fast, unsalted hashes (MD5/SHA-1) let attackers test billions of "
                   "guesses per second and reuse precomputed rainbow tables. Store "
                   "passwords with a slow, salted KDF: bcrypt, scrypt, or Argon2.",
    },
    {
        "id": "exif-metadata", "title": "The Photo Remembers", "icon": "📷",
        "difficulty": "Easy", "category": "Forensics", "points": DIFF_XP["Easy"],
        "brief": "A staffer posted a 'harmless' photo. Its embedded EXIF metadata says "
                 "more than they meant to. Read the dump and capture the flag.",
        "target": {"kind": "data",
                   "exif": "$ exiftool leak.jpg\n"
                           "File Name        : leak.jpg\n"
                           "Camera Model     : iPhone 14 Pro\n"
                           "Create Date      : 2026:03:11 22:41:07\n"
                           "GPS Position     : 29.1988 N, 96.2719 W  (El Campo, TX)\n"
                           "Artist           : j.doe@vertexdental.com\n"
                           "User Comment     : FLAG{metadata_never_lies}\n"
                           "Software         : Adobe Photoshop 25.0"},
        "hints": ["Metadata fields like Artist, GPS, and User Comment travel inside the "
                  "file.", "The flag is sitting in the User Comment field."],
        "check": ("exact", "FLAG{metadata_never_lies}"),
        "teaches": "Files carry hidden metadata — GPS coordinates, usernames, software, "
                   "timestamps. Strip EXIF before publishing photos and scrub document "
                   "metadata before sending. It has deanonymized people and leaked bases.",
    },
    {
        "id": "pcap-basic-auth", "title": "Cleartext Confessions", "icon": "🎧",
        "difficulty": "Medium", "category": "Forensics", "points": DIFF_XP["Medium"],
        "brief": "A packet capture caught a login over plain HTTP. HTTP Basic Auth is "
                 "just base64, not encryption. Recover the password (that's the flag).",
        "target": {"kind": "data",
                   "pcap": "GET /portal/dashboard HTTP/1.1\n"
                           "Host: intranet.vertexdental.com\n"
                           "Authorization: Basic YW5hbHlzdDpTM2NyM3RXMW50ZXIh\n"
                           "User-Agent: Mozilla/5.0\n"
                           "Accept: text/html\n",
                   "note": "Basic Auth sends base64(user:pass). base64 is encoding, not "
                           "encryption — decode it. Submit only the password."},
        "hints": ["base64-decode the string after 'Basic '. You'll get user:password.",
                  "The username is 'analyst'. Submit just the part after the colon."],
        "check": ("exact", "S3cr3tW1nter!"),
        "teaches": "HTTP Basic Auth base64-encodes credentials in the clear — anyone on "
                   "the path reads them. Always use HTTPS (TLS); never send credentials, "
                   "tokens, or PII over plain HTTP.",
    },
    {
        "id": "log-analysis", "title": "Needle in the Logstack", "icon": "📜",
        "difficulty": "Medium", "category": "Forensics", "points": DIFF_XP["Medium"],
        "brief": "Someone brute-forced the admin panel and eventually got in. Read the "
                 "access log and submit the attacker's IP (the one that finally hit 200 "
                 "on /admin).",
        "target": {"kind": "data",
                   "log": '198.51.100.7 - - "POST /login" 200 (normal user, 1 request)\n'
                          '203.0.113.66 - - "POST /admin" 401\n'
                          '203.0.113.66 - - "POST /admin" 401\n'
                          '203.0.113.66 - - "POST /admin" 401\n'
                          '192.0.2.15   - - "GET /pricing" 200\n'
                          '203.0.113.66 - - "POST /admin" 401\n'
                          '203.0.113.66 - - "POST /admin" 200  <-- success\n'
                          '198.51.100.7 - - "GET /dashboard" 200',
                   "note": "One IP hammers /admin with 401s, then a 200. That pattern IS "
                           "the brute force. Submit that IP."},
        "hints": ["Look for many 401s from one IP followed by a 200 on the same path.",
                  "The attacker's IP is in the 203.0.113.0/24 documentation range."],
        "check": ("exact", "203.0.113.66"),
        "teaches": "Repeated 401s from one source then a 200 is the signature of a "
                   "successful brute force — exactly what account lockout and alerting "
                   "exist to catch. Logs are how you detect and reconstruct an attack.",
    },
    {
        "id": "git-exposed", "title": "The .git Time Machine", "icon": "🕰️",
        "difficulty": "Easy", "category": "Recon", "points": DIFF_XP["Easy"],
        "brief": "A deploy left the site's .git folder web-accessible — a full history of "
                 "the code, including secrets someone 'removed'. Probe it and find the flag.",
        "target": {"kind": "probe",
                   "instructions": "Try fetching git internals under /.git/. Start with "
                                   "the config, then the commit log.",
                   "examples": ["?path=/.git/config", "?path=/.git/logs/HEAD"]},
        "hints": ["/.git/config confirms the folder is exposed; /.git/logs/HEAD lists "
                  "commits.", "An old commit message removed a secret — but git never "
                  "forgets. The flag is in the logs."],
        "check": ("exact", "FLAG{dot_git_is_a_time_machine}"),
        "teaches": "An exposed .git directory leaks your entire source history — including "
                   "secrets deleted in later commits. Block /.git in the web server and "
                   "rotate any credential that was ever committed; deletion isn't removal.",
    },
    {
        "id": "open-redirect", "title": "The Doorway to Anywhere", "icon": "🚪",
        "difficulty": "Easy", "category": "Web", "points": DIFF_XP["Easy"],
        "brief": "This login sends you to whatever ?next= says after you sign in — with no "
                 "checks. Point it off-site to prove the open redirect, and grab the flag.",
        "target": {"kind": "probe",
                   "instructions": "The app redirects to the ?next= value. Try an internal "
                                   "path, then an external URL.",
                   "examples": ["?next=/dashboard", "?next=https://evil.example/phish"]},
        "hints": ["Set next to a full external URL (https://...).",
                  "Redirecting users to an attacker's domain is the bug — the flag "
                  "appears when next points off-site."],
        "check": ("exact", "FLAG{always_validate_redirect_targets}"),
        "teaches": "Open redirects let attackers borrow your trusted domain to bounce "
                   "victims to phishing pages. Allow only relative paths or an allowlist of "
                   "hosts; never redirect to raw user-supplied URLs.",
    },
    {
        "id": "xss-reflected", "title": "The Search Box Bites Back", "icon": "🐍",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "This search page echoes your query straight back into the HTML with no "
                 "encoding. Inject a script that the page would execute (reflected XSS).",
        "target": {"kind": "probe",
                   "instructions": "Whatever you put in ?q= is reflected into the page. "
                                   "Try plain text, then an HTML/script payload.",
                   "examples": ["?q=hello", "?q=<script>alert(1)</script>"]},
        "hints": ["Submit a <script>...</script> (or an onerror= image) payload in q.",
                  "The lab detects an executable script injection and returns the flag."],
        "check": ("exact", "FLAG{encode_output_stop_reflected_xss}"),
        "teaches": "Reflected XSS happens when user input is written into a page without "
                   "output-encoding, letting an attacker run script in a victim's browser. "
                   "Contextually encode all output and set a strict Content-Security-Policy.",
    },
    {
        "id": "mass-assignment", "title": "Checking Your Own Box", "icon": "☑️",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "The 'update profile' endpoint saves every field you send — including "
                 "ones the form never showed you. Grant yourself admin (mass assignment).",
        "target": {"kind": "probe",
                   "instructions": "Send profile fields. The form only exposes 'name', but "
                                   "the API blindly binds whatever you pass. Try adding an "
                                   "admin-ish field.",
                   "examples": ["?name=Jordan", "?name=Jordan&role=admin", "?is_admin=true"]},
        "hints": ["Add a field the UI never offered, like role=admin or is_admin=true.",
                  "The server binds it straight to your account object — and hands you the flag."],
        "check": ("exact", "FLAG{never_bind_untrusted_fields}"),
        "teaches": "Mass assignment / over-posting: binding request fields directly to a "
                   "model lets users set fields (role, is_admin, balance) they should never "
                   "control. Bind an explicit allowlist of fields on the server.",
    },
    {
        "id": "ssrf-metadata", "title": "The Server's Inside Voice", "icon": "🛰️",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "This 'fetch a URL' feature runs from the server, so it can reach places "
                 "you can't — like the cloud metadata service. Make it fetch the secrets "
                 "endpoint (SSRF).",
        "target": {"kind": "probe",
                   "instructions": "The server fetches whatever ?url= you give it. Point it "
                                   "at the cloud metadata IP that hands out credentials.",
                   "examples": ["?url=https://example.com",
                                "?url=http://169.254.169.254/latest/meta-data/"]},
        "hints": ["Cloud instances expose secrets at the link-local IP 169.254.169.254.",
                  "Fetch http://169.254.169.254/latest/meta-data/iam/ to reach the creds — "
                  "the flag is returned from there."],
        "check": ("exact", "FLAG{ssrf_reaches_the_metadata_service}"),
        "teaches": "Server-Side Request Forgery abuses server-side fetchers to hit internal "
                   "services (metadata, admin panels, databases). Enforce an egress "
                   "allowlist, block link-local/private ranges, and require IMDSv2.",
    },
    {
        "id": "cmd-injection", "title": "Ping of Death", "icon": "📡",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "A network-tools page runs `ping <your input>` on the server shell, gluing "
                 "your text into the command. Chain an extra command to read the flag.",
        "target": {"kind": "probe",
                   "instructions": "The host value is passed to a shell ping. Try a normal "
                                   "host, then append a second command with a shell "
                                   "metacharacter.",
                   "examples": ["?host=8.8.8.8", "?host=8.8.8.8; cat flag.txt",
                                "?host=8.8.8.8 && cat flag.txt"]},
        "hints": ["Shell metacharacters ; | && chain commands. Append one that reads the flag.",
                  "Try host=8.8.8.8; cat flag.txt — the lab runs your second command."],
        "check": ("exact", "FLAG{never_pass_user_input_to_a_shell}"),
        "teaches": "OS command injection: concatenating user input into a shell command lets "
                   "attackers run arbitrary commands. Never build shell strings from input — "
                   "call binaries with an argument array and no shell, and validate inputs.",
    },
    {
        "id": "regex-waf", "title": "Build Your Own Firewall", "icon": "🧱",
        "difficulty": "Hard", "category": "Defense", "points": DIFF_XP["Hard"],
        "brief": "Now play defense. Write ONE regular expression that blocks every SQL-"
                 "injection payload below WITHOUT flagging any of the innocent inputs. "
                 "Submit your regex — the lab tests it live against both sets.",
        "target": {"kind": "waf",
                   "instructions": "Your regex must MATCH all of the attacks and NONE of the "
                                   "benign inputs (matching is case-insensitive). The tricky "
                                   "part: benign names contain quotes and words like 'or' and "
                                   "'union' — a lazy filter will false-positive. Target SQL "
                                   "*syntax*, not innocent substrings.",
                   "attacks": [
                       "' OR '1'='1",
                       "admin'--",
                       "' UNION SELECT password FROM users--",
                       "'; DROP TABLE users;--",
                       "1' OR '1'='1",
                   ],
                   "benign": [
                       "O'Brien",
                       "orlando",
                       "d'Angelo",
                       "password--strong",
                       "union square cafe",
                   ]},
        "hints": ["Anchor on a quote FOLLOWED by SQL syntax (a quote next to or/and/union/"
                  "comment/semicolon), plus keyword pairs like UNION SELECT and DROP TABLE.",
                  "Something like:  '\\s*(or|and|union|;|--)|union\\s+select|drop\\s+table"],
        "check": ("regex_waf", ""),
        "teaches": "Blocklists are brittle: too loose and you break real users (false "
                   "positives on O'Brien), too tight and attacks slip through. That's why "
                   "the real fix for SQLi is parameterized queries, not regex filtering — "
                   "but writing a WAF rule teaches you exactly how attacks are shaped.",
    },
    # ------------------------------------------------------------------ #
    # Wave 3 — more crypto/encoding, OSINT, and modern web (SSTI/NoSQL/
    # GraphQL/CORS/.env). Still safe emulators + server-side flag checks.
    # ------------------------------------------------------------------ #
    {
        "id": "binary-decode", "title": "Ones and Zeros", "icon": "🔢",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "Eight bits make a byte, and a byte is a character. Decode this binary "
                 "back into text.",
        "target": {"kind": "data",
                   "binary": "01000110 01001100 01000001 01000111 01111011 01100010 "
                             "01101001 01101110 01100001 01110010 01111001 01011111 "
                             "01101001 01110011 01011111 01101010 01110101 01110011 "
                             "01110100 01011111 01100010 01100001 01110011 01100101 "
                             "01011111 01110100 01110111 01101111 01111101",
                   "note": "Each 8-bit group is one ASCII character. 01000110 = 70 = 'F'."},
        "hints": ["Convert each 8-bit group to a decimal number, then to its ASCII letter.",
                  "The first byte 01000110 is 'F' — the flag starts with FLAG{."],
        "check": ("exact", "FLAG{binary_is_just_base_two}"),
        "teaches": "Binary is just base-2 text encoding — not a secret. Everything a "
                   "computer stores is bits; representation is not protection.",
    },
    {
        "id": "hex-decode", "title": "Base Sixteen", "icon": "🔠",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "Two hex digits make one byte. Decode this hex string into text.",
        "target": {"kind": "data",
                   "hex": "464c41477b6865785f69735f626173655f7369787465656e7d",
                   "note": "Pairs of hex digits map to bytes: 46 = 'F', 4c = 'L' ..."},
        "hints": ["Split into pairs and convert each from base-16 to a character.",
                  "46 4c 41 47 spells FLAG."],
        "check": ("exact", "FLAG{hex_is_base_sixteen}"),
        "teaches": "Hex is a compact way to show bytes (0-255 as two digits). Common in "
                   "dumps, hashes, and colors — a display format, never encryption.",
    },
    {
        "id": "morse-code", "title": "Dots and Dashes", "icon": "📻",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "The oldest digital code. Translate the Morse below to letters and submit "
                 "the hidden word (that's the flag).",
        "target": {"kind": "data",
                   "morse": "-.-. .- .--. - ..- .-. . - .... . -.. .- ... ....",
                   "note": "Space separates letters. Use a Morse chart: -.-. = C, .- = A ..."},
        "hints": ["Decode letter by letter with a Morse table.",
                  "It's a single all-caps phrase telling you what you just did."],
        "check": ("exact", "CAPTURETHEDASH"),
        "teaches": "Morse is a variable-length encoding of the alphabet into on/off "
                   "signals — the ancestor of all digital comms. Encoding, not cipher.",
    },
    {
        "id": "rot47", "title": "The Bigger Wheel", "icon": "🎯",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "ROT13's cousin. ROT47 rotates all 94 printable ASCII characters (not "
                 "just letters) by 47. Rotate it back to read the flag.",
        "target": {"kind": "data",
                   "cipher": "u{pvLC@Ecf0D9:7ED0?:?6EJ7@FCN",
                   "note": "Rotate each printable char (ASCII 33-126) by 47; like ROT13, "
                           "applying it again decodes it. Punctuation moves too this time."},
        "hints": ["ROT47 is self-inverse — apply ROT47 again.",
                  "The result starts with FLAG{ once you rotate correctly."],
        "check": ("exact", "FLAG{rot47_shifts_ninetyfour}"),
        "teaches": "ROT47 extends the Caesar idea to punctuation and digits, which is why "
                   "the ciphertext looks 'weirder' — but it's still a fixed-shift toy.",
    },
    {
        "id": "vigenere", "title": "The Keyed Cipher", "icon": "🗝️",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "Vigenère shifts each letter by a repeating keyword instead of a constant. "
                 "The key is KEY. Decrypt the message.",
        "target": {"kind": "data",
                   "cipher": "PPYQ{zgqilovc_binoerc_xfo_oci}",
                   "key": "KEY",
                   "note": "Each letter was shifted by the matching key letter (K=+10, E=+4, "
                           "Y=+24), repeating. Subtract the key to decrypt; non-letters "
                           "pass through."},
        "hints": ["Reverse the shift: for each letter subtract K/E/Y (10/4/24) in turn.",
                  "P shifted back by K(10) = F. The flag emerges as FLAG{..."],
        "check": ("exact", "FLAG{vigenere_repeats_the_key}"),
        "teaches": "Vigenère resisted attack for centuries but falls to frequency analysis "
                   "once the key length is found (Kasiski). Short reused keys = breakable.",
    },
    {
        "id": "jwt-decode", "title": "The Token Talks", "icon": "🎟️",
        "difficulty": "Medium", "category": "Forensics", "points": DIFF_XP["Medium"],
        "brief": "A JWT is three base64url parts joined by dots. The payload is NOT "
                 "encrypted — anyone can read it. Decode the payload and find the flag.",
        "target": {"kind": "data",
                   "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdmMtYWNjb3Vu"
                          "dCIsInJvbGUiOiJzZXJ2aWNlIiwibm90ZSI6IkZMQUd7and0X3BheWxvYWRf"
                          "aXNfb25seV9iYXNlNjR1cmx9In0.c2lnbmF0dXJlX2hlcmU",
                   "note": "Split on '.', take the MIDDLE part, base64url-decode it to JSON. "
                           "The flag is in a claim."},
        "hints": ["The payload is the second segment (between the two dots).",
                  "base64url-decode it — you'll get JSON with a 'note' claim holding the flag."],
        "check": ("exact", "FLAG{jwt_payload_is_only_base64url}"),
        "teaches": "JWT payloads are signed, not encrypted — never put secrets in them. "
                   "Anyone holding the token reads every claim. Signature stops tampering, "
                   "not reading.",
    },
    {
        "id": "google-dork", "title": "Search Like an Attacker", "icon": "🔎",
        "difficulty": "Easy", "category": "OSINT", "points": DIFF_XP["Easy"],
        "brief": "Attackers find exposed files with search operators ('dorks'). These "
                 "results came from  filetype:env  \"DB_PASSWORD\"  — read them for the flag.",
        "target": {"kind": "data",
                   "results": "Google  filetype:env DB_PASSWORD site:vertexdental.com\n\n"
                              "1. https://vertexdental.com/old/.env\n"
                              "   DB_HOST=10.0.0.5  DB_USER=root\n"
                              "   DB_PASSWORD=FLAG{dorks_find_what_you_forgot_to_hide}\n\n"
                              "2. https://vertexdental.com/backup/config.env  (403 Forbidden)",
                   "note": "Search engines index anything reachable — including files you "
                           "never meant to publish. The flag is a leaked DB_PASSWORD."},
        "hints": ["Read result #1 — the .env file's contents are right there.",
                  "The flag is the DB_PASSWORD value."],
        "check": ("exact", "FLAG{dorks_find_what_you_forgot_to_hide}"),
        "teaches": "Google dorking surfaces exposed configs, backups, and credentials that "
                   "were 'hidden' only by obscurity. Don't publish secrets; use robots + "
                   "access control + secret scanning, and rotate anything indexed.",
    },
    {
        "id": "cert-transparency", "title": "Every Cert Is Public", "icon": "📑",
        "difficulty": "Easy", "category": "OSINT", "points": DIFF_XP["Easy"],
        "brief": "Every TLS certificate is logged publicly (crt.sh). That reveals subdomains "
                 "you thought were private. Read the log and find the forgotten one.",
        "target": {"kind": "data",
                   "crtsh": "crt.sh?q=vertexdental.com\n\n"
                            "  www.vertexdental.com\n"
                            "  mail.vertexdental.com\n"
                            "  vpn.vertexdental.com\n"
                            "  staging-admin.vertexdental.com   <- banner: FLAG{ct_logs_reveal_subdomains}\n"
                            "  autodiscover.vertexdental.com",
                   "note": "Certificate Transparency logs every issued cert. A 'hidden' "
                           "staging host shows up the moment it gets HTTPS."},
        "hints": ["Scan the subdomain list for one that shouldn't be internet-facing.",
                  "staging-admin exposes the flag in its banner."],
        "check": ("exact", "FLAG{ct_logs_reveal_subdomains}"),
        "teaches": "You cannot hide a subdomain that has a public TLS cert — CT logs list "
                   "them all. Assume every hostname is discoverable; secure staging like prod.",
    },
    {
        "id": "exposed-env", "title": "The Dotfile Nobody Blocked", "icon": "🗂️",
        "difficulty": "Medium", "category": "Recon", "points": DIFF_XP["Medium"],
        "brief": "Apps read secrets from a .env file — which should NEVER be web-served. "
                 "This one is. Probe for it and read the flag.",
        "target": {"kind": "probe",
                   "instructions": "Try fetching common sensitive files by path.",
                   "examples": ["?path=/index.html", "?path=/.env", "?path=/config.php.bak"]},
        "hints": ["Request /.env directly — many deploys forget to block dotfiles.",
                  "The flag is stored as an APP_SECRET inside the .env."],
        "check": ("exact", "FLAG{never_ship_dot_env}"),
        "teaches": "A web-served .env leaks database creds, API keys, and app secrets in "
                   "one request. Block dotfiles at the web server, keep .env out of web "
                   "roots, and never commit it to git.",
    },
    {
        "id": "ssti", "title": "The Template Does Math", "icon": "🧮",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "This 'hello, {name}' page runs your input through its template engine. If "
                 "{{7*7}} comes back as 49, the engine is EVALUATING your input (SSTI). "
                 "Prove it and read the flag.",
        "target": {"kind": "probe",
                   "instructions": "Your name value is rendered by the server's template "
                                   "engine. Try plain text, then a template expression.",
                   "examples": ["?name=Jordan", "?name={{7*7}}", "?name={{config}}"]},
        "hints": ["Send name={{7*7}} — if it returns 49, the template is executing input.",
                  "Once you confirm evaluation, the lab hands you the flag."],
        "check": ("exact", "FLAG{template_injection_runs_code}"),
        "teaches": "Server-Side Template Injection lets attacker input reach the template "
                   "engine and run code (RCE in many engines). Never render user input as a "
                   "template; pass it as data to a pre-compiled template.",
    },
    {
        "id": "nosql-auth", "title": "Not Equal to Secure", "icon": "🍃",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "This login builds a MongoDB query from your JSON input. Operators like "
                 "$ne ('not equal') turn the password check into 'any password'. Bypass it.",
        "target": {"kind": "probe",
                   "instructions": "The login accepts user and pass. Instead of a real "
                                   "password, inject a query operator.",
                   "examples": ["?user=admin&pass=hunter2",
                                "?user=admin&pass[$ne]=x", "?user[$ne]=&pass[$ne]="]},
        "hints": ["Send pass[$ne]=x — 'password not equal to x' matches the real password.",
                  "The lab detects the operator injection and logs you in with the flag."],
        "check": ("exact", "FLAG{nosql_operators_are_injectable}"),
        "teaches": "NoSQL injection abuses query operators ($ne, $gt, $regex) smuggled via "
                   "untyped input. Validate/cast types, reject objects where strings are "
                   "expected, and use an ODM that separates data from query structure.",
    },
    {
        "id": "graphql-introspection", "title": "Ask the API About Itself", "icon": "📡",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "GraphQL can describe its own schema via introspection — often left on in "
                 "production, exposing hidden queries. Introspect this endpoint and call the "
                 "field you find.",
        "target": {"kind": "probe",
                   "instructions": "Send a query. Try introspection (__schema) to list "
                                   "types/fields, then call the hidden one.",
                   "examples": ["?query={me{name}}", "?query={__schema{queryType{fields{name}}}}",
                                "?query={secretFlag}"]},
        "hints": ["Introspect with {__schema...} — you'll see a field named secretFlag.",
                  "Then query {secretFlag} to retrieve it."],
        "check": ("exact", "FLAG{introspection_maps_the_whole_api}"),
        "teaches": "Left-on GraphQL introspection hands attackers a full map of your API, "
                   "including admin/debug fields. Disable introspection in production and "
                   "authorize every field resolver.",
    },
    {
        "id": "cors-misconfig", "title": "Trusting the Wrong Origin", "icon": "🌐",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "This API reflects any Origin into Access-Control-Allow-Origin AND allows "
                 "credentials — so an attacker's site can read a logged-in victim's data. "
                 "Send a malicious Origin and see the flag it reflects.",
        "target": {"kind": "probe",
                   "instructions": "Set the origin you're 'requesting from'. Try your own "
                                   "site, then an attacker domain.",
                   "examples": ["?origin=https://vertexdental.com",
                                "?origin=https://evil.attacker.com"]},
        "hints": ["Use an external attacker origin — the server echoes it back as allowed.",
                  "When it reflects an untrusted origin WITH credentials, it leaks the flag."],
        "check": ("exact", "FLAG{cors_reflect_plus_credentials}"),
        "teaches": "Reflecting arbitrary Origins with Allow-Credentials lets any site make "
                   "authenticated cross-origin reads. Use a strict origin allowlist and "
                   "never combine credentials with a wildcard/reflected origin.",
    },
    # ------------------------------------------------------------------ #
    # Wave 4 — the run to 50: more encodings/crypto, OSINT/recon, and
    # classic web injection (Host header, LDAP, XXE, deserialization).
    # ------------------------------------------------------------------ #
    {
        "id": "base32-decode", "title": "Five Bits at a Time", "icon": "🔤",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "Base32 packs data into A-Z and 2-7 (five bits per character), so it's "
                 "all uppercase and often ends in '='. Decode it.",
        "target": {"kind": "data",
                   "base32": "IZGECR33MJQXGZJTGJPXK43FONPWM2LWMVPWE2LUON6Q====",
                   "note": "Base32 alphabet is A-Z,2-7. Any base32 decoder returns the text."},
        "hints": ["It's base32, not base64 — note there are no lowercase letters.",
                  "Decoding yields text starting with FLAG{."],
        "check": ("exact", "FLAG{base32_uses_five_bits}"),
        "teaches": "Base32 trades density for a case-insensitive, URL/DNS-safe alphabet — "
                   "which is exactly why data-exfil-over-DNS uses it. Still just encoding.",
    },
    {
        "id": "base85-decode", "title": "Denser Still", "icon": "🧬",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "Base85 (b85) squeezes 4 bytes into 5 characters using a big symbol set. "
                 "Decode this back to text.",
        "target": {"kind": "data",
                   "base85": "Mod9Rdtza8WjHloX>(s>Wo~n2a$j?FX>4qL",
                   "note": "This is Base85 (RFC 1924 / b85), denser than base64. Use a b85 "
                           "decoder."},
        "hints": ["The odd punctuation is normal for base85's expanded alphabet.",
                  "A Python one-liner: base64.b85decode(...). Result starts with FLAG{."],
        "check": ("exact", "FLAG{base85_is_denser_still}"),
        "teaches": "Base85 appears in PDFs, Git binary diffs, and Adobe formats. More "
                   "efficient than base64 — and, still, not a shred of encryption.",
    },
    {
        "id": "atbash", "title": "Through the Looking Glass", "icon": "🪞",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "Atbash mirrors the alphabet: A<->Z, B<->Y, C<->X ... Decode this ancient "
                 "cipher (it's its own inverse).",
        "target": {"kind": "data",
                   "cipher": "UOZT{zgyzhs_nriilih_gsv_zokszyvg}",
                   "note": "Replace each letter with its mirror: A<->Z, B<->Y ... Apply the "
                           "same mapping to decode."},
        "hints": ["U is the mirror of F (U is 21st from start, F is 6th; 27-6=21).",
                  "UOZT decodes to FLAG."],
        "check": ("exact", "FLAG{atbash_mirrors_the_alphabet}"),
        "teaches": "Atbash is a 3,000-year-old substitution cipher with a fixed key — zero "
                   "security today, but a clean lesson in monoalphabetic substitution.",
    },
    {
        "id": "url-encoding", "title": "Percent Signs Everywhere", "icon": "🔗",
        "difficulty": "Easy", "category": "Crypto", "points": DIFF_XP["Easy"],
        "brief": "URL/percent-encoding turns unsafe characters into %XX hex. Decode this "
                 "back to readable text.",
        "target": {"kind": "data",
                   "encoded": "FLAG%7Bpercent_20_is_a_space%7D",
                   "note": "%7B is '{', %7D is '}', %20 is a space. Each %XX is a hex byte."},
        "hints": ["%7B = 0x7B = '{'. Decode each %XX to its character.",
                  "The braces are %7B and %7D."],
        "check": ("exact", "FLAG{percent_20_is_a_space}"),
        "teaches": "Percent-encoding is how arbitrary bytes travel in URLs. Attackers use "
                   "double-encoding (%252e) to slip past naive filters — always decode "
                   "fully before validating.",
    },
    {
        "id": "rail-fence", "title": "Zigzag", "icon": "🚧",
        "difficulty": "Medium", "category": "Crypto", "points": DIFF_XP["Medium"],
        "brief": "The Rail Fence is a transposition cipher: text is written in a zigzag "
                 "across 3 rails, then read row by row. Reverse it (3 rails).",
        "target": {"kind": "data",
                   "cipher": "F{lnzaLGri_ec_izgAafeg}",
                   "rails": 3,
                   "note": "Write the ciphertext back into the 3-rail zigzag pattern and "
                           "read down the columns to recover the original order."},
        "hints": ["It's transposition — every original letter is present, just reordered.",
                  "Rebuild the zigzag over 3 rails; the plaintext starts FLAG{rail..."],
        "check": ("exact", "FLAG{rail_fence_zigzag}"),
        "teaches": "Transposition ciphers scramble position, not symbols — so letter "
                   "frequencies are unchanged, which is exactly how they're detected and "
                   "broken. A puzzle, not protection.",
    },
    {
        "id": "xor-repeating", "title": "The Key Repeats", "icon": "🔁",
        "difficulty": "Hard", "category": "Crypto", "points": DIFF_XP["Hard"],
        "brief": "This is repeating-key XOR (the byte-level Vigenere). The 3-letter key is "
                 "CAT. XOR the hex back with the repeating key to read the flag.",
        "target": {"kind": "data",
                   "hex": "050d15043a2626313122353d2d260b28242d1c393b311e3d301e222a26312d2426261e"
                          "322c330b213820263229",
                   "key": "CAT",
                   "note": "Decode the hex to bytes, then XOR byte i with key[i % 3] "
                           "(C=0x43, A=0x41, T=0x54). XOR is reversible."},
        "hints": ["XOR the first byte 0x05 with 'C' (0x43) -> 0x46 = 'F'.",
                  "Cycle the key CAT across all bytes; the plaintext starts FLAG{."],
        "check": ("exact", "FLAG{repeating_key_xor_is_vigenere_for_bytes}"),
        "teaches": "Repeating-key XOR is real crypto's weak ancestor: once the key length "
                   "is found (Hamming distance / Kasiski), each position is a single-byte "
                   "XOR you brute-force. Never roll your own crypto.",
    },
    {
        "id": "macro-deob", "title": "The Malicious Macro", "icon": "📎",
        "difficulty": "Hard", "category": "Forensics", "points": DIFF_XP["Hard"],
        "brief": "A phishing doc's VBA macro was extracted. It builds a payload from a "
                 "base64 blob, then runs it. Deobfuscate the blob to reveal what it drops.",
        "target": {"kind": "data",
                   "vba": "Sub AutoOpen()\n"
                          "  p = \"RkxBR3ttYWNyb3NfaGlkZV9pbl9iYXNlNjR9\"\n"
                          "  Set o = CreateObject(\"WScript.Shell\")\n"
                          "  o.Run Decode64(p), 0, False\n"
                          "End Sub",
                   "note": "AutoOpen runs the macro on document open. The base64 string is "
                           "the real payload — decode it (do NOT run macros!)."},
        "hints": ["The interesting part is the base64 string assigned to p.",
                  "base64-decode it to see what the macro would execute."],
        "check": ("exact", "FLAG{macros_hide_in_base64}"),
        "teaches": "Office macro malware hides payloads in base64/obfuscation and fires on "
                   "AutoOpen. Disable macros by policy, block macros from the internet, and "
                   "analyze in a sandbox — never enable content on an unexpected doc.",
    },
    {
        "id": "s3-open-bucket", "title": "The Bucket Left Open", "icon": "🪣",
        "difficulty": "Easy", "category": "OSINT", "points": DIFF_XP["Easy"],
        "brief": "A cloud storage bucket was set to public. Its directory listing is right "
                 "here — read it and grab the flag from the exposed file.",
        "target": {"kind": "data",
                   "listing": "$ curl https://vertex-backups.s3.amazonaws.com/\n"
                              "<ListBucketResult>\n"
                              "  <Key>logo.png</Key>\n"
                              "  <Key>db-backup-2026-07.sql</Key>\n"
                              "  <Key>secrets/prod.txt</Key>  ->  FLAG{public_buckets_leak_everything}\n"
                              "</ListBucketResult>",
                   "note": "A public bucket lists (and serves) every object. The flag sits "
                           "in the exposed secrets file."},
        "hints": ["Public buckets let anyone list all keys — read the secrets/ file.",
                  "The flag is next to secrets/prod.txt."],
        "check": ("exact", "FLAG{public_buckets_leak_everything}"),
        "teaches": "Misconfigured public buckets are a top cause of mass data leaks. "
                   "Default to private, block public access at the account level, and audit "
                   "bucket policies continuously.",
    },
    {
        "id": "api-key-in-js", "title": "Secrets in the Source Bundle", "icon": "📦",
        "difficulty": "Easy", "category": "Recon", "points": DIFF_XP["Easy"],
        "brief": "Front-end JavaScript ships to every visitor — so any secret in it is "
                 "public. This bundle hardcoded one. Find it.",
        "target": {"kind": "data",
                   "js": "// app.min.js (served to every browser)\n"
                         "const API_BASE='https://api.vertexdental.com';\n"
                         "const ADMIN_API_KEY='FLAG{secrets_dont_belong_in_frontend}';\n"
                         "fetch(API_BASE+'/me',{headers:{'X-Key':ADMIN_API_KEY}});",
                   "note": "Anything in client-side JS is readable via View Source / "
                           "DevTools. Never ship secrets to the browser."},
        "hints": ["Read the JS — the key is assigned to a constant.",
                  "ADMIN_API_KEY holds the flag."],
        "check": ("exact", "FLAG{secrets_dont_belong_in_frontend}"),
        "teaches": "Client-side code is public by definition. Keep secrets server-side, "
                   "use short-lived scoped tokens, and proxy privileged calls through your "
                   "backend — never embed API keys in front-end bundles.",
    },
    {
        "id": "sqlite-strings", "title": "Strings Never Lie", "icon": "🧵",
        "difficulty": "Medium", "category": "Forensics", "points": DIFF_XP["Medium"],
        "brief": "You recovered a leaked app database file. Running `strings` on it dumps "
                 "readable text — including something that should have been hashed. Find it.",
        "target": {"kind": "data",
                   "strings": "$ strings app.db | grep -i flag\n"
                              "SQLite format 3\n"
                              "users\x00id\x00email\x00password\n"
                              "admin@vertexdental.com\n"
                              "reset_token=FLAG{plaintext_in_the_db}\n"
                              "CREATE TABLE sessions(...)",
                   "note": "`strings` extracts printable sequences from any binary. Secrets "
                           "stored in cleartext show right up."},
        "hints": ["Scan the strings output for a token or password stored in the clear.",
                  "The reset_token value is the flag."],
        "check": ("exact", "FLAG{plaintext_in_the_db}"),
        "teaches": "A stolen database gives up everything stored in cleartext. Hash "
                   "passwords (Argon2/bcrypt), encrypt sensitive columns, and keep tokens "
                   "short-lived and single-use.",
    },
    {
        "id": "host-header", "title": "Poisoning the Reset Link", "icon": "📨",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "This password-reset builds its link from the incoming Host header. Change "
                 "the host and the reset email points at YOUR server (token theft). Prove it.",
        "target": {"kind": "probe",
                   "instructions": "The reset link uses whatever host you send. Try the "
                                   "real host, then an attacker host.",
                   "examples": ["?host=portal.vertexdental.com", "?host=evil.attacker.com"]},
        "hints": ["Send host=evil.attacker.com — the emailed reset link will use it.",
                  "When the link points off-domain, the lab returns the flag."],
        "check": ("exact", "FLAG{never_trust_the_host_header}"),
        "teaches": "Host-header injection lets attackers poison password-reset links and "
                   "cache keys. Build absolute URLs from a configured canonical host, and "
                   "validate/allowlist the Host header at the edge.",
    },
    {
        "id": "ldap-injection", "title": "Wildcards in the Directory", "icon": "📇",
        "difficulty": "Medium", "category": "Web", "points": DIFF_XP["Medium"],
        "brief": "This login builds an LDAP filter from your input. Special characters like "
                 "* and )( let you rewrite the filter into 'match anything'. Bypass the login.",
        "target": {"kind": "probe",
                   "instructions": "Your user value goes straight into an LDAP filter. Try a "
                                   "normal name, then an injection with * and )(.",
                   "examples": ["?user=jdoe", "?user=*", "?user=*)(uid=*"]},
        "hints": ["An unescaped * or a )(uid=*) turns the filter into a tautology.",
                  "Send user=*)(uid=* to match every entry and bypass auth."],
        "check": ("exact", "FLAG{ldap_filters_need_escaping}"),
        "teaches": "LDAP injection abuses filter metacharacters ( * ( ) \\ | & ) the same "
                   "way SQLi abuses quotes. Escape all input per RFC 4515 and use "
                   "parameterized directory queries.",
    },
    {
        "id": "xxe", "title": "The XML That Reads Files", "icon": "📄",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "This XML upload parser resolves external entities. Define an entity that "
                 "points at a local file and the parser will read it back to you (XXE).",
        "target": {"kind": "probe",
                   "instructions": "Send an xml value. Try a plain doc, then one declaring "
                                   "an external entity pointing at a system file.",
                   "examples": ["?xml=<note>hi</note>",
                                "?xml=<!DOCTYPE r [<!ENTITY x SYSTEM \"file:///etc/passwd\">]><r>&x;</r>"]},
        "hints": ["Declare a DOCTYPE with an ENTITY using SYSTEM \"file:///...\" and "
                  "reference it in the body.", "Point the entity at file:///etc/passwd — "
                  "the parser inlines the file and the flag with it."],
        "check": ("exact", "FLAG{xxe_reads_local_files}"),
        "teaches": "XML External Entity injection reads local files, performs SSRF, and can "
                   "DoS the parser. Disable DTD/external-entity processing in your XML "
                   "parser (secure defaults) — the fix is one configuration flag.",
    },
    {
        "id": "insecure-deser", "title": "Trusting a Pickle", "icon": "🥒",
        "difficulty": "Hard", "category": "Web", "points": DIFF_XP["Hard"],
        "brief": "This app base64-decodes a cookie and deserializes it with pickle — which "
                 "can execute code on load. Send a payload the app would 'unpickle' to win.",
        "target": {"kind": "probe",
                   "instructions": "The 'data' param is base64 that gets unpickled. Try "
                                   "harmless data, then a payload marked as an object with a "
                                   "__reduce__ / os.system gadget.",
                   "examples": ["?data=normal", "?data=__reduce__:os.system",
                                "?data=pickle:cos.system"]},
        "hints": ["Deserializing attacker data runs its embedded gadget — signal an "
                  "os.system/__reduce__ payload.", "Include 'os.system' or '__reduce__' in "
                  "the data to trigger the (simulated) code execution and the flag."],
        "check": ("exact", "FLAG{never_deserialize_untrusted_data}"),
        "teaches": "Insecure deserialization (pickle, Java, PHP unserialize, YAML load) "
                   "turns data into code execution. Never deserialize untrusted input; use "
                   "safe formats (JSON) and sign/validate any serialized state you must trust.",
    },
]

# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
_LESSONS = {l["id"]: l for m in MODULES for l in m["lessons"]}
_GAMES = {g["id"]: g for g in GAMES}
_LABS = {b["id"]: b for b in LABS}
TOTAL_LESSONS = len(_LESSONS)
TOTAL_LABS = len(_LABS)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_profile(db: Session, user: User) -> AcademyProfile:
    prof = (db.query(AcademyProfile)
            .filter(AcademyProfile.user_id == user.id).first())
    if not prof:
        prof = AcademyProfile(user_id=user.id, xp=0, streak_days=0, badges="[]")
        db.add(prof)
        db.commit()
    return prof


def _badges(prof: AcademyProfile) -> list[str]:
    try:
        return list(json.loads(prof.badges or "[]"))
    except Exception:  # noqa: BLE001
        return []


def _level(xp: int) -> dict:
    idx = min(xp // LEVEL_XP, len(LEVELS) - 1)
    return {"n": idx + 1, "title": LEVELS[idx],
            "xp_into": xp - idx * LEVEL_XP,
            "xp_needed": LEVEL_XP if idx < len(LEVELS) - 1 else 0}


def _touch_streak(prof: AcademyProfile, today: date) -> None:
    if prof.last_active_on == today:
        return
    if prof.last_active_on == today - timedelta(days=1):
        prof.streak_days = (prof.streak_days or 0) + 1
    else:
        prof.streak_days = 1
    prof.last_active_on = today


def _award(db: Session, user: User, prof: AcademyProfile, item_id: str,
           kind: str, score: int | None, max_score: int | None,
           xp_override: int | None = None) -> tuple[int, list[str]]:
    """Record a completion; award XP only the first time. Returns (xp_gained,
    newly earned badge ids)."""
    now = _utcnow()
    first = not (db.query(AcademyCompletion)
                 .filter(AcademyCompletion.user_id == user.id,
                         AcademyCompletion.item_id == item_id).first())
    xp = 0
    if first:
        if xp_override is not None:
            xp = xp_override
        elif kind == "lesson":
            xp = LESSON_XP + (PERFECT_BONUS if score is not None and score == max_score else 0)
        else:
            xp = GAME_XP
    db.add(AcademyCompletion(user_id=user.id, item_id=item_id, kind=kind,
                             score=score, xp=xp, created_at=now))
    prof.xp = (prof.xp or 0) + xp
    _touch_streak(prof, now.date())

    have = set(_badges(prof))
    new: list[str] = []

    def earn(bid: str, cond: bool):
        if cond and bid not in have:
            have.add(bid)
            new.append(bid)

    done_lessons = {c.item_id for c in db.query(AcademyCompletion)
                    .filter(AcademyCompletion.user_id == user.id,
                            AcademyCompletion.kind == "lesson")} | (
                        {item_id} if kind == "lesson" else set())
    done_lessons &= set(_LESSONS)
    done_labs = {c.item_id for c in db.query(AcademyCompletion)
                 .filter(AcademyCompletion.user_id == user.id,
                         AcademyCompletion.kind == "lab")} | (
                     {item_id} if kind == "lab" else set())
    done_labs &= set(_LABS)
    earn("first_steps", kind == "lesson")
    earn("quiz_perfect", kind == "lesson" and score is not None and score == max_score)
    earn("phish_master", item_id == "phish-or-legit" and score is not None and score == max_score)
    earn("lab_rat", item_id == "password-lab")
    earn("first_flag", kind == "lab")
    earn("range_5", len(done_labs) >= 5)
    earn("range_all", len(done_labs) >= TOTAL_LABS)
    earn("l33t", kind == "lab" and _LABS.get(item_id, {}).get("difficulty") == "Hard")
    earn("streak_3", (prof.streak_days or 0) >= 3)
    earn("streak_7", (prof.streak_days or 0) >= 7)
    earn("half_way", len(done_lessons) * 2 >= TOTAL_LESSONS)
    earn("all_lessons", len(done_lessons) >= TOTAL_LESSONS)
    earn("xp_500", (prof.xp or 0) >= 500)

    prof.badges = json.dumps(sorted(have))
    db.commit()
    return xp, new


def profile_view(db: Session, user: User) -> dict:
    prof = get_profile(db, user)
    today = _utcnow().date()
    # A streak survives until a full day is missed.
    live_streak = prof.streak_days or 0
    if prof.last_active_on and prof.last_active_on < today - timedelta(days=1):
        live_streak = 0
    from ..models import STAFF_ROLES
    return {
        "xp": prof.xp or 0,
        "level": _level(prof.xp or 0),
        "streak_days": live_streak,
        "active_today": prof.last_active_on == today,
        "is_staff": user.role in STAFF_ROLES,
        "badges": [{**BADGES[b], "id": b} for b in _badges(prof) if b in BADGES],
        "all_badges": [{**v, "id": k, "earned": k in _badges(prof)}
                       for k, v in BADGES.items()],
    }


def catalog_view(db: Session, user: User) -> dict:
    done = {c.item_id: c for c in db.query(AcademyCompletion)
            .filter(AcademyCompletion.user_id == user.id)}
    mods = []
    for m in MODULES:
        lessons = []
        for l in m["lessons"]:
            c = done.get(l["id"])
            lessons.append({"id": l["id"], "title": l["title"], "icon": l["icon"],
                            "minutes": l["minutes"], "questions": len(l["quiz"]),
                            "xp": LESSON_XP, "completed": bool(c),
                            "score": c.score if c else None})
        mods.append({"id": m["id"], "title": m["title"], "icon": m["icon"],
                     "blurb": m["blurb"], "lessons": lessons})
    games = []
    for g in GAMES:
        c = done.get(g["id"])
        games.append({"id": g["id"], "title": g["title"], "icon": g["icon"],
                      "blurb": g["blurb"], "kind": g["kind"], "xp": GAME_XP,
                      "completed": bool(c), "score": c.score if c else None,
                      "rounds": len(g["items"]) or None})
    return {"modules": mods, "games": games, "total_lessons": TOTAL_LESSONS,
            "range": range_view(db, user)}


def lesson_view(db: Session, lesson_id: str) -> dict | None:
    l = _LESSONS.get(lesson_id)
    if not l:
        return None
    quiz = _merged_quiz(db, l)   # base + this month's AI-refreshed questions
    return {"id": l["id"], "title": l["title"], "icon": l["icon"],
            "minutes": l["minutes"], "body": l["body"],
            "quiz": [{"q": q["q"], "choices": q["choices"]} for q in quiz]}


def grade_lesson(db: Session, user: User, lesson_id: str,
                 answers: list[int]) -> dict | None:
    l = _LESSONS.get(lesson_id)
    if not l:
        return None
    quiz = _merged_quiz(db, l)   # same merge as lesson_view or grading skews
    results = []
    score = 0
    for i, q in enumerate(quiz):
        given = answers[i] if i < len(answers) else -1
        ok = given == q["answer"]
        score += 1 if ok else 0
        results.append({"correct": ok, "answer": q["answer"],
                        "explain": q["explain"]})
    prof = get_profile(db, user)
    xp, new_badges = _award(db, user, prof, lesson_id, "lesson", score, len(quiz))
    return {"score": score, "total": len(quiz), "results": results,
            "xp_gained": xp, "profile": profile_view(db, user),
            "new_badges": [{**BADGES[b], "id": b} for b in new_badges]}


def game_view(game_id: str) -> dict | None:
    g = _GAMES.get(game_id)
    if not g:
        return None
    out = {"id": g["id"], "title": g["title"], "icon": g["icon"],
           "blurb": g["blurb"], "kind": g["kind"]}
    if g["kind"] == "phish":
        out["items"] = [{"from_name": it["from_name"], "from_addr": it["from_addr"],
                         "subject": it["subject"], "body": it["body"]}
                        for it in g["items"]]
    return out


def grade_game(db: Session, user: User, game_id: str, answers: list) -> dict | None:
    g = _GAMES.get(game_id)
    if not g:
        return None
    if g["kind"] == "phish":
        items = g["items"]
        results = []
        score = 0
        for i, it in enumerate(items):
            given = bool(answers[i]) if i < len(answers) else None
            ok = given == it["is_phish"]
            score += 1 if ok else 0
            results.append({"correct": ok, "is_phish": it["is_phish"],
                            "explain": it["explain"]})
        prof = get_profile(db, user)
        xp, new_badges = _award(db, user, prof, game_id, "game", score, len(items))
        return {"score": score, "total": len(items), "results": results,
                "xp_gained": xp, "profile": profile_view(db, user),
                "new_badges": [{**BADGES[b], "id": b} for b in new_badges]}
    # password-lab: client-side interactive; completion means the goal was met.
    prof = get_profile(db, user)
    xp, new_badges = _award(db, user, prof, game_id, "game", None, None)
    return {"score": None, "total": None, "results": [],
            "xp_gained": xp, "profile": profile_view(db, user),
            "new_badges": [{**BADGES[b], "id": b} for b in new_badges]}


# --------------------------------------------------------------------------- #
# Cyber Range — views, the SAFE emulator (probe), flag checkers, grading.
# --------------------------------------------------------------------------- #
def range_view(db: Session, user: User) -> dict:
    """Catalog of labs with per-user solved state, grouped-friendly + summary."""
    solved = {c.item_id for c in db.query(AcademyCompletion)
              .filter(AcademyCompletion.user_id == user.id,
                      AcademyCompletion.kind == "lab")}
    labs = [{"id": b["id"], "title": b["title"], "icon": b["icon"],
             "difficulty": b["difficulty"], "category": b["category"],
             "points": b["points"], "solved": b["id"] in solved}
            for b in LABS]
    return {"labs": labs, "total": TOTAL_LABS,
            "solved": len([b for b in labs if b["solved"]])}


def lab_view(db: Session, user: User, lab_id: str) -> dict | None:
    """A single lab WITHOUT the flag or checker — everything needed to attempt it."""
    b = _LABS.get(lab_id)
    if not b:
        return None
    solved = bool(db.query(AcademyCompletion)
                  .filter(AcademyCompletion.user_id == user.id,
                          AcademyCompletion.item_id == lab_id,
                          AcademyCompletion.kind == "lab").first())
    return {"id": b["id"], "title": b["title"], "icon": b["icon"],
            "difficulty": b["difficulty"], "category": b["category"],
            "points": b["points"], "brief": b["brief"], "target": b["target"],
            "hints": b["hints"], "teaches": b["teaches"], "solved": solved}


def lab_probe(lab_id: str, params: dict) -> dict:
    """The SAFE emulator: hardcoded simulators of each vulnerable behavior. No
    real backend, no code execution, no filesystem — just deterministic canned
    responses that teach the technique. Returns {status, body} like an HTTP hit."""
    b = _LABS.get(lab_id)
    if not b or b["target"].get("kind") != "probe":
        return {"status": 404, "body": "No such lab endpoint."}

    def resp(status, body):
        return {"status": status, "body": body}

    if lab_id == "robots-recon":
        path = (params.get("path") or "").strip()
        if path in ("/robots.txt", "robots.txt"):
            return resp(200, "User-agent: *\nDisallow: /internal-backups-7f3/\n"
                             "Disallow: /admin\nSitemap: /sitemap.xml")
        if path.strip("/") == "internal-backups-7f3":
            return resp(200, "Index of /internal-backups-7f3/\n"
                             "  db_dump_2026.sql\n  NOTES.txt  -> FLAG{robots_txt_is_a_treasure_map}")
        return resp(404, "404 Not Found. (Try /robots.txt first.)")

    if lab_id == "idor-invoice":
        try:
            iid = int(params.get("id") or 0)
        except ValueError:
            return resp(400, "id must be a number, e.g. ?id=4021")
        if iid == 4021:
            return resp(200, "Invoice #4021 — YOUR account (Acme Co) — Balance $0.00")
        if iid == 4020:
            return resp(200, "Invoice #4020 — Vertex Dental — memo: FLAG{idor_means_check_the_owner}")
        if 4000 <= iid <= 4030:
            return resp(200, f"Invoice #{iid} — [another customer] — no memo")
        return resp(404, "Invoice not found.")

    if lab_id == "sqli-login":
        user_in = (params.get("user") or "")
        pass_in = (params.get("pass") or "")
        if _sqli_bypasses(pass_in) or _sqli_bypasses(user_in):
            return resp(200, "Login OK — welcome, admin. FLAG{sql_injection_needs_parameterized_queries}")
        return resp(401, "Invalid username or password.")

    if lab_id == "path-traversal":
        f = (params.get("file") or "").replace("\\", "/")
        base = f.split("/")[-1]
        if f in ("welcome.txt", "welcome.txt".lstrip("/")) and "/" not in f:
            return resp(200, "Welcome to Vertex Dental's document portal.")
        if "../" in f and base == "passwd":
            return resp(200, "root:x:0:0:root:/root:/bin/bash\n"
                             "www-data:x:33:33:/var/www:/usr/sbin/nologin\n"
                             "# FLAG{never_trust_a_filename_from_a_user}")
        if "../" in f:
            return resp(404, "File not found (you escaped the folder — now aim for etc/passwd).")
        return resp(200, f"[contents of files/{base}]")

    if lab_id == "git-exposed":
        path = (params.get("path") or "").strip().lower().strip("/")
        if path == ".git/config":
            return resp(200, "[core]\n\trepositoryformatversion = 0\n"
                             "[remote \"origin\"]\n\turl = git@github.com:vertex/portal.git\n"
                             "(exposed! now read .git/logs/HEAD)")
        if path == ".git/logs/head":
            return resp(200, "0000000 a1b2c3d Jordan <j@vertex> commit: initial portal\n"
                             "a1b2c3d 9f8e7d6 Jordan <j@vertex> commit: remove hardcoded key "
                             "FLAG{dot_git_is_a_time_machine}")
        if path.startswith(".git"):
            return resp(200, "(exists) try .git/config then .git/logs/HEAD")
        return resp(404, "Not found. Probe under /.git/ — start with ?path=/.git/config")

    if lab_id == "open-redirect":
        nxt = (params.get("next") or "").strip()
        if nxt.lower().startswith(("http://", "https://", "//")):
            return resp(302, f"Redirecting off-site to {nxt} — no validation! "
                             "FLAG{always_validate_redirect_targets}")
        if nxt:
            return resp(302, f"Redirecting to internal path {nxt} (safe).")
        return resp(400, "Provide ?next=. Try an external URL to prove the redirect.")

    if lab_id == "xss-reflected":
        q = params.get("q") or ""
        low = q.lower()
        # SAFE: pattern-match a script-injection shape; nothing is rendered or run.
        if ("<script" in low or "onerror=" in low or "onload=" in low
                or "<img" in low and "=" in low and "alert" in low):
            return resp(200, "Your input was reflected UNENCODED into the page — a browser "
                             "would execute it. FLAG{encode_output_stop_reflected_xss}")
        return resp(200, f"You searched for: {q} (0 results)")

    if lab_id == "mass-assignment":
        low = {k.lower(): str(v).lower() for k, v in params.items()}
        if low.get("role") == "admin" or low.get("is_admin") in ("true", "1", "yes") \
                or low.get("admin") in ("true", "1", "yes"):
            return resp(200, "Profile updated. role=admin was bound from your request! "
                             "FLAG{never_bind_untrusted_fields}")
        return resp(200, f"Profile updated: name={params.get('name', '(unchanged)')}, role=user")

    if lab_id == "ssrf-metadata":
        url = (params.get("url") or "").strip().lower()
        if "169.254.169.254" in url:
            if "iam" in url or "security-cred" in url or "meta-data/iam" in url:
                return resp(200, "{ \"AccessKeyId\": \"ASIA...\", \"SecretAccessKey\": "
                                 "\"FLAG{ssrf_reaches_the_metadata_service}\" }")
            return resp(200, "meta-data/\n  iam/\n  hostname\n  (drill into iam/ for creds)")
        if url.startswith(("http://", "https://")):
            return resp(200, "<html>example page</html> (external fetch OK — now aim inward)")
        return resp(400, "Provide ?url=. The server fetches it for you.")

    if lab_id == "cmd-injection":
        host = params.get("host") or ""
        # SAFE: detect a shell-chaining pattern in the input; no shell is invoked.
        if any(sep in host for sep in (";", "|", "&&", "`", "$(")) and \
                any(kw in host.lower() for kw in ("cat", "flag", "ls", "id", "whoami")):
            return resp(200, "PING 8.8.8.8 ... 0% loss\nflag.txt: "
                             "FLAG{never_pass_user_input_to_a_shell}")
        if host:
            return resp(200, f"PING {host} ... 64 bytes, 0% packet loss")
        return resp(400, "Provide ?host= to ping.")

    if lab_id == "exposed-env":
        path = (params.get("path") or "").strip().lower().lstrip("/")
        if path == ".env":
            return resp(200, "APP_ENV=production\nDB_PASSWORD=hunter2\n"
                             "APP_SECRET=FLAG{never_ship_dot_env}")
        if path in ("index.html", ""):
            return resp(200, "<html>Vertex Dental</html>")
        return resp(404, "Not found. Try a sensitive dotfile like ?path=/.env")

    if lab_id == "ssti":
        name = params.get("name") or ""
        if "{{" in name and "}}" in name:
            inner = name[name.find("{{") + 2:name.find("}}")].strip().replace(" ", "")
            if inner == "7*7":
                return resp(200, "Hello, 49  <-- the engine EVALUATED your input! "
                                 "FLAG{template_injection_runs_code}")
            if inner in ("config", "self", "7*'7'"):
                return resp(200, "Hello, <Config {...}>  (engine is evaluating — try {{7*7}})")
            return resp(200, f"Hello, [rendered:{inner}]  (it evaluated — now prove it with 7*7)")
        return resp(200, f"Hello, {name}")

    if lab_id == "nosql-auth":
        # operator injection arrives as pass[$ne]=x -> param key "pass[$ne]"
        keys = " ".join(params.keys()).lower()
        if "$ne" in keys or "$gt" in keys or "$regex" in keys:
            return resp(200, "Authentication bypassed via query operator! Welcome admin. "
                             "FLAG{nosql_operators_are_injectable}")
        if params.get("user") and params.get("pass"):
            return resp(401, "Invalid username or password.")
        return resp(400, "Provide user and pass (try a $ne operator on pass).")

    if lab_id == "graphql-introspection":
        q = (params.get("query") or "").replace(" ", "").lower()
        if "__schema" in q:
            return resp(200, "{ queryType: { fields: [ {name:'me'}, {name:'secretFlag'} ] } }\n"
                             "(introspection ON — a hidden field 'secretFlag' exists. Query it.)")
        if "secretflag" in q:
            return resp(200, "{ \"data\": { \"secretFlag\": "
                             "\"FLAG{introspection_maps_the_whole_api}\" } }")
        if "me" in q:
            return resp(200, "{ \"data\": { \"me\": { \"name\": \"guest\" } } }")
        return resp(400, "Send a ?query={...}. Introspection is a good start.")

    if lab_id == "cors-misconfig":
        origin = (params.get("origin") or "").strip()
        if origin.lower().startswith(("http://", "https://")):
            trusted = origin.lower().rstrip("/").endswith("vertexdental.com")
            if not trusted:
                return resp(200, f"Access-Control-Allow-Origin: {origin}\n"
                                 "Access-Control-Allow-Credentials: true\n"
                                 "{ \"note\": \"FLAG{cors_reflect_plus_credentials}\" }")
            return resp(200, f"Access-Control-Allow-Origin: {origin} (trusted own site)")
        return resp(400, "Provide ?origin= (an https URL).")

    if lab_id == "host-header":
        host = (params.get("host") or "").strip().lower()
        if host and not host.endswith("vertexdental.com"):
            return resp(200, f"Password reset link sent: https://{host}/reset?token=abc123\n"
                             "The link uses YOUR host — a victim's token goes to you. "
                             "FLAG{never_trust_the_host_header}")
        if host:
            return resp(200, f"Reset link: https://{host}/reset?token=abc123 (canonical host)")
        return resp(400, "Provide ?host= (the request Host header).")

    if lab_id == "ldap-injection":
        user = params.get("user") or ""
        if "*" in user or ")(" in user or "|(" in user:
            return resp(200, "LDAP filter became (uid=*)(uid=*) — matches everyone. "
                             "Bound as admin. FLAG{ldap_filters_need_escaping}")
        if user:
            return resp(401, f"No directory entry for uid={user}.")
        return resp(400, "Provide ?user= (goes into an LDAP filter).")

    if lab_id == "xxe":
        xml = params.get("xml") or ""
        low = xml.lower()
        if "<!entity" in low and "system" in low and ("file://" in low or "/etc/passwd" in low):
            return resp(200, "Parsed. Entity expanded to file contents:\n"
                             "root:x:0:0:root:/root:/bin/bash\n# FLAG{xxe_reads_local_files}")
        if "<!doctype" in low or "<!entity" in low:
            return resp(200, "DTD seen — declare an external SYSTEM entity to file:///etc/passwd.")
        if xml:
            return resp(200, "<parsed>ok</parsed> (no external entities in this document)")
        return resp(400, "Provide ?xml= to parse.")

    if lab_id == "insecure-deser":
        data = (params.get("data") or "").lower()
        if "__reduce__" in data or "os.system" in data or "subprocess" in data \
                or "cos\nsystem" in data or "pickle:c" in data:
            return resp(200, "Unpickling executed the embedded gadget (simulated). "
                             "FLAG{never_deserialize_untrusted_data}")
        if data:
            return resp(200, "Deserialized a plain object — no code gadget present.")
        return resp(400, "Provide ?data= (base64 that gets unpickled).")

    return resp(404, "No such lab endpoint.")


def _sqli_bypasses(s: str) -> bool:
    """Detect a classic authentication-bypass tautology in a login field. This
    only PATTERN-MATCHES a teaching payload; no SQL is ever built or run."""
    t = (s or "").lower().replace(" ", "")
    if "'or'1'='1" in t or '"or"1"="1' in t:
        return True
    if "or1=1" in t and ("--" in t or "'" in t or '"' in t or "#" in t):
        return True
    return False


def _check_flag(b: dict, submission: str) -> bool:
    """Server-side flag verification. The client never receives the answer."""
    kind, expected = b["check"]
    s = (submission or "").strip()
    if kind == "exact":
        return s == expected
    if kind == "md5":
        return _hashlib.md5(s.encode("utf-8", "ignore")).hexdigest() == expected
    if kind == "sha1":
        return _hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest() == expected
    if kind == "regex_waf":
        # Interactive defense lab: the learner submits a REGEX. We compile it
        # safely and require it to match every attack string and no benign one.
        # The candidate strings live on the lab (b["target"]) so the server is
        # the single source of truth; nothing but a pattern is ever evaluated.
        import re as _re
        pat = s
        if not pat or len(pat) > 200:
            return False
        try:
            rx = _re.compile(pat, _re.IGNORECASE)
        except _re.error:
            return False
        tgt = b.get("target") or {}
        attacks = tgt.get("attacks") or []
        benign = tgt.get("benign") or []
        if not attacks:
            return False
        try:
            return (all(rx.search(a) for a in attacks)
                    and not any(rx.search(bn) for bn in benign))
        except Exception:  # noqa: BLE001 — a pathological pattern must never crash grading
            return False
    if kind == "cookie_admin":
        try:
            raw = _b64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            return False
        return (data.get("admin") is True
                or str(data.get("role", "")).lower() == "admin")
    if kind == "jwt_none":
        parts = s.split(".")
        if len(parts) < 2:
            return False
        try:
            def _dec(p):
                return json.loads(_b64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
            header, payload = _dec(parts[0]), _dec(parts[1])
        except Exception:  # noqa: BLE001
            return False
        alg = str(header.get("alg", "")).lower()
        sig = parts[2] if len(parts) > 2 else ""
        return alg == "none" and str(payload.get("role", "")).lower() == "admin" and not sig
    if kind == "sqli":
        return _sqli_bypasses(s)
    return False


def grade_lab(db: Session, user: User, lab_id: str, submission: str) -> dict | None:
    """Check a flag submission; award difficulty-scaled XP the first time solved."""
    b = _LABS.get(lab_id)
    if not b:
        return None
    if not _check_flag(b, submission):
        return {"solved": False,
                "message": "Not quite — that's not the flag. Check the hints and try again."}
    prof = get_profile(db, user)
    xp, new_badges = _award(db, user, prof, lab_id, "lab", None, None,
                            xp_override=b["points"])
    return {"solved": True, "xp_gained": xp,
            "message": ("🚩 Flag captured!" if xp else "Already solved — nice work."),
            "teaches": b["teaches"], "profile": profile_view(db, user),
            "new_badges": [{**BADGES[bd], "id": bd} for bd in new_badges]}


def leaderboard(db: Session, user: User, *, staff: bool) -> list[dict]:
    """Top 20 by XP. Client users only see their own company's people —
    tenant isolation applies to gamification too."""
    q = (db.query(AcademyProfile, User)
         .join(User, User.id == AcademyProfile.user_id)
         .filter(User.is_active.is_(True), AcademyProfile.xp > 0))
    if not staff:
        q = q.filter(User.client_id == user.client_id)
    rows = q.order_by(AcademyProfile.xp.desc()).limit(20).all()
    out = []
    for i, (prof, u) in enumerate(rows):
        name = (u.full_name or u.email.split("@")[0]).strip()
        parts = name.split()
        display = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")
        out.append({"rank": i + 1, "name": display, "xp": prof.xp,
                    "level": _level(prof.xp or 0), "streak": prof.streak_days or 0,
                    "you": u.id == user.id})
    return out


# --------------------------------------------------------------------------- #
# v1.3 — training compliance, streak-saver reminders, AI-refreshed questions
# --------------------------------------------------------------------------- #
def client_compliance(db: Session, client_id: int) -> dict:
    """Per-client training adoption — the QBR number: how many of this client's
    people train, and how much of the curriculum they've covered."""
    users = (db.query(User)
             .filter(User.client_id == client_id, User.is_active.is_(True)).all())
    uids = [u.id for u in users]
    if not uids:
        return {"users": 0, "trained_users": 0, "trained_pct": None,
                "lessons_done": 0, "curriculum_pct": None, "top_learner": None}
    comps = (db.query(AcademyCompletion)
             .filter(AcademyCompletion.user_id.in_(uids),
                     AcademyCompletion.kind == "lesson").all())
    per_user: dict[int, set] = {}
    for c in comps:
        if c.item_id in _LESSONS:
            per_user.setdefault(c.user_id, set()).add(c.item_id)
    trained = len(per_user)
    lessons_done = sum(len(v) for v in per_user.values())
    top = None
    profs = (db.query(AcademyProfile, User)
             .join(User, User.id == AcademyProfile.user_id)
             .filter(AcademyProfile.user_id.in_(uids), AcademyProfile.xp > 0)
             .order_by(AcademyProfile.xp.desc()).first())
    if profs:
        p, u = profs
        nm = (u.full_name or u.email.split("@")[0]).strip()
        top = {"name": nm, "xp": p.xp}
    return {
        "users": len(uids),
        "trained_users": trained,
        "trained_pct": round(100 * trained / len(uids)) if uids else None,
        "lessons_done": lessons_done,
        "curriculum_pct": round(100 * lessons_done / (len(uids) * TOTAL_LESSONS)),
        "top_learner": top,
    }


def compliance_all(db: Session) -> list[dict]:
    """Training adoption for every client — the staff dashboard table."""
    from ..models import Client
    out = []
    for cli in db.query(Client).order_by(Client.name.asc()).all():
        row = client_compliance(db, cli.id)
        row["client_id"] = cli.id
        row["client"] = cli.name
        out.append(row)
    return out


REMINDER_HOUR_UTC = 16   # ~11am Central: the nudge lands during the workday


def streak_reminders(db: Session, now: datetime | None = None) -> list[dict]:
    """Email users whose streak dies at midnight UTC (trained yesterday, not yet
    today). At most one reminder per user per day; only streaks worth saving
    (>= 2 days). Email sending is a safe no-op when SMTP isn't configured."""
    from . import email as email_svc
    now = now or _utcnow()
    if now.hour < REMINDER_HOUR_UTC:
        return []
    from ..core.config import get_settings
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    today = now.date()
    yesterday = today - timedelta(days=1)
    rows = (db.query(AcademyProfile, User)
            .join(User, User.id == AcademyProfile.user_id)
            .filter(AcademyProfile.last_active_on == yesterday,
                    AcademyProfile.streak_days >= 2,
                    User.is_active.is_(True)).all())
    sent = []
    for prof, u in rows:
        if prof.last_reminder_on == today or not u.email:
            continue
        first = (u.full_name or u.email.split("@")[0]).split()[0]
        subject = f"🔥 Your {prof.streak_days}-day streak expires tonight"
        body = (f"Hey {first},\n\n"
                f"Your {prof.streak_days}-day learning streak on the Pulse Cyber "
                f"Academy ends at midnight — one quick lesson or game keeps it alive "
                f"(most take about 5 minutes).\n\n"
                f"Save it here: {base}/academy\n\n"
                f"— Pulse Cyber Academy")
        try:
            email_svc.send(u.email, subject, body)
            prof.last_reminder_on = today
            sent.append({"user_id": u.id, "streak": prof.streak_days})
        except Exception:  # noqa: BLE001
            pass
    if sent:
        db.commit()
    return sent


# ---- AI-refreshed quiz questions (monthly, via Claude) ---------------------- #
AI_QUESTIONS_PER_LESSON = 2

_AI_QGEN_SYSTEM = (
    "You write quiz questions for a workplace security-awareness course. "
    "Reply with ONLY a JSON array (no prose, no markdown fences) of exactly "
    "{n} objects, each with keys: "
    '"q" (one clear scenario-based question, max 200 chars), '
    '"choices" (array of exactly 4 plausible answers, one correct), '
    '"answer" (0-based index of the correct choice), '
    '"explain" (1-2 sentences on why, max 250 chars). '
    "Questions must test judgment on realistic situations, never trivia, and "
    "must be answerable from the lesson content alone."
)


def _active_ai_questions(db: Session, lesson_id: str) -> list:
    from ..models import AcademyAiQuestion
    return (db.query(AcademyAiQuestion)
            .filter(AcademyAiQuestion.lesson_id == lesson_id,
                    AcademyAiQuestion.active.is_(True))
            .order_by(AcademyAiQuestion.id.asc()).all())


def _merged_quiz(db: Session, lesson: dict) -> list[dict]:
    """Base (hand-written) questions plus the active AI batch, in stable order —
    lesson_view and grade_lesson MUST use the same merge or grading skews."""
    quiz = list(lesson["quiz"])
    for row in _active_ai_questions(db, lesson["id"]):
        try:
            choices = json.loads(row.choices)
        except Exception:  # noqa: BLE001
            continue
        quiz.append({"q": row.q, "choices": choices, "answer": row.answer,
                     "explain": row.explain})
    return quiz


def ai_refresh(db: Session, now: datetime | None = None) -> dict:
    """Once a month, ask Claude for fresh questions per lesson so the quiz bank
    never goes stale. Old AI questions are deactivated (kept for history);
    hand-written base questions are never touched. Per-lesson best-effort."""
    from . import ai
    from ..models import AcademyAiQuestion
    now = now or _utcnow()
    if not ai.enabled():
        return {"refreshed": False, "reason": "ai_off"}
    month = now.strftime("%Y-%m")
    already = (db.query(AcademyAiQuestion)
               .filter(AcademyAiQuestion.month == month).first())
    if already:
        return {"refreshed": False, "reason": "current", "month": month}

    added = 0
    for lesson_id, lesson in _LESSONS.items():
        try:
            raw = ai.complete(
                _AI_QGEN_SYSTEM.replace("{n}", str(AI_QUESTIONS_PER_LESSON)),
                f"Lesson title: {lesson['title']}\n\nLesson content:\n{lesson['body'][:5000]}",
                max_tokens=900)
            start, end = raw.find("["), raw.rfind("]")
            batch = json.loads(raw[start:end + 1])
            valid = []
            for item in batch[:AI_QUESTIONS_PER_LESSON]:
                ch = item.get("choices")
                ans = item.get("answer")
                if (isinstance(ch, list) and len(ch) == 4
                        and isinstance(ans, int) and 0 <= ans <= 3
                        and item.get("q") and item.get("explain")):
                    valid.append(item)
            if not valid:
                continue
            (db.query(AcademyAiQuestion)
             .filter(AcademyAiQuestion.lesson_id == lesson_id,
                     AcademyAiQuestion.active.is_(True))
             .update({"active": False}, synchronize_session=False))
            for item in valid:
                db.add(AcademyAiQuestion(
                    lesson_id=lesson_id, month=month, q=str(item["q"])[:400],
                    choices=json.dumps([str(c)[:250] for c in item["choices"]]),
                    answer=int(item["answer"]), explain=str(item["explain"])[:400],
                    active=True))
                added += 1
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    return {"refreshed": added > 0, "month": month, "questions_added": added}
