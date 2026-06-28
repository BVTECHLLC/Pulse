"""v0.11 networking / IPAM: sites, networks (subnets), and tracked IP addresses,
plus a subnet calculator. Staff manage; client users have read-only visibility
into their own org's network documentation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Client, Device, IPAddress, Network, Role, Site, User
from ...services import audit, networking

router = APIRouter(prefix="/api/net", tags=["networking"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _scope(q, model, user: User):
    return q if is_staff(user) else q.filter(model.client_id == user.client_id)


# --------------------------------------------------------------------------- #
# Subnet calculator (pure utility)
# --------------------------------------------------------------------------- #
class CalcIn(BaseModel):
    cidr: str


@router.post("/subnet-calc")
def subnet_calc(body: CalcIn, user: User = Depends(current_user)):
    try:
        return networking.subnet_info(body.cidr)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid CIDR: {e}")


# --------------------------------------------------------------------------- #
# Sites
# --------------------------------------------------------------------------- #
class SiteIn(BaseModel):
    client_id: int
    name: str
    address: str | None = None
    notes: str | None = None


@router.get("/sites")
def list_sites(client_id: int | None = None, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    q = _scope(db.query(Site), Site, user)
    if client_id and is_staff(user):
        q = q.filter(Site.client_id == client_id)
    return [{"id": s.id, "client_id": s.client_id, "name": s.name,
             "address": s.address, "notes": s.notes} for s in q.order_by(Site.name).all()]


@router.post("/sites", status_code=201)
def create_site(body: SiteIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    s = Site(client_id=body.client_id, name=body.name[:200], address=body.address, notes=body.notes)
    db.add(s)
    db.commit()
    audit.record(db, action="site.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="site", target_id=str(s.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"name={s.name}")
    return {"id": s.id}


# --------------------------------------------------------------------------- #
# Networks
# --------------------------------------------------------------------------- #
class NetworkIn(BaseModel):
    client_id: int
    name: str
    cidr: str
    site_id: int | None = None
    vlan: int | None = None
    gateway: str | None = None
    dns: str | None = None
    notes: str | None = None


def _serialize_network(db: Session, n: Network) -> dict:
    used = db.query(IPAddress).filter(IPAddress.network_id == n.id).count()
    try:
        info = networking.subnet_info(n.cidr)
        capacity = info["usable_hosts"]
    except ValueError:
        info, capacity = None, 0
    util = round(100.0 * used / capacity, 1) if capacity else None
    return {
        "id": n.id, "client_id": n.client_id, "site_id": n.site_id, "name": n.name,
        "cidr": n.cidr, "vlan": n.vlan, "gateway": n.gateway, "dns": n.dns, "notes": n.notes,
        "used": used, "capacity": capacity, "utilization_pct": util, "info": info,
    }


@router.get("/networks")
def list_networks(client_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    q = _scope(db.query(Network), Network, user)
    if client_id and is_staff(user):
        q = q.filter(Network.client_id == client_id)
    return [_serialize_network(db, n) for n in q.order_by(Network.name).all()]


@router.post("/networks", status_code=201)
def create_network(body: NetworkIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    try:
        networking.subnet_info(body.cidr)  # validate CIDR
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid CIDR: {e}")
    if body.site_id is not None:
        site = db.get(Site, body.site_id)
        if not site or site.client_id != body.client_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Site not in this client")
    n = Network(client_id=body.client_id, site_id=body.site_id, name=body.name[:200],
                cidr=body.cidr, vlan=body.vlan, gateway=body.gateway, dns=body.dns, notes=body.notes)
    db.add(n)
    db.commit()
    audit.record(db, action="network.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="network", target_id=str(n.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"cidr={n.cidr}")
    return {"id": n.id}


@router.delete("/networks/{network_id}")
def delete_network(network_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    n = db.get(Network, network_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
    db.query(IPAddress).filter(IPAddress.network_id == n.id).delete()
    cid = n.client_id
    db.delete(n)
    db.commit()
    audit.record(db, action="network.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="network", target_id=str(network_id),
                 client_id=cid, ip=_ip(request))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# IP addresses (IPAM)
# --------------------------------------------------------------------------- #
class IPIn(BaseModel):
    address: str
    hostname: str | None = None
    mac: str | None = None
    device_id: int | None = None
    status: str = "allocated"
    notes: str | None = None


@router.get("/networks/{network_id}/ips")
def list_ips(network_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Network, network_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
    assert_client_access(user, n.client_id)
    rows = db.query(IPAddress).filter(IPAddress.network_id == network_id).order_by(IPAddress.address).all()
    return [{"id": r.id, "address": r.address, "hostname": r.hostname, "mac": r.mac,
             "device_id": r.device_id, "status": r.status, "notes": r.notes} for r in rows]


@router.post("/networks/{network_id}/ips", status_code=201)
def allocate_ip(network_id: int, body: IPIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    n = db.get(Network, network_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
    if not networking.is_valid_ip(body.address):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid IP address")
    if not networking.ip_in_network(body.address, n.cidr):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{body.address} is outside {n.cidr}")
    if body.status not in ("allocated", "reserved", "free"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    dup = (db.query(IPAddress)
           .filter(IPAddress.network_id == network_id, IPAddress.address == body.address).first())
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.address} is already tracked in this network")
    rec = IPAddress(network_id=network_id, client_id=n.client_id, address=body.address,
                    hostname=body.hostname, mac=body.mac, device_id=body.device_id,
                    status=body.status, notes=body.notes)
    db.add(rec)
    db.commit()
    audit.record(db, action="ip.allocate", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ip_address", target_id=str(rec.id),
                 client_id=n.client_id, ip=_ip(request), detail=f"{body.address} net={n.name}")
    return {"id": rec.id}


@router.delete("/ips/{ip_id}")
def release_ip(ip_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rec = db.get(IPAddress, ip_id)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "IP not found")
    cid, addr = rec.client_id, rec.address
    db.delete(rec)
    db.commit()
    audit.record(db, action="ip.release", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="ip_address", target_id=str(ip_id),
                 client_id=cid, ip=_ip(request), detail=addr)
    return {"ok": True}
