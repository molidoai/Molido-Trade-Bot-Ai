"""
System status and health endpoints.
"""

from fastapi import APIRouter, Depends
from app.core.config import get_settings, Settings
from app.schemas.system import HealthResponse, SystemStatus

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)):
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        env=settings.app_env,
        account_mode=settings.trading_account_mode,
        master_bot=settings.master_bot_enabled,
    )


@router.get("/system/status", response_model=SystemStatus)
async def system_status(settings: Settings = Depends(get_settings)):
    """
    High-level system status for Dashboard and Telegram.
    """
    return SystemStatus(
        account_mode=settings.trading_account_mode,
        master_bot_enabled=settings.master_bot_enabled,
        database="unknown",
        redis="unknown",
        risk_engine="ready",
        circuit_breaker="inactive",
        trading_hours_ok=True,
        news_blackout=False,
        last_sync=None,
        prop_firm_name=settings.prop_firm_name if settings.is_prop_account else None,
        prop_phase=settings.prop_phase if settings.is_prop_account else None,
        prop_max_daily_loss_pct=settings.prop_max_daily_loss_pct if settings.is_prop_account else None,
        prop_max_total_drawdown_pct=settings.prop_max_total_drawdown_pct if settings.is_prop_account else None,
    )
