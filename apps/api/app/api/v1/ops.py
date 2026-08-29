"""Operational controls: Master ON/OFF, account mode (DEMO/PROP/REAL)."""

from __future__ import annotations
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Literal

from app.core.config import get_settings, Settings
from app.api.deps import require_admin
from app.models.user import User

router = APIRouter(prefix="/ops", tags=["ops"])

_master_on: bool = os.getenv("MASTER_BOT_ENABLED", "true").lower() in ("1", "true", "yes")
_account_mode: str = os.getenv("TRADING_ACCOUNT_MODE", "REAL").upper()
_confirm_real_pending: bool = False


class MasterBody(BaseModel):
    enabled: bool
    actor: str = "dashboard"


class ModeBody(BaseModel):
    mode: Literal["DEMO", "PROP", "REAL"]
    confirm_token: str | None = None
    actor: str = "dashboard"


def _snapshot(settings: Settings) -> dict:
    mode = _account_mode or settings.trading_account_mode
    return {
        "master_on": _master_on,
        "account_mode": mode,
        "default_from_env": settings.trading_account_mode,
        "confirm_real_pending": _confirm_real_pending,
        "live": mode == "REAL" and _master_on,
    }


@router.get("/state")
async def ops_state(settings: Settings = Depends(get_settings)):
    return _snapshot(settings)


@router.post("/master")
async def set_master(
    body: MasterBody,
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    global _master_on
    _master_on = body.enabled
    out = _snapshot(settings)
    out["actor"] = body.actor or admin.email
    out["message"] = "Master " + ("ON" if _master_on else "OFF")
    return out


@router.post("/mode")
async def set_mode(
    body: ModeBody,
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    global _account_mode, _confirm_real_pending, _master_on
    _account_mode = body.mode
    _confirm_real_pending = False
    if body.mode == "REAL":
        _master_on = True
    out = _snapshot(settings)
    out["actor"] = body.actor or admin.email
    out["message"] = f"Mode set to {_account_mode}"
    return out


@router.post("/live")
async def enable_live(
    actor: str = "dashboard",
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    global _account_mode, _master_on, _confirm_real_pending
    _account_mode = "REAL"
    _master_on = True
    _confirm_real_pending = False
    out = _snapshot(settings)
    out["actor"] = actor or admin.email
    out["message"] = "LIVE enabled: REAL + master ON"
    return out
