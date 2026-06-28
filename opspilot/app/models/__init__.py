"""Database models for OpsPilot v0.1.

Tenancy model: every client-scoped row carries `client_id`. BVTech staff
(OWNER/TECH) can see across clients; CLIENT_ADMIN/CLIENT_VIEWER are constrained
to their own client_id at the query layer (see app.core.deps.scoped_query).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, Float,
    UniqueConstraint, func,
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
    patches_pending: Mapped[int | None] = mapped_column(Integer)  # count of pending updates
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
    # SLA tracking (v0.4) — due targets stamped at creation from the SLA policy;
    # first_responded_at/resolved_at recorded as the ticket progresses.
    first_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once the automation engine has fired a breach event for this ticket, so
    # the recurring run-checks tick doesn't re-fire every cycle. Reset on reopen.
    sla_breach_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
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


class DeviceSoftware(Base):
    """Installed-software inventory reported by the agent (v0.19). One row per
    (device, app); the agent replaces a device's full set on each inventory
    report. Powers license tracking and 'who has package X?' vulnerability
    response across the fleet."""
    __tablename__ = "device_software"
    __table_args__ = (UniqueConstraint("device_id", "name", "version",
                                       name="uq_device_software"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(120))
    publisher: Mapped[str | None] = mapped_column(String(200))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DevicePatch(Base):
    """Pending OS/software updates reported by the agent (v0.20). The agent
    replaces a device's pending set on each report. Powers patch-compliance
    visibility across the fleet."""
    __tablename__ = "device_patches"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    kb: Mapped[str | None] = mapped_column(String(60))         # e.g. KB5034123 (Windows)
    severity: Mapped[str | None] = mapped_column(String(40))   # critical|important|security|other
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReportSchedule(Base):
    """Recurring client report delivery (v0.20). The run-checks tick emails the
    client's branded report on the configured cadence."""
    __tablename__ = "report_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(200), nullable=False)
    cadence: Mapped[str] = mapped_column(String(20), default="monthly")  # weekly|monthly|quarterly
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# --------------------------------------------------------------------------- #
# v0.21 — Integrations & command center: API keys, outbound/inbound webhooks,
# and an integration catalog so Pulse can interoperate with anything.
# --------------------------------------------------------------------------- #
class APIKey(Base):
    """Programmatic access key. Authenticates AS the user that owns it (so it
    inherits that user's role + client scope). We store only a SHA-256 hash; the
    plaintext is shown exactly once at creation."""
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), index=True)   # shown for identification
    key_hash: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Canonical internal events external systems can subscribe to.
WEBHOOK_EVENTS = [
    "ticket.created", "ticket.updated", "ticket.sla_breached",
    "alert.opened", "alert.resolved", "device.enrolled", "device.offline",
    "invoice.created", "client.created", "signup.received",
]


class WebhookSubscription(Base):
    """Outbound event delivery: when an internal event fires, POST a signed JSON
    payload to this URL. Lets any external tool react to Pulse in real time."""
    __tablename__ = "webhook_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list)   # subset of WEBHOOK_EVENTS; [] = all
    secret: Mapped[str | None] = mapped_column(String(120))    # HMAC-SHA256 signing secret
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_status: Mapped[int | None] = mapped_column(Integer)   # last HTTP status seen
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InboundSource(Base):
    """Inbound ingest endpoint. Any external tool can POST JSON to
    /api/ingest/{token}; we create a ticket or alert for the bound client.
    The token is the shared secret (kept server-side, shown once)."""
    __tablename__ = "inbound_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(20), default="ticket")  # ticket|alert
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IntegrationConnection(Base):
    """A configured connection to an external product (PSA/RMM/docs/comms/etc.).
    Config is free-form JSON (keys, base URLs, etc.). This is the command-center
    hub — what's connected, and how."""
    __tablename__ = "integration_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # catalog key
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str | None] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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


