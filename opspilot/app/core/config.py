"""Central configuration. Everything comes from environment variables.
No secret is ever hardcoded — see .env.example for the full list."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Identity ---
    APP_NAME: str = "BVTech OpsPilot"
    APP_VERSION: str = "0.6.0"
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
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@bvtech.org"
    BOOTSTRAP_ADMIN_PASSWORD: str | None = None  # if unset, a random one is printed once

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_PER_MIN: int = 5

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
