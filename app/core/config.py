"""Application configuration.

All configuration comes from environment variables (or a local .env file).
No secret is ever written in code. See .env.example for the full list.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "SitePilot AI"
    app_env: str = "development"
    debug: bool = True
    app_version: str = "0.1.0"

    # PostgreSQL in real use. SQLite only for local experiments / tests.
    database_url: str = "sqlite:///./sitepilot_dev.db"

    # JWT signing key (used from Phase 2). Must be overridden in real .env.
    secret_key: str = "change-me-in-your-real-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Groq LLM (Phase 5). Optional in Phase 1 so the app runs without it.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    @property
    def groq_configured(self) -> bool:
        """True only when a Groq key is actually present."""
        return bool(self.groq_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Cached settings — one instance for the whole process."""
    return Settings()
