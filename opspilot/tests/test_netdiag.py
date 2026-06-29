"""Unit tests for app/services/netdiag.py — the SSRF guard on the looking-glass.

The guard is the security-critical part: it must REFUSE any target that resolves
to a private / loopback / link-local / reserved / cloud-metadata address. DNS is
monkeypatched so these tests never touch the network.
"""
from __future__ import annotations

import pytest

from app.services import netdiag
from app.services.netdiag import DiagError


# --------------------------------------------------------------------------- #
# _guard_ip — the core allow/deny decision
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ip", [
    "127.0.0.1",          # loopback
    "10.1.2.3",           # RFC1918 private
    "192.168.0.1",        # RFC1918 private
    "172.16.5.9",         # RFC1918 private
    "169.254.169.254",    # link-local / cloud metadata endpoint
    "0.0.0.0",            # unspecified
    "224.0.0.1",          # multicast
    "::1",                # IPv6 loopback
    "fe80::1",            # IPv6 link-local
])
def test_guard_ip_blocks_internal_ranges(ip):
    with pytest.raises(DiagError):
        netdiag._guard_ip(ip)


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"])
def test_guard_ip_allows_public(ip):
    netdiag._guard_ip(ip)  # must not raise


# --------------------------------------------------------------------------- #
# resolve — literal IPs and DNS, both guarded
# --------------------------------------------------------------------------- #
def test_resolve_public_literal_ip_passes():
    assert netdiag.resolve("8.8.8.8") == ["8.8.8.8"]


def test_resolve_private_literal_ip_blocked():
    with pytest.raises(DiagError):
        netdiag.resolve("127.0.0.1")


def test_resolve_empty_host_raises():
    with pytest.raises(DiagError):
        netdiag.resolve("   ")


def test_resolve_blocks_dns_rebinding_to_private(monkeypatch):
    """A hostname that resolves to a private IP must be refused (the classic
    SSRF / DNS-rebinding bypass)."""
    def fake_getaddrinfo(host, port, *a, **k):
        return [(2, 1, 6, "", ("10.0.0.5", 0))]
    monkeypatch.setattr(netdiag.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(DiagError):
        netdiag.resolve("evil.example.com")


def test_resolve_allows_public_dns_result(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **k):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(netdiag.socket, "getaddrinfo", fake_getaddrinfo)
    assert netdiag.resolve("example.com") == ["93.184.216.34"]


def test_resolve_one_private_in_set_blocks_all(monkeypatch):
    """If ANY resolved address is internal, the whole target is refused."""
    def fake_getaddrinfo(host, port, *a, **k):
        return [(2, 1, 6, "", ("93.184.216.34", 0)),
                (2, 1, 6, "", ("127.0.0.1", 0))]
    monkeypatch.setattr(netdiag.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(DiagError):
        netdiag.resolve("mixed.example.com")


def test_resolve_dns_failure_becomes_diagerror(monkeypatch):
    import socket as _socket

    def boom(host, port, *a, **k):
        raise _socket.gaierror("nope")
    monkeypatch.setattr(netdiag.socket, "getaddrinfo", boom)
    with pytest.raises(DiagError):
        netdiag.resolve("does-not-exist.invalid")


# --------------------------------------------------------------------------- #
# tcp_check — port validation happens before any socket work
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("port", [0, -1, 65536, 99999])
def test_tcp_check_rejects_out_of_range_ports(port):
    with pytest.raises(DiagError):
        netdiag.tcp_check("8.8.8.8", port)


def test_tcp_check_guards_target_before_connecting():
    # Private target must be refused by resolve() before any connection attempt.
    with pytest.raises(DiagError):
        netdiag.tcp_check("127.0.0.1", 22)
