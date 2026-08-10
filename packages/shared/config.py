from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""

    discord_bot_token: str = ""
    discord_guild_id: str = ""
    discord_alert_channel_id: str = ""
    discord_webhook_url: str = ""
    discord_admin_role_id: str = ""

    resend_api_key: str = ""
    alert_email_from: str = ""

    llm_api_key: str = ""
    llm_model: str = ""

    ransomware_live_base: str = "https://api.ransomware.live/v2"
    tz_display: str = "Asia/Bangkok"


@lru_cache
def get_settings() -> Settings:
    return Settings()
