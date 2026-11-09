"""Application configuration.

All values come from environment variables, loaded from the project-root
``.env`` file. A ``Settings`` instance is created at import time so a missing
required key fails fast (this is the only import-time side effect of ``core``).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- required: Rebecca panel ---
    rebecca_base_url: str
    rebecca_api_key: str

    # --- required: shared storage ---
    db_path: str
    receipts_dir: str
    tz: str = "UTC"
    log_level: str = "INFO"

    # --- optional: Rebecca service assignment (Marzban requires it on create) ---
    rebecca_service_id: int = 1

    # --- pricing (Toman) ---
    price_per_gb_toman: int = 4000
    bulk_threshold_gb: int = 50
    bulk_discount_percent: int = 10

    # --- payment card shown in the user bot ---
    payment_card_number: str = "6037998169174314"
    payment_card_holder: str = "Mohsen Khodaparast"

    # --- referral bonus ---
    referral_bonus_percent: float = 5.0

    # --- optional: notifications / AI ---
    manager_group_id: Optional[int] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_max_tokens: int = 600
    llm_timeout_seconds: float = 45.0
    llm_daily_message_limit: int = 1000

    # --- optional: consumed by the bots, not required by core ---
    user_bot_token: Optional[str] = None
    manager_bot_token: Optional[str] = None
    manager_ids: Optional[str] = Field(default=None, description="Comma-separated admin ids")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def manager_id_list(self) -> list[int]:
        if not self.manager_ids:
            return []
        return [int(part) for part in self.manager_ids.replace(" ", "").split(",") if part]

    @property
    def receipts_path(self) -> Path:
        return Path(self.receipts_dir)

    @property
    def db_file(self) -> Path:
        return Path(self.db_path)

    @property
    def rebecca_base(self) -> str:
        return self.rebecca_base_url.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Fail fast at import time if a required key is missing.
settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "ROOT_DIR"]
