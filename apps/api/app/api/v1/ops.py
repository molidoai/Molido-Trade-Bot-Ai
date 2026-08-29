"""Operational controls: Master ON/OFF, flatten, engine heartbeat.

Telegram for /flatten, /off (master off), and stale heartbeat is sent only
when telegram_bot_token + chat id exist in runtime-settings.json.
Token is never written to git and never logged.
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal

from app.core.config import get_settings, Settings
from app.api.deps import require_admin
from app.models.user import User
from app.services.ops_notify import notify as telegram_notify

router = APIRouter(prefix="/ops", tags=["ops"])

_master_on: bool = os.getenv("MASTER_BOT_ENABLED", "true").lower() in ("1", "true", "yes")
_account_mode: str = os.getenv("TRADING_ACCOUNT_MODE", "DEMO").upper()
_confirm_real_pending: bool = False
_flatten_seq: int = 0
_engine_pulse_at: datetime | None = None
_stale_notified: bool = False
HEARTBEAT_STALE_SEC = 90.0


class MasterBody(BaseModel):
    enabled: bool | None = None
    on: bool | None = None
    actor: str = "dashboard"

    def is_on(self) -> bool:
        if self.on is not None:
            return bool(self.on)
        if self.enabled is not None:
            return bool(self.enabled)
        raise ValueError("provide on or enabled")


class ModeBody(BaseModel):
    mode: Literal["DEMO", "PROP", "REAL"]
    confirm_token: str | None = None
    actor: str = "dashboard"


class FlattenBody(BaseModel):
    actor: str = "dashboard"
    reason: str = "dashboard flatten"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stale_seconds(now: datetime | None = None) -> float | None:
    if _engine_pulse_at is None:
        return None
    now = now or _now()
    return (now - _engine_pulse_at).total_seconds()


def _engine_alive(now: datetime | None = None) -> bool:
    age = _stale_seconds(now)
    return age is not None and age <= HEARTBEAT_STALE_SEC


def _maybe_notify_dead() -> None:
    global _stale_notified
    if _engine_alive():
        _stale_notified = False
        return
    if _stale_notified:
        return
    age = _stale_seconds()
    telegram_notify(
        f"Molido engine heartbeat dead (stale {int(age) if age is not None else 'never'}s, threshold {int(HEARTBEAT_STALE_SEC)}s)"
    )
    _stale_notified = True


def _snapshot(settings: Settings) -> dict:
    mode = _account_mode or settings.trading_account_mode
    age = _stale_seconds()
    alive = _engine_alive()
    return {
        "master_on": _master_on,
        "account_mode": mode,
        "default_from_env": settings.trading_account_mode,
        "confirm_real_pending": _confirm_real_pending,
        "live": mode == "REAL" and _master_on,
        "flatten_seq": _flatten_seq,
        "engine_pulse_at": _engine_pulse_at.isoformat() if _engine_pulse_at else None,
        "engine_alive": alive,
        "engine_stale_seconds": round(age, 1) if age is not None else None,
        "engine_stale_threshold_seconds": HEARTBEAT_STALE_SEC,
    }


@router.get("/state")
async def ops_state(settings: Settings = Depends(get_settings)):
    _maybe_notify_dead()
    return _snapshot(settings)


@router.get("/heartbeat")
async def get_heartbeat(settings: Settings = Depends(get_settings)):
    _maybe_notify_dead()
    out = _snapshot(settings)
    out["message"] = "engine alive" if out["engine_alive"] else "engine dead or never pulsed"
    return out


@router.post("/heartbeat")
async def post_heartbeat():
    """Engine pulse. Internal docker network; no token in git."""
    global _engine_pulse_at, _stale_notified
    _engine_pulse_at = _now()
    _stale_notified = False
    return {
        "ok": True,
        "engine_pulse_at": _engine_pulse_at.isoformat(),
        "engine_alive": True,
    }


@router.post("/master")
async def set_master(
    body: MasterBody,
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    global _master_on
    try:
        _master_on = body.is_on()
    except ValueError:
        raise HTTPException(status_code=400, detail="body must include on or enabled")
    out = _snapshot(settings)
    out["actor"] = body.actor or admin.email
    out["message"] = "Master " + ("ON" if _master_on else "OFF")
    if not _master_on:
        telegram_notify("Molido master OFF")
    return out


@router.post("/flatten")
async def flatten_all(
    body: FlattenBody | None = None,
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """Ask the live engine to close every open position. Engine polls flatten_seq."""
    global _flatten_seq
    _flatten_seq += 1
    actor = (body.actor if body else None) or admin.email
    reason = body.reason if body else "dashboard flatten"
    out = _snapshot(settings)
    out["actor"] = actor
    out["message"] = "flatten requested"
    out["reason"] = reason
    telegram_notify(f"Molido flatten requested ({reason})")
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
