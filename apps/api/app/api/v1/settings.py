"""Admin-editable runtime settings from the dashboard."""

from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_admin, require_user
from app.models.user import User
from app.services import runtime_settings as rs

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    # trading_account_mode / master_bot_enabled are deliberately NOT here.
    # The trading-engine reads both straight from runtime-settings.json every
    # cycle (see app.live.runner._apply_runtime), so if this endpoint could
    # write them too it would bypass the confirm_token-gated 2-step flow in
    # POST /ops/mode and /ops/live entirely — go live only through /ops/*.
    mt5_login: str | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_path: str | None = None
    mt5_real_login: str | None = None
    mt5_real_password: str | None = None
    mt5_real_server: str | None = None
    mt5_real_path: str | None = None
    symbols: str | None = None
    timeframe: str | None = None
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None
    telegram_allowed_chat_ids: str | None = None
    default_risk_per_trade: float | None = Field(default=None, ge=0.0001, le=0.05)
    max_daily_loss: float | None = Field(default=None, ge=0.001, le=0.2)
    max_drawdown: float | None = Field(default=None, ge=0.001, le=0.5)
    max_open_positions: int | None = Field(default=None, ge=1, le=50)
    # The engine reads both of these every cycle; they were persisted but not
    # settable here, so the dashboard could not change them at all.
    max_weekly_loss: float | None = Field(default=None, ge=0.001, le=0.5)
    max_entries_per_day: int | None = Field(default=None, ge=1, le=100)
    # False (default) = trade any active session; True = London/NY overlap only
    session_overlap_only: bool | None = None
    strategy_names: list[str] | None = None


@router.get("")
async def get_settings(_user: User = Depends(require_user)) -> dict[str, Any]:
    return rs.mask(rs.load())


@router.put("")
async def put_settings(body: SettingsPatch, admin: User = Depends(require_admin)) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    saved = rs.save(payload)
    return {"ok": True, "actor": admin.email, "settings": rs.mask(saved)}
