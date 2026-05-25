from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(
        default="workflow-webhook-platform",
        validation_alias="APP_NAME",
    )
    app_env: str = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
