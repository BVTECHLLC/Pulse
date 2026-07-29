"""v1.75 The Grid — an interactive, SAFE Linux terminal hacking simulator.

This is the showpiece: a real "boot2root" engagement you type your way through in
the browser. You land as a low-privilege web user on a vulnerable box, ENUMERATE
the filesystem, find leaked credentials, pivot to a real user, grab the user
flag, discover a sudo/GTFOBins misconfiguration, escalate to root, and capture
the root flag. It teaches genuine Linux enumeration + privilege escalation — the
core of every pentest — the way HackTheBox does, but with zero risk.

SAFE BY CONSTRUCTION: there is NO real shell, filesystem, or code execution. The
"box" is a hardcoded virtual filesystem and a deterministic command interpreter.
Every command's output is computed, permissions are modeled (a 700 home dir is
unreadable until you become its owner), and privilege is authoritative server
state. The worst a player can do is read canned strings.

`_exec(state, line)` is a PURE function (state dict + input line -> new state +
output lines) so it's trivially testable. `run(user_id, line)` is the thin
stateful wrapper the API uses (in-memory per-user session; losing it just resets
the box, which is harmless — the flags are checked by the normal lab engine).
"""
from __future__ import annotations

import threading

BOX = "sentinel"
USER_FLAG = "FLAG{enum3rati0n_comes_first}"
ROOT_FLAG = "FLAG{b00t2r00t_gtfo_via_sudo_find}"
JORDAN_PW = "Summer2024!"

# --------------------------------------------------------------------------- #
# Virtual filesystem. Each node: type, owner, mode (3 octal digits), content.
# Permissions are modeled so enumeration and privesc actually matter.
# --------------------------------------------------------------------------- #
def _d(owner="root", mode="755"):
    return {"type": "dir", "owner": owner, "mode": mode}


def _f(owner, mode, content):
    return {"type": "file", "owner": owner, "mode": mode, "content": content}


FS = {
    "/": _d(),
    "/etc": _d(),
    "/etc/passwd": _f("root", "644",
        "root:x:0:0:root:/root:/bin/bash\n"
        "jordan:x:1000:1000:Jordan,,,:/home/jordan:/bin/bash\n"
        "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
        "# Three accounts. You're www-data. Target: root. Waypoint: jordan."),
    "/etc/os-release": _f("root", "644", 'PRETTY_NAME="Sentinel Linux 3.1 (grid)"'),
    "/var": _d(),
    "/var/www": _d("www-data", "755"),
    "/var/www/html": _d("www-data", "755"),
    "/var/www/html/index.php": _f("www-data", "644",
        "<?php require 'config.php'; echo 'Sentinel Corp — Employee Portal'; ?>"),
    "/var/www/html/config.php": _f("www-data", "644",
        "<?php\n"
        "// DB connection for the portal\n"
        "$db_host = 'localhost';\n"
        "$db_user = 'jordan';\n"
        f"$db_pass = '{JORDAN_PW}';  // NOTE: jordan reuses this everywhere. rotate!!\n"
        "?>"),
    "/var/www/html/notes.txt": _f("www-data", "644",
        "TODO:\n- migrate off shared password\n"
        "- jordan keeps a NOPASSWD sudo entry for testing (remove before prod!)\n"),
    "/var/www/html/.htaccess": _f("www-data", "644", "Options -Indexes"),
    "/home": _d(),
    # 700: www-data cannot read this until it becomes jordan. This is the pivot gate.
    "/home/jordan": _d("jordan", "700"),
    "/home/jordan/user.txt": _f("jordan", "600", USER_FLAG),
    "/home/jordan/.bash_history": _f("jordan", "600",
        "id\nsudo -l\n# oh nice, i can run find as root without a password\n"
        "sudo find . -exec /bin/sh \\; -quit\nwhoami\ncat /root/root.txt"),
    "/home/jordan/todo.md": _f("jordan", "644",
        "# reminders\n- rotate that reused DB password\n"
        "- ask ops to remove my sudo find entry (security flagged it)\n"),
    # 700: root-only until you escalate.
    "/root": _d("root", "700"),
    "/root/root.txt": _f("root", "600", ROOT_FLAG),
    "/usr": _d(),
    "/usr/bin": _d(),
    "/usr/bin/find": _f("root", "755", "(ELF binary)"),
}

