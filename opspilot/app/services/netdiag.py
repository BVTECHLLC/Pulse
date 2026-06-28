"""Server-side network diagnostics ("looking glass") — run from the portal/Linode
box toward PUBLIC targets to triage a client's internet-facing issues (site up?
DNS resolving? mail port open? latency?).

Hard SSRF guard: every target is resolved and any private / loopback / link-local
(incl. cloud metadata 169.254.169.254) / reserved / multicast address is REFUSED.
ICMP isn't used (containers rarely have it); reachability is a TCP connect, which
needs no special privileges. All probes are read-only with tight timeouts.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from urllib.parse import urlparse


class DiagError(Exception):
    pass


def _guard_ip(ip: str) -> None:
    a = ipaddress.ip_address(ip)
    if (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
            or a.is_reserved or a.is_unspecified):
        raise DiagError(f"Target {ip} is in a blocked (private/internal) range")


def resolve(host: str) -> list[str]:
    """Resolve a hostname to IPs, guarding every result against internal ranges."""
    host = (host or "").strip()
    if not host:
        raise DiagError("No host given")
    # If they passed a literal IP, guard it directly.
    try:
        ipaddress.ip_address(host)
        _guard_ip(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise DiagError(f"DNS resolution failed: {e}")
    ips = sorted({i[4][0] for i in infos})
    if not ips:
        raise DiagError("No addresses resolved")
    for ip in ips:
        _guard_ip(ip)
    return ips


def dns_lookup(host: str) -> dict:
    return {"host": host, "addresses": resolve(host)}


def tcp_check(host: str, port: int, timeout: float = 4.0) -> dict:
    if not (1 <= port <= 65535):
        raise DiagError("Port must be 1..65535")
    ips = resolve(host)
    ip = ips[0]
    start = time.monotonic()
    s = socket.socket(socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        ms = round((time.monotonic() - start) * 1000, 1)
        return {"host": host, "ip": ip, "port": port, "open": True, "latency_ms": ms}
    except (socket.timeout, OSError):
        return {"host": host, "ip": ip, "port": port, "open": False, "latency_ms": None}
    finally:
        s.close()


def reachability(host: str, timeout: float = 4.0) -> dict:
    """ICMP-free 'ping': try TCP 443 then 80 and report the best latency."""
    resolve(host)  # guard first
    best = None
    results = []
    for port in (443, 80):
        r = tcp_check(host, port, timeout=timeout)
        results.append({"port": port, "open": r["open"], "latency_ms": r["latency_ms"]})
        if r["open"] and (best is None or (r["latency_ms"] or 1e9) < best):
            best = r["latency_ms"]
    return {"host": host, "reachable": best is not None, "latency_ms": best, "probes": results}


def http_check(url: str, timeout: float = 6.0) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    resolve(host)  # guard
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    start = time.monotonic()
    try:
        ip = resolve(host)[0]
        sock = socket.create_connection((ip, port), timeout=timeout)
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        req = f"HEAD {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: OpsPilot-LookingGlass\r\nConnection: close\r\n\r\n"
        sock.sendall(req.encode())
        data = sock.recv(256).decode("latin1", "replace")
        sock.close()
        ms = round((time.monotonic() - start) * 1000, 1)
        status_line = data.splitlines()[0] if data else ""
        code = None
        parts = status_line.split(" ")
        if len(parts) >= 2 and parts[1].isdigit():
            code = int(parts[1])
        return {"url": url, "host": host, "status": code, "status_line": status_line.strip(),
                "latency_ms": ms, "ok": code is not None and code < 500}
    except DiagError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"url": url, "host": host, "status": None, "status_line": str(e),
                "latency_ms": None, "ok": False}