# --------------------------------------------------------------------------- #
# v0.4 — PSA depth: SLAs, time tracking, IT documentation
# --------------------------------------------------------------------------- #
# Valid ticket priorities, ordered low -> urgent. Shared by SLA defaults & guards.
PRIORITIES = ("low", "normal", "high", "urgent")


class SLAPolicy(Base):
    """Per-priority response/resolution targets (in minutes). One row per
    (scope, priority) where scope is a client_id or NULL for the global default.
    The engine resolves per-client first, then global, then built-in defaults."""
    __tablename__ = "sla_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TimeEntry(Base):
    """Billable/non-billable work logged against a ticket by staff. Powers PSA
    time rollups and (later) invoicing."""
    __tablename__ = "time_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer)
    user_email: Mapped[str | None] = mapped_column(String(200))
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    billable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Set when this entry has been rolled into an invoice (v0.10).
    invoiced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    invoice_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class KBArticle(Base):
    """IT documentation / knowledge-base article. `client_id` NULL means it's a
    global article applicable to every client. `visibility` of 'internal' keeps
    it staff-only; 'client' exposes it to that client's portal users."""
    __tablename__ = "kb_articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="internal", index=True)  # internal|client
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    author_email: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


# --------------------------------------------------------------------------- #
# v0.5 — Automation engine (server-side, safe & logged; no remote code exec)
# --------------------------------------------------------------------------- #
# Triggers the engine reacts to. Events are emitted by the platform itself.
TRIGGER_ALERT_OPENED = "alert.opened"
TRIGGER_TICKET_CREATED = "ticket.created"
TRIGGER_SLA_BREACHED = "ticket.sla_breached"
AUTOMATION_TRIGGERS = (TRIGGER_ALERT_OPENED, TRIGGER_TICKET_CREATED, TRIGGER_SLA_BREACHED)

# Safe, in-platform actions. NOTHING here touches an endpoint or runs code on a
# device — actions only manipulate OpsPilot's own records.
ACTION_CREATE_TICKET = "create_ticket"   # alert -> open a ticket
ACTION_ACK_ALERT = "ack_alert"           # auto-acknowledge the alert
ACTION_NOTIFY = "notify"                  # raise an in-app notification
ACTION_ASSIGN = "assign"                  # assign ticket (explicit user or auto least-loaded)
ACTION_SET_PRIORITY = "set_priority"      # bump/lower ticket priority
ACTION_ADD_NOTE = "add_note"              # internal note on the ticket
AUTOMATION_ACTIONS = (
    ACTION_CREATE_TICKET, ACTION_ACK_ALERT, ACTION_NOTIFY,
    ACTION_ASSIGN, ACTION_SET_PRIORITY, ACTION_ADD_NOTE,
)


class AutomationRule(Base):
    """A trigger + match conditions + ordered actions. Disabled rules are inert.
    `client_id` NULL applies the rule to every client; otherwise it's scoped."""
    __tablename__ = "automation_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    # e.g. {"severity": "critical"} or {"priority": "urgent"} — all keys must match.
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    # e.g. [{"type": "create_ticket", "priority": "high"}, {"type": "notify"}]
    actions: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    author_email: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)