MOTD = [
    "  ____             _   _            _ ",
    " / ___|  ___ _ __ | |_(_)_ __   ___| |",
    " \\___ \\ / _ \\ '_ \\| __| | '_ \\ / _ \\ |   THE GRID // target: sentinel",
    "  ___) |  __/ | | | |_| | | | |  __/ |   you are www-data — get to root.",
    " |____/ \\___|_| |_|\\__|_|_| |_|\\___|_|",
    "",
    "Type `help` for commands, `hint` if you're stuck, `reset` to start over.",
    "Goal: capture the user flag (/home/jordan) and the root flag (/root).",
    "",
]

HELP = [
    "Available commands (a curated, safe subset):",
    "  ls [-la] [path]     list files (permissions matter!)",
    "  cd <path>           change directory",
    "  cat <file>          read a file",
    "  pwd / whoami / id   who and where you are",
    "  find <path> <opts>  e.g. find / -perm -4000   (SUID hunt)",
    "  su <user>           switch user (prompts for a password)",
    "  sudo -l             list what you may run as root",
    "  sudo <command>      run a command as root (if permitted)",
    "  grep <text> <file>  search inside a file",
    "  uname -a / hostname / cat /etc/passwd   enumerate the box",
    "  hint                a nudge   ·   reset   reboot the box",
]


def fresh_state() -> dict:
    return {"user": "www-data", "cwd": "/var/www/html", "pending": None, "root_shell": False}


# ---- permission + path helpers -------------------------------------------- #
def _can_read(node: dict, user: str) -> bool:
    if user == "root":
        return True
    mode = node.get("mode", "644")
    if user == node.get("owner"):
        return bool(int(mode[0]) & 4)
    return bool(int(mode[2]) & 4)


def _norm(cwd: str, path: str) -> str:
    if not path:
        return cwd
    if not path.startswith("/"):
        path = (cwd.rstrip("/") + "/" + path)
    parts = []
    for p in path.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
        else:
            parts.append(p)
    return "/" + "/".join(parts)


def _children(path: str) -> list[str]:
    path = path.rstrip("/") or "/"
    base = "" if path == "/" else path
    out = []
    for k in FS:
        if k == path:
            continue
        parent = k.rsplit("/", 1)[0] or "/"
        if parent == path:
            out.append(k.rsplit("/", 1)[1])
    return sorted(out)


def _prompt(state: dict) -> str:
    u = state["user"]
    sym = "#" if u == "root" else "$"
    cwd = state["cwd"].replace("/home/jordan", "~") if u == "jordan" else state["cwd"]
    return f"{u}@{BOX}:{cwd}{sym}"


# ---- the interpreter ------------------------------------------------------- #
def _exec(state: dict, line: str) -> tuple[dict, list[str]]:
    state = dict(state)
    line = (line or "").strip()

    # interactive password prompt (from `su`)
    if state.get("pending"):
        pend = state["pending"]
        state["pending"] = None
        if pend["type"] == "password":
            if pend["user"] == "jordan" and line == JORDAN_PW:
                state["user"] = "jordan"
                return state, [f"Welcome back, jordan. (uid=1000)"]
            return state, ["su: Authentication failure"]
    if not line:
        return state, [""]

    parts = line.split()
    cmd, args = parts[0], parts[1:]
    u, cwd = state["user"], state["cwd"]

    if cmd == "help":
        return state, HELP
    if cmd == "hint":
        return state, [_hint(state)]
    if cmd == "reset":
        return fresh_state(), ["** box rebooted — you are www-data again **"]
    if cmd == "clear":
        return state, ["\x0c"]   # client clears
    if cmd in ("whoami",):
        return state, [u]
    if cmd == "id":
        ids = {"www-data": "uid=33(www-data) gid=33(www-data) groups=33(www-data)",
               "jordan": "uid=1000(jordan) gid=1000(jordan) groups=1000(jordan)",
               "root": "uid=0(root) gid=0(root) groups=0(root)"}
        return state, [ids[u]]
    if cmd == "pwd":
        return state, [cwd]
    if cmd == "hostname":
        return state, [BOX]
    if cmd == "uname":
        return state, ["Linux sentinel 3.1.0-grid #1 SMP x86_64 GNU/Linux"]
    if cmd == "env":
        return state, [f"USER={u}", "SHELL=/bin/bash", f"PWD={cwd}", "PATH=/usr/bin:/bin"]
    if cmd == "history":
        return state, ["(shell history is per-user; try reading a user's .bash_history)"]
    if cmd == "echo":
        return state, [" ".join(args)]

    if cmd == "ls":
        return state, _ls(state, args)
    if cmd == "cd":
        return _cd(state, args)
    if cmd == "cat":
        return state, _cat(state, args)
    if cmd == "grep":
        return state, _grep(state, args)
    if cmd == "find":
        return state, _find(state, args, sudo=False)
    if cmd == "su":
        return _su(state, args)
    if cmd == "sudo":
        return _sudo(state, args)

    return state, [f"{cmd}: command not found  (type `help`)"]


