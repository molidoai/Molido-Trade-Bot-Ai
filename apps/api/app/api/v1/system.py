"""
System status and health endpoints.
"""

from fastapi import APIRouter, Depends
from app.core.config import get_settings, Settings
from app.schemas.system import HealthResponse, SystemStatus
from app.services import runtime_settings as rs

router = APIRouter()


def _effective(settings: Settings) -> tuple[str, bool]:
    """Master switch and account mode as the trading-engine actually sees them.

    The engine takes both from runtime-settings.json every cycle and only falls
    back to the environment when the file says nothing, so reporting the env
    value here made the dashboard disagree with reality: .env carries
    MASTER_BOT_ENABLED=false while the runtime file says true, and the engine
    was live-trading with master=ON under a dashboard that read "off". A status
    panel that under-reports live trading is the dangerous direction to be
    wrong in, so mirror the engine's own precedence.
    """
    try:
        rt = rs.load() or {}
    except Exception:
        rt = {}
    mode = str(rt.get("trading_account_mode") or settings.trading_account_mode)
    master = rt.get("master_bot_enabled")
    return mode, bool(settings.master_bot_enabled if master is None else master)


async def _probe_db() -> str:
    """Real connectivity check. This used to be the literal string "unknown",
    so the dashboard's Database lamp never reflected anything."""
    try:
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "error"


async def _probe_redis() -> str:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(get_settings().redis_url)
        try:
            await client.ping()
            return "connected"
        finally:
            await client.aclose()
    except Exception:
        return "error"


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)):
    mode, master = _effective(settings)
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        env=settings.app_env,
        account_mode=mode,
        master_bot=master,
    )


@router.get("/system/status", response_model=SystemStatus)
async def system_status(settings: Settings = Depends(get_settings)):
    """
    High-level system status for Dashboard and Telegram.
    """
    mode, master = _effective(settings)
    return SystemStatus(
        account_mode=mode,
        master_bot_enabled=master,
        database=await _probe_db(),
        redis=await _probe_redis(),
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
