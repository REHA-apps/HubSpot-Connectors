from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, HttpUrl, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Description:
        Centralized application configuration using Pydantic Settings.

    Rules Applied:
        - Uses HttpUrl for URL validation and SecretStr for sensitive values.
        - Loads configuration from .env files.
        - Provides computed properties for environment state and scope encoding.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        validate_default=True,
    )

    # App settings
    APP_NAME: str = "HubSpot CRM - Slack Connectors"
    APP_VERSION: str = "1.0.0"

    ENV: Literal["dev", "staging", "prod"] = "dev"

    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # HubSpot settings
    HUBSPOT_CLIENT_ID: str = Field(default="")
    HUBSPOT_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""))
    HUBSPOT_REDIRECT_URI: HttpUrl = Field(default=HttpUrl("http://localhost"))

    # Slack settings
    SLACK_CLIENT_ID: str = Field(default="")
    SLACK_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""))
    SLACK_REDIRECT_URI: HttpUrl = Field(default=HttpUrl("http://localhost"))
    SLACK_SIGNING_SECRET: SecretStr = Field(default=SecretStr(""))
    SLACK_BOT_TOKEN: SecretStr = Field(default=SecretStr(""))

    # Supabase settings
    SUPABASE_URL: HttpUrl = Field(default=HttpUrl("http://localhost"))
    SUPABASE_KEY: SecretStr = Field(default=SecretStr(""))

    # API settings
    API_BASE_URL: HttpUrl = Field(default=HttpUrl("http://localhost"))
    API_PUBLIC_URL: HttpUrl = Field(default=HttpUrl("http://localhost"))

    # Scopes
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
            "crm.objects.owners.read "
            "crm.schemas.companies.read "
            "conversations.read "
            "conversations.write "
            "tickets "
            "oauth"
        ),
        repr=False,
    )
    # "crm.schemas.contacts.read "

    SLACK_SCOPES: str = Field(
        default=(
            "commands chat:write chat:write.public users:read users:read.email "
            "app_mentions:read im:history channels:history groups:history "
            "mpim:history links:read links:write channels:read groups:read"
        ),
        repr=False,
    )

    def dump(self) -> Mapping[str, Any]:
        """Description:
            Returns a safe, scrubbed snapshot of the current configuration.

        Returns:
            Mapping[str, Any]: Configuration dictionary with sensitive values masked.

        Rules Applied:
            - Masks all SecretStr instances with '***'.

        """
        data = self.model_dump()

        def scrub(value: Any) -> Any:
            if isinstance(value, SecretStr):
                return "***"
            return value

        return {key: scrub(value) for key, value in data.items()}

    @computed_field(repr=False)
    @property
    def HUBSPOT_SCOPES_ENCODED(self) -> str:
        return self.HUBSPOT_SCOPES.replace(" ", "%20")

    @computed_field(repr=False)
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

    def require_prod_secrets(self) -> None:
        """Description:
            Validates that all necessary secrets are provided when running in prod.

        Returns:
            None

        Rules Applied:
            - Raises RuntimeError if any SecretStr is empty in a production environment.

        """
        if not self.is_prod:
            return

        missing = []
        for name, value in self.model_dump().items():
            if isinstance(value, SecretStr) and not value.get_secret_value():
                missing.append(name)

        if missing:
            raise RuntimeError(f"Missing required production secrets: {missing}")

    def validate_all(self) -> None:
        """Description:
            Executes all application-level configuration validation checks.

        Returns:
            None

        """
        self.require_prod_secrets()


settings = Settings()
