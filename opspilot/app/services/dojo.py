"""v1.74 Code Dojo — server-verified, write-real-code challenges.

This is the piece HackThisSite / HTB don't have: you write actual code in the
browser, it runs in a sandboxed Web Worker against the challenge's HIDDEN test
inputs, and the OUTPUTS are graded on the SERVER. The learner never sees the
expected answers, so passing means their code genuinely works — yet no untrusted
code ever runs on our server (it runs in the learner's own browser). Security
themes throughout: sanitize XSS, mask PCI data, redact PII, spot SQLi, validate
Luhn — you learn to code AND to defend at the same time.

Plugs into the Academy's XP / badge / streak / leaderboard system via
academy._award (kind="dojo"). Difficulty sets the XP.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AcademyCompletion, User

DOJO_XP = {"Easy": 120, "Medium": 200, "Hard": 320}

CODE_CHALLENGES = [{'id': 'reverse-string',
  'title': 'Reverse It',
  'difficulty': 'Easy',
  'category': 'Warmup',
  'prompt': 'Write solve(s) that returns the string s reversed.',
  'signature': 'function solve(s) {\n  // return s reversed\n}',
  'examples': [{'in': 'hello', 'out': 'olleh'}, {'in': 'Pulse', 'out': 'esluP'}],
  'tests': [{'in': 'cyberacademy', 'out': 'ymedacarebyc'},
            {'in': 'a', 'out': 'a'},
            {'in': 'racecar', 'out': 'racecar'},
            {'in': '1234567890', 'out': '0987654321'},
            {'in': 'H4ck th3 Pl4n3t', 'out': 't3n4lP 3ht kc4H'},
            {'in': '  spaced  ', 'out': '  decaps  '}],
  'teaches': 'Warm-up: get comfortable with the editor and the test runner.'},
 {'id': 'sanitize-script',
  'title': 'Strip the Script',
  'difficulty': 'Medium',
  'category': 'Security',
  'prompt': 'Write solve(s) that removes every <script>...</script> block (case-insensitive, including its contents) '
            'and returns the cleaned string. This is output-sanitization: the core defense against XSS.',
  'signature': 'function solve(s) {\n  // remove <script>...</script> blocks\n}',
  'examples': [{'in': 'hi<script>evil()</script>bye', 'out': 'hibye'}, {'in': '<b>ok</b>', 'out': '<b>ok</b>'}],
  'tests': [{'in': 'a<script>x</script>b', 'out': 'ab'},
            {'in': '<SCRIPT>alert(1)</SCRIPT>done', 'out': 'done'},
            {'in': 'no scripts here', 'out': 'no scripts here'},
            {'in': 'one<script>a</script>two<script>b</script>three', 'out': 'onetwothree'},
            {'in': '<script src=x></script>clean', 'out': 'clean'},
            {'in': 'text<ScRiPt>mixed</sCrIpT>case', 'out': 'textcase'}],
  'teaches': 'Stripping active markup is how you neutralize stored/reflected XSS. Real apps encode on output too.'},
 {'id': 'strong-password',
  'title': 'Password Policy',
  'difficulty': 'Medium',
  'category': 'Security',
  'prompt': 'Write solve(s) that returns true if s is a strong password: at least 12 characters AND contains a '
            'lowercase, an uppercase, a digit, and a symbol (non-alphanumeric). Otherwise return false.',
  'signature': 'function solve(s) {\n  // return true/false\n}',
  'examples': [{'in': 'Sh0rt!', 'out': False}, {'in': 'Tr0ub4dor&3xtra', 'out': True}],
  'tests': [{'in': 'password', 'out': False},
            {'in': 'PASSWORD1234', 'out': False},
            {'in': 'Abcdefgh1234', 'out': False},
            {'in': 'Abcdefgh123!', 'out': True},
            {'in': 'xK9#pLm2$vQ7', 'out': True},
            {'in': 'aaaaaaaaaaaa1A!', 'out': True},
            {'in': 'correct-horse-Battery-9', 'out': True}],
  'teaches': 'Length plus character variety is the classic policy. In production, prefer length + a breach-list '
             'check.'},
 {'id': 'mask-card',
  'title': 'Mask the Card',
  'difficulty': 'Medium',
  'category': 'Security',
  'prompt': "Write solve(s) that masks a credit-card string: replace every digit EXCEPT the last four with '*', "
            'keeping spaces/dashes as-is. Never log or show full card numbers (PCI).',
  'signature': 'function solve(s) {\n  // mask all but last 4 digits\n}',
  'examples': [{'in': '4111 1111 1111 1111', 'out': '**** **** **** 1111'},
               {'in': '1234-5678-9012-3456', 'out': '****-****-****-3456'}],
  'tests': [{'in': '4242424242424242', 'out': '************4242'},
            {'in': '5555 4444 3333 2222', 'out': '**** **** **** 2222'},
            {'in': '378282246310005', 'out': '***********0005'},
            {'in': '6011000990139424', 'out': '************9424'},
            {'in': '1111', 'out': '1111'},
            {'in': 'x9999y8888z7777', 'out': 'x****y****z7777'}],
  'teaches': 'Masking PII (PCI-DSS) means the last four only. The safest card data is data you never store.'},
 {'id': 'rot13-decode',
  'title': 'Rotate Back',
  'difficulty': 'Easy',
  'category': 'Crypto',
  'prompt': 'Write solve(s) that applies ROT13 to s (rotate each letter 13 places; leave non-letters alone). ROT13 '
            'is its own inverse, so this both encodes and decodes.',
  'signature': 'function solve(s) {\n  // ROT13 every letter\n}',
  'examples': [{'in': 'FLAG', 'out': 'SYNT'}, {'in': 'Uryyb, Jbeyq!', 'out': 'Hello, World!'}],
  'tests': [{'in': 'Purpx gur ybtf', 'out': 'Check the logs'},
            {'in': 'abcXYZ', 'out': 'nopKLM'},
            {'in': 'H4ck3r', 'out': 'U4px3e'},
            {'in': 'The quick brown fox', 'out': 'Gur dhvpx oebja sbk'},
            {'in': 'ZERO-day!', 'out': 'MREB-qnl!'},
            {'in': 'aA zZ', 'out': 'nN mM'}],
  'teaches': 'ROT13 is a fixed-shift Caesar cipher — a puzzle, not encryption. Great for learning string '
             'manipulation.'},
 {'id': 'redact-emails',
  'title': 'Redact the PII',
  'difficulty': 'Medium',
  'category': 'Security',
  'prompt': 'Write solve(s) that replaces every email address in s with the literal text [REDACTED]. '
            'Data-loss-prevention basics.',
  'signature': 'function solve(s) {\n  // replace emails with [REDACTED]\n}',
  'examples': [{'in': 'mail me at a@b.com ok', 'out': 'mail me at [REDACTED] ok'},
               {'in': 'no emails', 'out': 'no emails'}],
  'tests': [{'in': 'contact jordan@bvtech.org today', 'out': 'contact [REDACTED] today'},
            {'in': 'two: a@x.io and b@y.net', 'out': 'two: [REDACTED] and [REDACTED]'},
            {'in': 'plain text', 'out': 'plain text'},
            {'in': 'nested.name+tag@sub.domain.co works', 'out': '[REDACTED] works'},
            {'in': '@notanemail here', 'out': '@notanemail here'},
            {'in': 'END jane.doe@example.com', 'out': 'END [REDACTED]'}],
  'teaches': 'Redacting PII before logs/tickets/AI tools is a core DLP control. Regex is the everyday tool for it.'},
 {'id': 'detect-sqli',
  'title': 'Spot the Injection',
  'difficulty': 'Hard',
  'category': 'Security',
  'prompt': 'Write solve(list) that takes an array of input strings and returns an array of booleans: true where the '
            'input looks like a SQL-injection attempt (contains a quote-then-OR, a -- comment, UNION SELECT, ; DROP, '
            "or '='). Case-insensitive.",
  'signature': 'function solve(list) {\n  // return array of booleans\n}',
  'examples': [{'in': ['admin', "' OR '1'='1"], 'out': [False, True]},
               {'in': ["O'Brien", 'x--'], 'out': [False, True]}],
  'tests': [{'in': ['hello', "' or 1=1--"], 'out': [False, True]},
            {'in': ['UNION SELECT pw FROM users', 'normal input'], 'out': [True, False]},
            {'in': ["'; DROP TABLE t;--", 'just text'], 'out': [True, False]},
            {'in': ["'='", 'safe'], 'out': [True, False]},
            {'in': ['orlando', "admin'--"], 'out': [False, True]}],
  'teaches': "This is WAF logic. Note the false-positive trap: 'orlando' contains 'or' but isn't SQL syntax."},
 {'id': 'luhn-check',
  'title': 'Luhn Validator',
  'difficulty': 'Hard',
  'category': 'Crypto',
  'prompt': 'Write solve(s) that returns true if the digits in s pass the Luhn checksum (the algorithm that '
            'validates most card numbers), else false. Ignore non-digits.',
  'signature': 'function solve(s) {\n  // return true if Luhn-valid\n}',
  'examples': [{'in': '4242 4242 4242 4242', 'out': True}, {'in': '1234 5678 9012 3456', 'out': False}],
  'tests': [{'in': '79927398713', 'out': True},
            {'in': '79927398710', 'out': False},
            {'in': '4111111111111111', 'out': True},
            {'in': '5500005555555559', 'out': True},
            {'in': '000', 'out': True},
            {'in': '1111 2222 3333 4444', 'out': True}],
  'teaches': 'Luhn is a simple, ubiquitous checksum. Implementing it teaches modular arithmetic and digit handling.'}]
_CHALLENGES = {c["id"]: c for c in CODE_CHALLENGES}
TOTAL_CHALLENGES = len(_CHALLENGES)


def _solved_ids(db: Session, user: User) -> set:
    return {c.item_id for c in db.query(AcademyCompletion)
            .filter(AcademyCompletion.user_id == user.id,
                    AcademyCompletion.kind == "dojo")}


def dojo_view(db: Session, user: User) -> dict:
    """Catalog of coding challenges with per-user solved state. No answers."""
    solved = _solved_ids(db, user)
    items = [{"id": c["id"], "title": c["title"], "difficulty": c["difficulty"],
              "category": c["category"], "points": DOJO_XP[c["difficulty"]],
              "solved": c["id"] in solved} for c in CODE_CHALLENGES]
    return {"challenges": items, "total": TOTAL_CHALLENGES,
            "solved": len([i for i in items if i["solved"]])}


def challenge_view(db: Session, user: User, cid: str) -> dict | None:
    """Everything needed to attempt a challenge — prompt, function signature,
    PUBLIC examples, and the hidden test INPUTS (so the browser can run the
    learner's code) but NEVER the expected outputs. The teaching note only comes
    back once solved."""
    c = _CHALLENGES.get(cid)
    if not c:
        return None
    solved = bool(cid in _solved_ids(db, user))
    return {
        "id": c["id"], "title": c["title"], "difficulty": c["difficulty"],
        "category": c["category"], "points": DOJO_XP[c["difficulty"]],
        "prompt": c["prompt"], "signature": c["signature"],
        "examples": c["examples"],                       # public in/out
        "test_inputs": [t["in"] for t in c["tests"]],    # hidden inputs, no outputs
        "solved": solved,
        "teaches": c["teaches"] if solved else None,
    }


def grade(db: Session, user: User, cid: str, outputs: list):
    """Grade submitted outputs against the hidden expected outputs (deep JSON
    equality). Awards difficulty-scaled XP the first time. The expected answers
    live only here on the server."""
    c = _CHALLENGES.get(cid)
    if c is None:
        return None
    expected = [t["out"] for t in c["tests"]]
    ok = isinstance(outputs, list) and len(outputs) == len(expected) and all(
        outputs[i] == expected[i] for i in range(len(expected)))
    if not ok:
        # how many passed, so the UI can nudge without leaking answers
        passed = sum(1 for i in range(min(len(outputs or []), len(expected)))
                     if (outputs or [])[i] == expected[i])
        return {"solved": False, "passed": passed, "total": len(expected),
                "message": f"{passed}/{len(expected)} hidden tests passed — keep going."}
    from . import academy   # lazy: avoids an import cycle
    prof = academy.get_profile(db, user)
    xp, new_badges = academy._award(db, user, prof, cid, "dojo", None, None,
                                    xp_override=DOJO_XP[c["difficulty"]])
    return {"solved": True, "passed": len(expected), "total": len(expected),
            "xp_gained": xp, "teaches": c["teaches"],
            "message": "✅ All hidden tests passed!" if xp else "Already solved — nice.",
            "profile": academy.profile_view(db, user),
            "new_badges": [{**academy.BADGES[b], "id": b} for b in new_badges]}
