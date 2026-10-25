from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", extra="ignore", case_sensitive=False
    )

    database_url: str = "sqlite:///./freshflow.db"
    admin_api_key: str = Field(min_length=8)
    staff_api_key: str = Field(min_length=8)
    service_api_key: str = Field(min_length=8)
    cors_origins: list[str] = ["http://localhost:5173"]
