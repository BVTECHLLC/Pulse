"""Database models for OpsPilot v0.1.

Tenancy model: every client-scoped row carries `client_id`. BVTech staff
(OWNER/TECH) can see across clients; CLIENT_ADMIN/CLIENT_VIEWER are constrained
to their own client_id at the query layer (see app.core.deps.scoped_query).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Float, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    OWNER = "owner"            # BVTech owner/admin — full control
    TECH = "tech"             # BVTech technician — operational, no destructive config
    CLIENT_ADMIN = "client_admin"   # client's admin — their org only
    CLIENT_VIEWER = "client_viewer"  # client read-only


STAFF_ROLES = {Role.OWNER, Role.TECH}
CLIENT_ROLES = {Role.CLIENT_ADMIN, Role.CLIENT_VIEWER}


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_contact: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    site_address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="client")
    devices: Mapped[list["Device"]] = relationship(back_populates="client")
    licenses: Mapped[list["License"]] = relationship(back_populates="client")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.CLIENT_VIEWER)
    # null for BVTech staff; set for client-side users
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # MFA
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped["Client | None"] = relationship(back_populates="users")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")


class AuthSession(Base):
    """DB-backed refresh sessions so we can revoke. Access tokens reference sid."""
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # session_id (jti-ish)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(200), nullable=False)
    os: Mapped[str | None] = mapped_column(String(120))
    serial: Mapped[str | None] = mapped_column(String(120))
    ip: Mapped[str | None] = mapped_column(String(64))
    cpu_pct: Mapped[float | None] = mapped_column(Float)
    ram_pct: Mapped[float | None] = mapped_column(Float)
    disk_pct: Mapped[float | None] = mapped_column(Float)
    logged_in_user: Mapped[str | None] = mapped_column(String(200))
    av_status: Mapped[str | None] = mapped_column(String(120))
    patch_status: Mapped[str | None] = mapped_column(String(120))
    health_score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    last_checkin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # agent linkage
    enroll_id: Mapped[str | None] = mapped_column(String(64), index=True)
    agent_key_hash: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    client: Mapped["Client"] = relationship(back_populates="devices")


class License(Base):
    __tablename__ = "licenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    product: Mapped[str] = mapped_column(String(200), nullable=False)
    seats: Mapped[int | None] = mapped_column(Integer)
    seats_used: Mapped[int | None] = mapped_column(Integer)
    monthly_cost: Mapped[float | None] = mapped_column(Float)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    client: Mapped["Client"] = relationship(back_populates="licenses")


class AuditLog(Base):
    """Append-only audit trail. We never UPDATE or DELETE these rows."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer)
    actor_email: Mapped[str | None] = mapped_column(String(200))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(80))
    client_id: Mapped[int | None] = mapped_column(Integer, index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=True)


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportTicket(Base):
    """Client-submitted support requests. Visible to the submitting client and all staff."""
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low|normal|high|urgent
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.OPEN, index=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class DeviceCheckin(Base):
    """One row per agent check-in — the historical record. Latest summary also
    lives denormalized on Device for fast list views."""
    __tablename__ = "device_checkins"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    cpu_pct: Mapped[float | None] = mapped_column(Float)
    ram_pct: Mapped[float | None] = mapped_column(Float)
    disk_pct: Mapped[float | None] = mapped_column(Float)
    health_score: Mapped[int | None] = mapped_column(Integer)
    av_status: Mapped[str | None] = mapped_column(String(120))
    patch_status: Mapped[str | None] = mapped_column(String(120))


# --------------------------------------------------------------------------- #
# v0.3 — Monitoring & alerting
# --------------------------------------------------------------------------- #
class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Stable machine-readable alert kinds. The monitoring engine opens at most one
# non-resolved alert per (device, kind), so these double as dedup keys.
ALERT_OFFLINE = "device_offline"
ALERT_DISK_FULL = "disk_full"
ALERT_HIGH_CPU = "high_cpu"
ALERT_HIGH_RAM = "high_ram"
ALERT_AV_OFF = "antivirus_off"
ALERT_PATCH_BEHIND = "patch_behind"
ALERT_LOW_HEALTH = "low_health"


class Alert(Base):
    """A monitoring alert raised by the engine against a device. Lifecycle:
    active -> acknowledged (optional) -> resolved. The engine auto-resolves an
    alert when its triggering condition clears, so the table stays a faithful
    record of incidents rather than stale noise."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.WARNING)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.ACTIVE, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float)  # the reading that tripped it
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertPolicy(Base):
    """Threshold configuration for the monitoring engine. A row with
    client_id=NULL is the global default; a per-client row overrides it for that
    client. The engine falls back to built-in defaults if no row exists."""
    __tablename__ = "alert_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), unique=True)
    disk_pct_max: Mapped[float] = mapped_column(Float, default=90.0)
    cpu_pct_max: Mapped[float] = mapped_column(Float, default=95.0)
    ram_pct_max: Mapped[float] = mapped_column(Float, default=95.0)
    health_min: Mapped[int] = mapped_column(Integer, default=60)
    offline_minutes: Mapped[int] = mapped_column(Integer, default=30)
    alert_on_av_off: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_patch_behind: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TicketComment(Base):
    """A threaded reply on a support ticket. `internal=True` comments are staff
    notes never shown to client users; client-visible comments form the
    conversation the client sees in the portal."""
    __tablename__ = "ticket_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"), index=True, nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(Integer)
    author_email: Mapped[str | None] = mapped_column(String(200))
    author_role: Mapped[str | None] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    internal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
