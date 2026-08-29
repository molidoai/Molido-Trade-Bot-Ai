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

    app_name: str = "Molido Trade Bot AI"
    app_env: Literal["development", "staging", "production"] = "production"
    debug: bool = False
    secret_key: str = Field(..., min_length=32)
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "molido"
    postgres_password: str = Field(..., min_length=8)
    postgres_db: str = "molido_trading"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0

    # Live is the intended mode. Operator asked to keep REAL + master ON.
    trading_account_mode: Literal["DEMO", "PROP", "REAL"] = "REAL"
    master_bot_enabled: bool = True

    mt5_demo_login: int | None = None
    mt5_demo_password: str | None = None
    mt5_demo_server: str | None = None
    mt5_demo_path: str | None = None

    mt5_prop_login: int | None = None
    mt5_prop_password: str | None = None
    mt5_prop_server: str | None = None
    mt5_prop_path: str | None = None
    prop_firm_name: str | None = None
    prop_phase: str | None = None
    prop_account_size: float | None = None
    prop_max_daily_loss_pct: float = 5.0
    prop_max_total_drawdown_pct: float = 10.0
    prop_profit_target_pct: float | None = None

    mt5_real_login: int | None = None
    mt5_real_password: str | None = None
    mt5_real_server: str | None = None
    mt5_real_path: str | None = None

    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None
    telegram_allowed_chat_ids: str = ""

    default_risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_drawdown: float = 0.05
    max_open_positions: int = 5

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

    @property
    def is_prop_account(self) -> bool:
        return self.trading_account_mode == "PROP"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_max_daily_loss(self) -> float:
        if self.is_prop_account and self.prop_max_daily_loss_pct:
            return self.prop_max_daily_loss_pct / 100.0
        return self.max_daily_loss

    @property
    def effective_max_drawdown(self) -> float:
        if self.is_prop_account and self.prop_max_total_drawdown_pct:
            return self.prop_max_total_drawdown_pct / 100.0
        return self.max_drawdown

    @field_validator("trading_account_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        mode = (v or "REAL").upper()
        if mode not in ("DEMO", "PROP", "REAL"):
            return "REAL"
        return mode


@lru_cache
def get_settings() -> Settings:
    return Settings()
