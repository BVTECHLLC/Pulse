"""Networking / IPAM helpers — pure computation over the stdlib `ipaddress`
module (no external calls). Powers the subnet calculator and IP-allocation
guards (in-range + conflict checks).
"""
from __future__ import annotations

import ipaddress


def subnet_info(cidr: str) -> dict:
    """Return network math for a CIDR (e.g. '10.0.0.0/24'). Raises ValueError
    on bad input (caller turns that into a 400)."""
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = list(net.hosts())
    return {
        "cidr": str(net),
        "version": net.version,
        "network_address": str(net.network_address),
        "broadcast_address": str(net.broadcast_address) if net.version == 4 else None,
        "netmask": str(net.netmask),
        "prefixlen": net.prefixlen,
        "num_addresses": net.num_addresses,
        "usable_hosts": len(hosts),
        "first_host": str(hosts[0]) if hosts else None,
        "last_host": str(hosts[-1]) if hosts else None,
    }


def usable_host_count(cidr: str) -> int:
    net = ipaddress.ip_network(cidr, strict=False)
    return len(list(net.hosts())) or net.num_addresses


def ip_in_network(addr: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(addr) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def is_valid_ip(addr: str) -> bool:
    try:
        ipaddress.ip_address(addr)
        return True
    except ValueError:
        return False
