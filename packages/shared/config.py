from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""
    supabase_auth_key: str = ""
    web_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    web_url: str = "http://localhost:3000"
    api_port: int = Field(default=8000, ge=1, le=65535)
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_default_language: Literal["en", "th"] = "en"
    line_default_delivery: Literal["monthly", "digest", "immediate"] = "monthly"

    discord_bot_token: str = ""
    discord_guild_id: str = ""
    discord_alert_channel_id: str = ""
    discord_webhook_url: str = ""
    discord_admin_role_id: str = ""
    discord_ask_channel_id: str = ""

    resend_api_key: str = ""
    alert_email_from: str = ""

    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""

    ransomware_live_base: str = "https://api.ransomware.live/v2"
    cisa_kev_enabled: bool = True
    cisa_kev_url: str = (
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    )
    thaicert_enabled: bool = True
    thaicert_feed_url: str = "https://www.thaicert.or.th/feed/"
    news_rss_urls: list[str] = Field(default_factory=list)
    intel_poll_minutes: int = Field(default=60, ge=15)
    tz_display: str = "Asia/Bangkok"


@lru_cache
def get_settings() -> Settings:
    return Settings()
