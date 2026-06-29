"""Unit tests for app/services/networking.py — pure IPAM / subnet math."""
from __future__ import annotations

import pytest

from app.services import networking


def test_subnet_info_ipv4_24():
    info = networking.subnet_info("10.0.0.0/24")
    assert info["version"] == 4
    assert info["network_address"] == "10.0.0.0"
    assert info["broadcast_address"] == "10.0.0.255"
    assert info["netmask"] == "255.255.255.0"
    assert info["prefixlen"] == 24
    assert info["num_addresses"] == 256
    assert info["usable_hosts"] == 254
    assert info["first_host"] == "10.0.0.1"
    assert info["last_host"] == "10.0.0.254"


def test_subnet_info_normalizes_non_strict_cidr():
    # Host bits set + strict=False -> network is normalized down.
    assert networking.subnet_info("10.0.0.37/24")["cidr"] == "10.0.0.0/24"


def test_subnet_info_slash31_point_to_point():
    # /31 (RFC 3021): Python's hosts() returns BOTH addresses as usable.
    info = networking.subnet_info("192.168.1.0/31")
    assert info["num_addresses"] == 2
    assert info["usable_hosts"] == 2
    assert info["first_host"] == "192.168.1.0"
    assert info["last_host"] == "192.168.1.1"


def test_subnet_info_slash32_single_address():
    # /32: hosts() returns the single address itself.
    info = networking.subnet_info("192.168.1.5/32")
    assert info["num_addresses"] == 1
    assert info["usable_hosts"] == 1
    assert info["first_host"] == "192.168.1.5"


def test_subnet_info_ipv6_has_no_broadcast():
    # NOTE: a small prefix on purpose. subnet_info() materializes list(net.hosts()),
    # so a large IPv6 prefix (e.g. /64 -> 2**64 hosts) would hang / exhaust memory.
    # That is a real limitation of subnet_info() worth hardening separately.
    info = networking.subnet_info("2001:db8::/126")
    assert info["version"] == 6
    assert info["broadcast_address"] is None
    assert info["usable_hosts"] == 3  # /126 -> IPv6 hosts() excludes the anycast addr


def test_subnet_info_invalid_raises_valueerror():
    with pytest.raises(ValueError):
        networking.subnet_info("not-a-cidr")


def test_usable_host_count_normal_and_edge():
    assert networking.usable_host_count("10.0.0.0/24") == 254
    # /32: hosts() is empty so it falls back to num_addresses (1).
    assert networking.usable_host_count("10.0.0.1/32") == 1
    # /31: empty hosts() falls back to num_addresses (2).
    assert networking.usable_host_count("10.0.0.0/31") == 2


def test_ip_in_network():
    assert networking.ip_in_network("10.0.0.5", "10.0.0.0/24") is True
    assert networking.ip_in_network("10.0.1.5", "10.0.0.0/24") is False


def test_ip_in_network_bad_input_is_false_not_error():
    assert networking.ip_in_network("garbage", "10.0.0.0/24") is False
    assert networking.ip_in_network("10.0.0.5", "garbage") is False


def test_is_valid_ip():
    assert networking.is_valid_ip("192.168.1.1") is True
    assert networking.is_valid_ip("::1") is True
    assert networking.is_valid_ip("999.1.1.1") is False
    assert networking.is_valid_ip("") is False
