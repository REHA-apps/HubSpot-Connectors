from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

class Settings(BaseSettings):
    # ... (rest of the class remains same)
    HUBSPOT_CLIENT_ID: str = Field(default="")
    HUBSPOT_CLIENT_SECRET: str = Field(default="")
    HUBSPOT_REDIRECT_URI: str = Field(default="")

    SLACK_BOT_TOKEN: str = Field(default="")
    SLACK_SIGNING_SECRET: str = Field(default="")

    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def hubspot_client_secret_raw(self) -> str:
        return self.HUBSPOT_CLIENT_SECRET

    @property
    def slack_signing_secret_raw(self) -> str:
        return self.SLACK_SIGNING_SECRET

@lru_cache()
def get_settings() -> Settings:
    """Returns a cached instance of the application settings."""
    return Settings()

# Create a single instance for easier access
settings = get_settings()
