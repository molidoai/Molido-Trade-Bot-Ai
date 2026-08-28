"""
Central configuration for Molido Trade Bot AI.
All settings are loaded from environment variables.
No secrets are hardcoded.
"""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Molido Trade Bot AI"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = Field(..., min_length=32)
    api_prefix: str = "/api/v1"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "molido"
    postgres_password: str = Field(..., min_length=8)
    postgres_db: str = "molido_trading"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0

    # Trading Mode (Safety critical)
    trading_account_mode: Literal["DEMO", "REAL"] = "DEMO"
    master_bot_enabled: bool = False  # MASTER ON/OFF – default OFF

    # MT5 DEMO
    mt5_demo_login: int | None = None
    mt5_demo_password: str | None = None
    mt5_demo_server: str | None = None
    mt5_demo_path: str | None = None

    # MT5 REAL (must remain empty until explicit activation)
    mt5_real_login: int | None = None
    mt5_real_password: str | None = None
    mt5_real_server: str | None = None
    mt5_real_path: str | None = None

    # Telegram
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None
    telegram_allowed_chat_ids: str = ""

    # Risk defaults
    default_risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_drawdown: float = 0.05
    max_open_positions: int = 5

    # Observability
    prometheus_enabled: bool = True
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_real_account(self) -> bool:
        return self.trading_account_mode == "REAL"

    @field_validator("trading_account_mode")
    @classmethod
    def force_demo_by_default(cls, v: str) -> str:
        # Extra safety: never allow REAL unless explicitly set
        if v not in ("DEMO", "REAL"):
            return "DEMO"
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