class AutomationRun(Base):
    """Execution-log row: one per rule that matched and ran. The audit trail for
    'why did the system do that?'."""
    __tablename__ = "automation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, index=True)
    rule_name: Mapped[str | None] = mapped_column(String(200))
    trigger: Mapped[str] = mapped_column(String(40), index=True)
    client_id: Mapped[int | None] = mapped_column(Integer, index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class Notification(Base):
    """An in-app notification. `target_user_id` NULL means 'all staff'. Raised by
    automation actions and (later) other subsystems."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(Integer, index=True)
    target_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(40), default="info")
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# --------------------------------------------------------------------------- #
# v0.6 — Security posture & remediation (defensive: track & fix, never exploit)
# --------------------------------------------------------------------------- #
class FindingSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(str, enum.Enum):
    OPEN = "open"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    RISK_ACCEPTED = "risk_accepted"  # documented, accepted by the client


class AssessmentStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SecurityAssessment(Base):
    """An authorized security review engagement. `authorized_by` records WHO at
    the client gave written authorization — assessments without an authorizing
    party are a compliance/ethics red flag, so the field is required by the API.
    This is documentation of defensive work; it never executes anything."""
    __tablename__ = "security_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)            # systems/IPs in scope
    authorized_by: Mapped[str] = mapped_column(String(200), nullable=False)  # client authoriser
    status: Mapped[AssessmentStatus] = mapped_column(Enum(AssessmentStatus), default=AssessmentStatus.PLANNED, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    author_email: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SecurityFinding(Base):
    """A vulnerability / security finding to be tracked and remediated. May be
    tied to a device and/or an assessment. High & critical findings raise an
    alert through the existing engine so automation can act (e.g. open a ticket)."""
    __tablename__ = "security_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("security_assessments.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), index=True)  # e.g. patching, config, credential
    severity: Mapped[FindingSeverity] = mapped_column(Enum(FindingSeverity), default=FindingSeverity.MEDIUM, index=True)
    cve: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FindingStatus] = mapped_column(Enum(FindingStatus), default=FindingStatus.OPEN, index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")  # manual|assessment|import
    client_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_id: Mapped[int | None] = mapped_column(Integer)  # linked alert, if one was raised
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    author_email: Mapped[str | None] = mapped_column(String(200))


# --------------------------------------------------------------------------- #
# v0.7 — Script library & deployment governance
#
# SAFETY MODEL (read before touching this):
#   * A script is INERT until an OWNER flips `enabled = True`.
#   * Pushing a script to a device is a *request* that (by default) needs an
#     OWNER approval, and the approver must NOT be the requester (separation of
#     duties). Consent + a reason are recorded on every request.
#   * The exact content+version is SNAPSHOTTED onto the deployment at request
#     time, so editing the library later can't change what was approved/runs.
#   * The agent PULLS only its own approved jobs and reports results; the server
#     never pushes ad-hoc commands. The agent runner is itself opt-in.
#   Result: no arbitrary remote code execution — only approved, logged,
#   attributable, content-pinned jobs.
# --------------------------------------------------------------------------- #
SCRIPT_LANGUAGES = ("powershell", "bash", "python", "cmd")
SCRIPT_RISK_LEVELS = ("low", "medium", "high")


class DeploymentStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"          # ready for the agent to pull
    RUNNING = "running"            # agent has picked it up
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELED = "canceled"


class Script(Base):
    """A reusable script in the library. Disabled by default; only an OWNER may
    enable it. Editing bumps `version` so deployment snapshots stay meaningful."""
    __tablename__ = "scripts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    author_email: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ScriptDeployment(Base):
    """A request to run a specific script on a specific device. Content/version
    are snapshotted so what is approved is exactly what runs."""
    __tablename__ = "script_deployments"
    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("scripts.id"), index=True)
    script_name: Mapped[str] = mapped_column(String(200))
    script_version: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)           # snapshot of what runs
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(Enum(DeploymentStatus),
                                                     default=DeploymentStatus.PENDING_APPROVAL, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    consent_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer)
    requested_by_email: Mapped[str | None] = mapped_column(String(200))
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer)
    approved_by_email: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)  # rejection reason / notes
    exit_code: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# --------------------------------------------------------------------------- #
# v0.8 — Public signup / access requests
# --------------------------------------------------------------------------- #
class SignupRequest(Base):
    """A public 'request access' submission from the marketing/login page. It is
    a lead, NOT an account — staff review and provision deliberately (open
    self-provisioning into an MSP console would be a security hole)."""
    __tablename__ = "signup_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    company: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new|contacted|approved|rejected
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# --------------------------------------------------------------------------- #
# v0.9 — Microsoft 365 (read-only Graph; app-only, multi-tenant)
# --------------------------------------------------------------------------- #
class M365Connection(Base):
    """Per-client link to a customer's Microsoft 365 tenant. The MSP app (client
    id/secret from env) gets app-only, read-only tokens for `tenant_id`. Cached
    access tokens are stored ENCRYPTED at rest (see services/crypto.py)."""
    __tablename__ = "m365_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|connected|error
    access_token_enc: Mapped[str | None] = mapped_column(Text)   # encrypted cache
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    secure_score: Mapped[int | None] = mapped_column(Integer)
    secure_score_max: Mapped[int | None] = mapped_column(Integer)
    license_count: Mapped[int | None] = mapped_column(Integer)
    risky_signin_count: Mapped[int | None] = mapped_column(Integer)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(200))
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


# --------------------------------------------------------------------------- #
# v0.10 — Invoicing (turns billable time + licenses into invoices)
# --------------------------------------------------------------------------- #
class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    VOID = "void"


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    number: Mapped[str | None] = mapped_column(String(40), index=True)   # e.g. INV-00001
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)     # percent
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # time|license|manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# --------------------------------------------------------------------------- #
# v0.11 — Sites & networking (IPAM)
# --------------------------------------------------------------------------- #
class Site(Base):
    """A physical/logical location for a client (HQ, branch, datacenter)."""
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Network(Base):
    """A subnet/VLAN for a client (optionally tied to a site). `cidr` drives the
    IPAM math (usable hosts, ranges) computed in services/networking.py."""
    __tablename__ = "networks"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cidr: Mapped[str] = mapped_column(String(64), nullable=False)   # e.g. 10.0.0.0/24
    vlan: Mapped[int | None] = mapped_column(Integer)
    gateway: Mapped[str | None] = mapped_column(String(64))
    dns: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IPAddress(Base):
    """A tracked IP within a Network. Unique per (network, address)."""
    __tablename__ = "ip_addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    network_id: Mapped[int] = mapped_column(ForeignKey("networks.id"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hostname: Mapped[str | None] = mapped_column(String(200))
    mac: Mapped[str | None] = mapped_column(String(40))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    status: Mapped[str] = mapped_column(String(20), default="allocated")  # allocated|reserved|free
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (UniqueConstraint("network_id", "address", name="uq_ip_per_network"),)


# --------------------------------------------------------------------------- #
# v0.12 — Network diagnostics (agent-run, read-only probes on a client's LAN)
# --------------------------------------------------------------------------- #
DIAG_KINDS = ("ping", "traceroute", "dns", "port_check", "subnet_discovery")


class DiagnosticRequest(Base):
    """A read-only network probe queued for an on-site agent to run and report.
    Non-destructive by design (no config changes) — the agent only inspects."""
    __tablename__ = "diagnostic_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target: Mapped[str | None] = mapped_column(String(200))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|running|done|failed
    result: Mapped[str | None] = mapped_column(Text)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer)
    requested_by_email: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- #
# v0.14 — Recurring service contracts (MRR)
# --------------------------------------------------------------------------- #
class Contract(Base):
    """A recurring service agreement — flat monthly (or per-period) revenue that
    feeds the billing/MRR rollup independently of license costs."""
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)      # per billing period
    billing_period: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly|quarterly|annual
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|paused|expired
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# --------------------------------------------------------------------------- #
# v0.15 — Notification channels (fan out in-app notifications to email/Slack/etc)
# --------------------------------------------------------------------------- #
CHANNEL_TYPES = ("email", "slack", "teams", "webhook")
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


class NotificationChannel(Base):
    """An outbound delivery target configured by staff. When a notification is
    raised, it fans out to enabled channels whose scope + min severity match."""
    __tablename__ = "notification_channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)   # email|slack|teams|webhook
    target: Mapped[str] = mapped_column(Text, nullable=False)        # email addr or webhook URL
    min_severity: Mapped[str] = mapped_column(String(20), default="info")
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)  # None = all
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
