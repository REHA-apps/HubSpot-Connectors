# app/core/config.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration with:
    - URL validation
    - SecretStr for sensitive values
    - Environment-based config
    - Safe dump() helper
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    APP_NAME: str = "CRM Connectors"
    ENV: str = "dev"
    HUBSPOT_CLIENT_ID: str = Field(...)
    HUBSPOT_CLIENT_SECRET: SecretStr = Field(...)
    HUBSPOT_REDIRECT_URI: HttpUrl = Field(...)

    SLACK_CLIENT_ID: str = Field(...)
    SLACK_CLIENT_SECRET: SecretStr = Field(...)
    SLACK_REDIRECT_URI: HttpUrl = Field(...)
    SLACK_SIGNING_SECRET: SecretStr = Field(...)

    SLACK_BOT_TOKEN: SecretStr = Field(...)

    SUPABASE_URL: HttpUrl = Field(...)
    SUPABASE_KEY: SecretStr = Field(...)

    def dump(self) -> Mapping[str, Any]:
        """Return a safe, non-secret configuration snapshot."""
        data = self.model_dump()

        def scrub(value: Any) -> Any:
            if isinstance(value, SecretStr):
                return "***"
            return value

        return {key: scrub(value) for key, value in data.items()}

    @property
    def is_dev(self) -> bool:
        return self.ENV.lower() == "dev"

    @property
    def is_staging(self) -> bool:
        return self.ENV.lower() == "staging"

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "prod"


settings = Settings()  # pyright: ignore[reportCallIssue]
