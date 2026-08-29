"""Operational controls: Master ON/OFF, account mode (DEMO/PROP/REAL)."""

from __future__ import annotations
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Literal

from app.core.config import get_settings, Settings

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


@router.get("/state")
async def ops_state(settings: Settings = Depends(get_settings)):
    return {
        "master_on": _master_on,
        "account_mode": _account_mode or settings.trading_account_mode,
        "default_from_env": settings.trading_account_mode,
        "confirm_real_pending": _confirm_real_pending,
        "live": (_account_mode or settings.trading_account_mode) == "REAL" and _master_on,
    }


@router.post("/master")
async def set_master(body: MasterBody):
    global _master_on
    _master_on = body.enabled
    return {
        "master_on": _master_on,
        "actor": body.actor,
        "message": "Master " + ("ON" if _master_on else "OFF"),
    }


@router.post("/mode")
async def set_mode(body: ModeBody):
    global _account_mode, _confirm_real_pending, _master_on
    _account_mode = body.mode
    _confirm_real_pending = False
    if body.mode == "REAL":
        _master_on = True
    return {
        "account_mode": _account_mode,
        "master_on": _master_on,
        "actor": body.actor,
        "message": f"Mode set to {_account_mode}",
        "live": _account_mode == "REAL" and _master_on,
    }


@router.post("/live")
async def enable_live(actor: str = "dashboard"):
    """Force REAL + master ON."""
    global _account_mode, _master_on, _confirm_real_pending
    _account_mode = "REAL"
    _master_on = True
    _confirm_real_pending = False
    return {
        "account_mode": _account_mode,
        "master_on": _master_on,
        "actor": actor,
        "live": True,
        "message": "LIVE enabled: REAL + master ON",
    }
