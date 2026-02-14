# app/core/config.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field, HttpUrl, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration with:
    - URL validation
    - SecretStr for sensitive values
    - Environment-based config
    - Safe dump() helper
    - Computed environment flags
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        validate_default=True,
    )

    # ---------------------------------------------------------
    # App
    # ---------------------------------------------------------
    APP_NAME: str = "CRM Connectors"
    APP_VERSION: str = "1.0.0"

    ENV: str = "dev"

    # ---------------------------------------------------------
    # HubSpot
    # ---------------------------------------------------------
    HUBSPOT_CLIENT_ID: str = Field(...)
    HUBSPOT_CLIENT_SECRET: SecretStr = Field(...)
    HUBSPOT_REDIRECT_URI: HttpUrl = Field(...)

    # ---------------------------------------------------------
    # Slack
    # ---------------------------------------------------------
    SLACK_CLIENT_ID: str = Field(...)
    SLACK_CLIENT_SECRET: SecretStr = Field(...)
    SLACK_REDIRECT_URI: HttpUrl = Field(...)
    SLACK_SIGNING_SECRET: SecretStr = Field(...)
    SLACK_BOT_TOKEN: SecretStr = Field(...)

    # ---------------------------------------------------------
    # Supabase
    # ---------------------------------------------------------
    SUPABASE_URL: HttpUrl = Field(...)
    SUPABASE_KEY: SecretStr = Field(...)

    # ---------------------------------------------------------
    # Safe dump
    # ---------------------------------------------------------
    def dump(self) -> Mapping[str, Any]:
        """Return a safe, non-secret configuration snapshot."""
        data = self.model_dump()

        def scrub(value: Any) -> Any:
            if isinstance(value, SecretStr):
                return "***"
            return value

        return {key: scrub(value) for key, value in data.items()}

    # ---------------------------------------------------------
    # Environment flags
    # ---------------------------------------------------------
    @computed_field
    @property
    def is_dev(self) -> bool:
        return self.ENV.lower() == "dev"

    @computed_field
    @property
    def is_staging(self) -> bool:
        return self.ENV.lower() == "staging"

    @computed_field
    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "prod"

    # ---------------------------------------------------------
    # Optional: production validation
    # ---------------------------------------------------------
    def require_prod_secrets(self) -> None:
        """Ensure all secrets are present in production."""
        if not self.is_prod:
            return

        missing = [
            name
            for name, value in self.model_dump().items()
            if isinstance(value, SecretStr) and not value.get_secret_value()
        ]

        if missing:
            raise RuntimeError(f"Missing required production secrets: {missing}")


settings = Settings()  # pyright: ignore[reportCallIssue]
