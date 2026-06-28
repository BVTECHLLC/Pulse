"""Central configuration. Everything comes from environment variables.
No secret is ever hardcoded — see .env.example for the full list."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Identity ---
    APP_NAME: str = "BVTech OpsPilot"
    APP_VERSION: str = "0.27.0"
    ENV: str = "development"  # development | production

    # --- Security ---
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
    SECRET_KEY: str
    ACCESS_TOKEN_TTL_MIN: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 14
    # Enrollment token signing for agents (separate key from user sessions)
    AGENT_ENROLL_SECRET: str

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://opspilot:opspilot@db:5432/pulse"
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Cookies / sessions ---
    COOKIE_SECURE: bool = True   # set False only for local http dev
    COOKIE_DOMAIN: str | None = None

    # --- Bootstrap admin (first run only; rotate after) ---
    BOOTSTRAP_ADMIN_EMAIL: str = "help@bvtech.org"
    BOOTSTRAP_ADMIN_PASSWORD: str | None = None  # if unset, a random one is printed once

    # --- Branding / public URLs ---
    SUPPORT_EMAIL: str = "help@bvtech.org"          # signup notifications land here
    PUBLIC_BASE_URL: str = "https://portal.bvtech.org"

    # Where prebuilt standalone agent binaries live. The build-agent workflow
    # publishes opspilot-agent.exe / opspilot-agent to GitHub Releases; the repo
    # is public so the `latest` asset URLs are downloadable without auth. If a
    # binary is present locally in agent/dist/ it's served directly; otherwise
    # /download/agent.exe redirects here so the .exe works as soon as it's built.
    AGENT_RELEASE_BASE: str = "https://github.com/BVTECHLLC/Pulse/releases/latest/download"

    # --- Outbound email (SMTP). If unset, email is logged, never sent (safe no-op). ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None       # defaults to SUPPORT_EMAIL when unset
    SMTP_STARTTLS: bool = True

    # --- Microsoft 365 (Graph) — app-only, multi-tenant. Keys via env/secrets. ---
    M365_CLIENT_ID: str | None = None
    M365_CLIENT_SECRET: str | None = None
    M365_LOGIN_BASE: str = "https://login.microsoftonline.com"
    M365_GRAPH_BASE: str = "https://graph.microsoft.com/v1.0"

    # --- OAuth2 / SSO sign-in & connectors (authorization-code + PKCE) ---
    # Microsoft reuses M365_CLIENT_ID/SECRET; Google uses its own pair. When a
    # provider's credentials are present it lights up automatically (SSO button +
    # connector). Tenant 'common' allows any work/school/personal account.
    MS_OAUTH_TENANT: str = "common"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_ALLOW_SSO: bool = True   # allow signing in via a matched provider account

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def ms_oauth_enabled(self) -> bool:
        return bool(self.M365_CLIENT_ID and self.M365_CLIENT_SECRET)

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_PER_MIN: int = 5
    RATE_LIMIT_SIGNUP_PER_MIN: int = 3

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_HOST)

    @property
    def m365_enabled(self) -> bool:
        return bool(self.M365_CLIENT_ID and self.M365_CLIENT_SECRET)

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