def _ls(state, args):
    long = any(a.startswith("-") and ("l" in a) for a in args)
    show_all = any(a.startswith("-") and ("a" in a) for a in args)
    targets = [a for a in args if not a.startswith("-")] or ["."]
    path = _norm(state["cwd"], targets[0])
    node = FS.get(path)
    if node is None:
        return [f"ls: cannot access '{targets[0]}': No such file or directory"]
    if node["type"] == "file":
        return [path.rsplit("/", 1)[1]]
    if not _can_read(node, state["user"]):
        return [f"ls: cannot open directory '{targets[0]}': Permission denied"]
    names = _children(path)
    if not show_all:
        names = [n for n in names if not n.startswith(".")]
    if show_all:
        names = [".", ".."] + names
    if not long:
        return ["  ".join(names)] if names else [""]
    rows = []
    for n in names:
        if n in (".", ".."):
            rows.append(f"drwxr-xr-x  {state['user']:<8} {n}")
            continue
        child = FS.get(path.rstrip("/") + "/" + n) or FS.get("/" + n)
        cp = (path.rstrip("/") + "/" + n)
        child = FS.get(cp, {})
        t = "d" if child.get("type") == "dir" else "-"
        m = child.get("mode", "644")
        perm = "".join(("r" if int(x) & 4 else "-") + ("w" if int(x) & 2 else "-")
                       + ("x" if int(x) & 1 else "-") for x in m)
        rows.append(f"{t}{perm}  {child.get('owner','root'):<8} {n}")
    return rows


def _cd(state, args):
    if not args:
        state = dict(state); state["cwd"] = "/home/" + state["user"] if state["user"] != "www-data" else "/var/www/html"
        return state, [""]
    path = _norm(state["cwd"], args[0])
    node = FS.get(path)
    if node is None or node["type"] != "dir":
        return state, [f"cd: {args[0]}: No such file or directory"]
    if not _can_read(node, state["user"]):
        return state, [f"cd: {args[0]}: Permission denied"]
    state = dict(state); state["cwd"] = path
    return state, [""]


def _cat(state, args):
    if not args:
        return ["cat: missing operand"]
    out = []
    for a in args:
        path = _norm(state["cwd"], a)
        node = FS.get(path)
        if node is None:
            out.append(f"cat: {a}: No such file or directory")
        elif node["type"] == "dir":
            out.append(f"cat: {a}: Is a directory")
        elif not _can_read(node, state["user"]):
            out.append(f"cat: {a}: Permission denied")
        else:
            out.extend(node["content"].split("\n"))
    return out


def _grep(state, args):
    if len(args) < 2:
        return ["usage: grep <text> <file>"]
    pat, a = args[0], args[1]
    path = _norm(state["cwd"], a)
    node = FS.get(path)
    if node is None or node["type"] != "file":
        return [f"grep: {a}: No such file"]
    if not _can_read(node, state["user"]):
        return [f"grep: {a}: Permission denied"]
    return [ln for ln in node["content"].split("\n") if pat.lower() in ln.lower()] or [""]


