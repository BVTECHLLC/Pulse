"""Shared pytest fixtures.

IMPORTANT: environment variables are set here, at import time, BEFORE any
`app.*` module is imported. `app.core.db` builds the SQLAlchemy engine from
DATABASE_URL at import time and `app.core.config.Settings` requires SECRET_KEY /
AGENT_ENROLL_SECRET to exist, so they must be present the moment those modules
load. pytest imports conftest.py before collecting the test modules, which makes
this the correct place to do it.
"""
from __future__ import annotations

import os
import pathlib
import tempfile

# --- test environment (must precede the app imports below) ------------------ #
os.environ.setdefault("SECRET_KEY", "pytest_secret_key_not_for_production_use_xxxxxxxxxxxx")
os.environ.setdefault("AGENT_ENROLL_SECRET", "pytest_enroll_secret_not_for_production_yyyyyyyy")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ENV", "development")
# Force a throwaway SQLite DB for hermetic tests regardless of any DATABASE_URL
# the developer may have exported in their shell.
_DB_FILE = pathlib.Path(tempfile.gettempdir()) / "pulse_pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"

import pytest  # noqa: E402

import app.models as models  # noqa: E402  (registers all tables on Base.metadata)
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token, hash_api_key  # noqa: E402
from app.models import APIKey, AuthSession, Client, Role, User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Build the schema once for the whole test session."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db(_schema):
    """A clean database session per test. Rows are cleared afterwards (cheaper
    and far less memory-churn than dropping/recreating the full schema each
    test, which keeps the suite light enough for constrained CI runners)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


# --------------------------------------------------------------------------- #
# Convenience factories — keep the auth/RBAC tests terse.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def make_client(db):
    def _make(name: str = "Acme Co") -> Client:
        c = Client(name=name)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c
    return _make


@pytest.fixture()
def make_user(db):
    _seq = {"n": 0}

    def _make(role: Role = Role.OWNER, client_id: int | None = None,
              is_active: bool = True) -> User:
        _seq["n"] += 1
        u = User(
            # These tests authenticate via tokens / API keys, never by verifying a
            # password, so we skip the (deliberately slow) Argon2 hash here and use
            # a placeholder. Password hashing itself is covered in test_security.py.
            email=f"user{_seq['n']}@test.local",
            full_name=f"User {_seq['n']}",
            password_hash="placeholder-not-a-real-hash",
            role=role,
            client_id=client_id,
            is_active=is_active,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    return _make


@pytest.fixture()
def login(db):
    """Return (token, session) for a user — a real access token backed by a live
    AuthSession row, exactly like the login route produces."""
    from datetime import datetime, timedelta, timezone

    def _login(user: User) -> tuple[str, AuthSession]:
        sid = f"sid-{user.id}-{user.email}"
        sess = AuthSession(
            id=sid,
            user_id=user.id,
            refresh_hash="x" * 16,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            revoked=False,
        )
        db.add(sess)
        db.commit()
        token = create_access_token(user_id=user.id, role=user.role.value, session_id=sid)
        return token, sess
    return _login


@pytest.fixture()
def make_api_key(db):
    def _make(user: User, plaintext: str = "pk_live_testkey_abcdef", revoked: bool = False) -> str:
        row = APIKey(
            user_id=user.id,
            label="test",
            prefix=plaintext[:8],
            key_hash=hash_api_key(plaintext),
            revoked=revoked,
        )
        db.add(row)
        db.commit()
        return plaintext
    return _make
