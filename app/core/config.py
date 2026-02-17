# app/core/config.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, HttpUrl, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration with:
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
    APP_NAME: str = "HubSpot CRM - Slack Connectors"
    APP_VERSION: str = "1.0.0"

    ENV: Literal["dev", "staging", "prod"] = "dev"

    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # ---------------------------------------------------------
    # HubSpot
    # ---------------------------------------------------------
    HUBSPOT_CLIENT_ID: str = Field(default="")
    HUBSPOT_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""))
    HUBSPOT_REDIRECT_URI: HttpUrl = Field(default=HttpUrl("http://localhost"))

    # ---------------------------------------------------------
    # Slack
    # ---------------------------------------------------------
    SLACK_CLIENT_ID: str = Field(default="")
    SLACK_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""))
    SLACK_REDIRECT_URI: HttpUrl = Field(default=HttpUrl("http://localhost"))
    SLACK_SIGNING_SECRET: SecretStr = Field(default=SecretStr(""))
    SLACK_BOT_TOKEN: SecretStr = Field(default=SecretStr(""))

    # ---------------------------------------------------------
    # Supabase
    # ---------------------------------------------------------
    SUPABASE_URL: HttpUrl = Field(default=HttpUrl("http://localhost"))
    SUPABASE_KEY: SecretStr = Field(default=SecretStr(""))

    # ---------------------------------------------------------
    # API
    # --------------------------------------------------------- 
    API_BASE_URL: HttpUrl = Field(default=HttpUrl("http://localhost"))
    API_PUBLIC_URL: HttpUrl = Field(default=HttpUrl("http://localhost"))

    # ---------------------------------------------------------
    # HubSpot Scopes
    # ---------------------------------------------------------
    HUBSPOT_SCOPES: str = Field(
        default=(
            "crm.objects.contacts.read "
            "crm.objects.contacts.write "
            "crm.objects.companies.read "
            "crm.objects.companies.write "
            "crm.objects.deals.read "
            "crm.objects.deals.write "
            "crm.objects.leads.read "
            "crm.objects.leads.write "
            "oauth"
            "crm.schemas.companies.read "
        ),
    )   
    # "crm.schemas.contacts.read "

    SLACK_SCOPES: str = (
        "commands "
        "chat:write "
        "chat:write.public "
        "users:read "
        "users:read.email"
    )
   
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

    @computed_field
    @property
    def HUBSPOT_SCOPES_ENCODED(self) -> str:
        return self.HUBSPOT_SCOPES.replace(" ", "%20")

    @computed_field
    @property
    def SLACK_SCOPES_ENCODED(self) -> str:
        return self.SLACK_SCOPES.replace(" ", "%20")

    # ---------------------------------------------------------
    # Environment normalization
    # ---------------------------------------------------------
    @computed_field
    @property
    def env_normalized(self) -> str:
        return self.ENV.lower()

    # ---------------------------------------------------------
    # Environment flags
    # ---------------------------------------------------------
    @computed_field
    @property
    def is_dev(self) -> bool:
        return self.env_normalized == "dev"

    @computed_field
    @property
    def is_staging(self) -> bool:
        return self.env_normalized == "staging"

    @computed_field
    @property
    def is_prod(self) -> bool:
        return self.env_normalized == "prod"

    @computed_field
    @property
    def is_debug(self) -> bool:
        return self.DEBUG or self.is_dev

    # ---------------------------------------------------------
    # Production validation
    # ---------------------------------------------------------
    def require_prod_secrets(self) -> None:
        """Ensure all secrets are present in production."""
        if not self.is_prod:
            return

        missing = []
        for name, value in self.model_dump().items():
            if isinstance(value, SecretStr) and not value.get_secret_value():
                missing.append(name)

        if missing:
            raise RuntimeError(f"Missing required production secrets: {missing}")

    # ---------------------------------------------------------
    # Full validation entrypoint
    # ---------------------------------------------------------
    def validate_all(self) -> None:
        """Run all validation checks."""
        self.require_prod_secrets()


settings = Settings()