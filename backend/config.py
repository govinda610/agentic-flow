from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path

# .env lives at the repo root, but the backend is launched from backend/ (see start.sh).
# Resolve the env file relative to this file so it loads regardless of the working directory.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _parse_int_list(v) -> list[int]:
    if v is None or v == "":
        return []
    return [int(x.strip()) for x in v.split(",") if x.strip()]


def _parse_str_list(v) -> list[str]:
    if v is None or v == "":
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )

    # LLM
    glm_api_key: Optional[str] = None
    glm_base_url: str = "https://api.z.ai/api/anthropic"
    glm_model: str = "glm-5-turbo"

    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_allowed_users_str: str = ""
    telegram_allowed_users: list[int] = []

    # Database
    database_url: str = "sqlite:///./agentic_flow.db"

    # Security
    api_key_enabled: bool = False
    api_key: str = "change_me_for_production"
    allowed_origins_str: str = "http://localhost:5173"
    allowed_origins: list[str] = ["http://localhost:5173"]

    def model_post_init(self, __context):
        self.telegram_allowed_users = _parse_int_list(self.telegram_allowed_users_str)
        self.allowed_origins = _parse_str_list(self.allowed_origins_str) or ["http://localhost:5173"]

settings = Settings()
