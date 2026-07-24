from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WECHATAGENT_", env_file=".env", extra="ignore")

    app_name: str = "微信关系记忆"
    database_url: str = "sqlite:///./data/wechatagent.db"
    connector: str = "synthetic"
    wx_command: str = "wx"
    selected_account_id: str | None = None
    sync_overlap_seconds: int = 300
    auto_sync_enabled: bool = True
    auto_sync_interval_seconds: int = 300
    allowed_origin: str = "http://127.0.0.1:5173"

    def ensure_data_directory(self) -> None:
        if self.database_url.startswith("sqlite:///./"):
            Path(self.database_url.removeprefix("sqlite:///./")).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_directory()
    return settings
