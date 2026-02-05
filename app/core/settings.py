from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    cors_origins: str = ""

    database_url: str

    jwt_secret: str
    jwt_issuer: str = "cyberxercise"
    jwt_audience: str = "cyberxercise-api"
    jwt_access_ttl_seconds: int = 3600

    # Dev-only convenience. Do not enable in production.
    allow_instructor_register: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