def _find(state, args, sudo):
    joined = " ".join(args)
    # SUID hunt — a legitimate enumeration technique (here it's a teaching red herring)
    if "-perm" in args and "-4000" in joined:
        return ["/usr/bin/find", "/usr/bin/passwd", "(no unusual SUID binaries — try `sudo -l`)"]
    # GTFOBins privesc: `sudo find ... -exec /bin/sh \;`
    if sudo and "-exec" in args and any(s in joined for s in ("/bin/sh", "/bin/bash", " sh ", "sh;", "sh \\;")):
        state = dict(state); state["user"] = "root"; state["root_shell"] = True
        return state, ["# id", "uid=0(root) gid=0(root) groups=0(root)",
                       "** root shell spawned via GTFOBins (find -exec) — you are ROOT **",
                       "now: cat /root/root.txt"]
    if sudo:
        return ["(find ran as root but spawned no shell — use -exec /bin/sh \\; to drop a shell)"]
    return [f"find: paths must precede expression (try `find / -perm -4000`)"]


def _su(state, args):
    if not args:
        return state, ["usage: su <user>"]
    target = args[0]
    if target == state["user"]:
        return state, [""]
    if target not in ("jordan", "root", "www-data"):
        return state, [f"su: user {target} does not exist"]
    if target == "www-data":
        state = dict(state); state["user"] = "www-data"; return state, [""]
    if target == "root":
        # root's password isn't recoverable — funnel players to the sudo path.
        state = dict(state); state["pending"] = {"type": "password", "user": "root"}
        return state, ["Password:"]
    state = dict(state); state["pending"] = {"type": "password", "user": "jordan"}
    return state, ["Password:"]


def _sudo(state, args):
    u = state["user"]
    if not args:
        return state, ["usage: sudo <command>"]
    if args == ["-l"]:
        if u == "www-data":
            return state, ["Sorry, user www-data may not run sudo on sentinel."]
        if u == "jordan":
            return state, ["Matching Defaults entries for jordan on sentinel:",
                           "    env_reset, secure_path=/usr/bin:/bin", "",
                           "User jordan may run the following commands on sentinel:",
                           "    (root) NOPASSWD: /usr/bin/find"]
        return state, ["(root) ALL"]
    # running something as root
    if u == "www-data":
        return state, [f"Sorry, user www-data is not allowed to run '{' '.join(args)}' as root."]
    if u == "jordan":
        if args[0] == "find" or args[0].endswith("/find"):
            return _find(state, args[1:], sudo=True)
        return state, [f"Sorry, user jordan is not allowed to run '{args[0]}' as root. "
                       "(check `sudo -l` — only /usr/bin/find is permitted)"]
    # already root
    return state, ["(already root)"]


def _hint(state):
    u = state["user"]
    if u == "www-data":
        return ("You're www-data in the web root. Read every file here — `ls -la` then "
                "`cat config.php`. Web configs love to leak database passwords, and people "
                "reuse them. Then `su` to that user.")
    if u == "jordan":
        return ("You're jordan now — grab the user flag in your home dir (`cat user.txt`). "
                "Then hunt for privesc: `sudo -l` shows what you can run as root. A find with "
                "NOPASSWD is a classic GTFOBins escape.")
    return "You're root. `cat /root/root.txt` and submit that flag to finish the box."


# --------------------------------------------------------------------------- #
# Stateful wrapper for the API (in-memory per-user session).
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_sessions: dict[int, dict] = {}


def start(user_id: int) -> dict:
    with _lock:
        _sessions[user_id] = fresh_state()
        if len(_sessions) > 5000:               # cap: drop oldest-ish
            for k in list(_sessions)[:1000]:
                _sessions.pop(k, None)
    st = _sessions[user_id]
    return {"lines": MOTD, "prompt": _prompt(st)}


def run(user_id: int, line: str) -> dict:
    with _lock:
        st = _sessions.get(user_id) or fresh_state()
        new_st, lines = _exec(st, line)
        _sessions[user_id] = new_st
    return {"lines": lines, "prompt": _prompt(new_st),
            "user": new_st["user"], "awaiting_password": bool(new_st.get("pending"))}


def reset_all():
    with _lock:
        _sessions.clear()
