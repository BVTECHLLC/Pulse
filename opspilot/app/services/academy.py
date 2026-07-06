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
# Lookups
# --------------------------------------------------------------------------- #
_LESSONS = {l["id"]: l for m in MODULES for l in m["lessons"]}
_GAMES = {g["id"]: g for g in GAMES}
TOTAL_LESSONS = len(_LESSONS)


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
           kind: str, score: int | None, max_score: int | None) -> tuple[int, list[str]]:
    """Record a completion; award XP only the first time. Returns (xp_gained,
    newly earned badge ids)."""
    now = _utcnow()
    first = not (db.query(AcademyCompletion)
                 .filter(AcademyCompletion.user_id == user.id,
                         AcademyCompletion.item_id == item_id).first())
    xp = 0
    if first:
        if kind == "lesson":
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
    earn("first_steps", kind == "lesson")
    earn("quiz_perfect", kind == "lesson" and score is not None and score == max_score)
    earn("phish_master", item_id == "phish-or-legit" and score is not None and score == max_score)
    earn("lab_rat", item_id == "password-lab")
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
    return {
        "xp": prof.xp or 0,
        "level": _level(prof.xp or 0),
        "streak_days": live_streak,
        "active_today": prof.last_active_on == today,
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
    return {"modules": mods, "games": games, "total_lessons": TOTAL_LESSONS}


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
                f"Save it here: https://portal.bvtech.org/academy\n\n"
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
