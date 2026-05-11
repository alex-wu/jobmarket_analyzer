"""Centralised settings, surfaced via environment / .env. See `.env.example`."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    adzuna_app_id: str = Field(default="", description="Adzuna developer app_id")
    adzuna_app_key: str = Field(default="", description="Adzuna developer app_key")

    llm_enabled: bool = Field(default=False)
    llm_base_url: str = Field(default="")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="")

    gh_token: str = Field(default="", description="Set automatically by GitHub Actions")


settings = Settings()
