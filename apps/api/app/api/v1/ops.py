"""Operational controls: Master ON/OFF, account mode (DEMO/PROP/REAL)."""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Literal

from app.core.config import get_settings, Settings

router = APIRouter(prefix="/ops", tags=["ops"])

# Process-local store (replace with Redis-backed MasterSwitchStore in deploy)
_master_on: bool = False
_account_mode: str = "DEMO"
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
    if body.mode == "REAL":
        if body.confirm_token != "CONFIRM_REAL":
            _confirm_real_pending = True
            raise HTTPException(
                status_code=400,
                detail="REAL requires confirm_token=CONFIRM_REAL (two-step)",
            )
        _confirm_real_pending = False
        # Safety: turning REAL does not auto-enable master
        _master_on = False
    if body.mode == "PROP" and body.confirm_token not in (None, "CONFIRM_PROP"):
        if body.confirm_token != "CONFIRM_PROP":
            raise HTTPException(status_code=400, detail="PROP requires confirm_token=CONFIRM_PROP")
    _account_mode = body.mode
    return {
        "account_mode": _account_mode,
        "master_on": _master_on,
        "actor": body.actor,
        "message": f"Mode set to {_account_mode}",
    }
