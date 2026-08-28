from pydantic import BaseModel
from typing import Literal


class HealthResponse(BaseModel):
    status: str
    app: str
    env: str
    account_mode: Literal["DEMO", "PROP", "REAL"]
    master_bot: bool


class SystemStatus(BaseModel):
    account_mode: Literal["DEMO", "PROP", "REAL"]
    master_bot_enabled: bool
    database: str
    redis: str
    risk_engine: str
    circuit_breaker: str
    trading_hours_ok: bool
    news_blackout: bool
    last_sync: str | None = None
    # Prop-specific (only meaningful when account_mode == PROP)
    prop_firm_name: str | None = None
    prop_phase: str | None = None
    prop_max_daily_loss_pct: float | None = None
    prop_max_total_drawdown_pct: float | None = None
