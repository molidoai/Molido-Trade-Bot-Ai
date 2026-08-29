"""Admin-editable runtime settings (MT5, telegram, risk, live mode)."""

from __future__ import annotations
from typing import Any, Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_admin, require_user
from app.models.user import User
from app.services import runtime_settings as rs

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    trading_account_mode: Literal["DEMO", "PROP", "REAL"] | None = None
    master_bot_enabled: bool | None = None
    mt5_real_login: str | None = None
    mt5_real_password: str | None = None
    mt5_real_server: str | None = None
    mt5_real_path: str | None = None
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None
    telegram_allowed_chat_ids: str | None = None
    default_risk_per_trade: float | None = Field(default=None, ge=0.0001, le=0.05)
    max_daily_loss: float | None = Field(default=None, ge=0.001, le=0.2)
    max_drawdown: float | None = Field(default=None, ge=0.001, le=0.5)
    max_open_positions: int | None = Field(default=None, ge=1, le=50)


@router.get("")
async def get_settings(_user: User = Depends(require_user)) -> dict[str, Any]:
    return rs.mask(rs.load())


@router.put("")
async def put_settings(body: SettingsPatch, admin: User = Depends(require_admin)) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    saved = rs.save(payload)
    return {"ok": True, "actor": admin.email, "settings": rs.mask(saved)}
