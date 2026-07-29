"""v1.72 The School — open, self-serve academy accounts, isolated from clients.

The Cyber Academy is now its own front door: anyone can register (email or SSO)
and start hacking/learning, hack-this-site style — WITHOUT touching the MSP's
real client tenants. We do this with zero schema risk (no new Role enum value,
which on Postgres would need a migration): every self-registered learner is a
low-privilege CLIENT_VIEWER scoped to a single dedicated "Pulse Academy" client.

That gives us for free:
  * hard isolation — a student can only ever see the Academy tenant (which holds
    no devices, invoices, or client data), never a real client's data;
  * a global student leaderboard (they all share one tenant);
  * a clean routing signal — academy users land on /academy, not the client portal.

Real MSP clients keep coming in exactly as before (staff invite / domain SSO).
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.security import hash_password
from ..models import Client, Role, User

ACADEMY_CLIENT_NAME = "Pulse Academy"


def get_or_create_academy_client(db: Session) -> Client:
    c = (db.query(Client)
         .filter(func.lower(Client.name) == ACADEMY_CLIENT_NAME.lower()).first())
    if not c:
        c = Client(name=ACADEMY_CLIENT_NAME, primary_contact="Pulse Academy",
                   email="academy@bvtech.org",
                   notes="System tenant for self-registered Academy learners. "
                         "Isolated from real MSP clients.")
        db.add(c)
        db.commit()
    return c


def academy_client_id(db: Session) -> int | None:
    c = (db.query(Client.id)
         .filter(func.lower(Client.name) == ACADEMY_CLIENT_NAME.lower()).first())
    return c[0] if c else None


def is_academy_user(db: Session, user: User) -> bool:
    if not user.client_id:
        return False
    return user.client_id == academy_client_id(db)


def home_for(db: Session, user: User) -> str:
    """Where this user belongs after sign-in — the single source of truth used by
    both password login and the SSO callback."""
    if user.role in (Role.OWNER, Role.TECH):
        return "/dashboard"
    if is_academy_user(db, user):
        return "/academy"
    return "/portal"


def register_student(db: Session, *, email: str, password: str,
                     full_name: str | None = None) -> tuple[User | None, str | None]:
    """Create a self-serve Academy learner. Returns (user, error). Always the
    lowest privilege, always scoped to the Academy tenant — never staff, never a
    real client."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return None, "A valid email is required."
    if len(password or "") < 8:
        return None, "Password must be at least 8 characters."
    if db.query(User.id).filter(func.lower(User.email) == email).first():
        return None, "An account with that email already exists — try signing in."
    academy = get_or_create_academy_client(db)
    user = User(email=email, full_name=(full_name or email.split("@")[0])[:200],
                password_hash=hash_password(password), role=Role.CLIENT_VIEWER,
                client_id=academy.id, is_active=True)
    db.add(user)
    db.commit()
    return user, None


def get_or_create_sso_student(db: Session, email: str,
                              full_name: str | None = None) -> User | None:
    """SSO one-click Academy signup: match an existing user, else create a learner
    under the Academy tenant. Used only when a sign-in arrives through the Academy
    door (purpose='academy'), so it never opens account creation for the MSP."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return None
    existing = (db.query(User).filter(func.lower(User.email) == email)
                .filter(User.is_active.is_(True)).first())
    if existing:
        return existing
    academy = get_or_create_academy_client(db)
    user = User(email=email, full_name=(full_name or email.split("@")[0])[:200],
                password_hash=hash_password(hash_password(email)),  # unusable random-ish
                role=Role.CLIENT_VIEWER, client_id=academy.id, is_active=True)
    db.add(user)
    db.commit()
    return user
