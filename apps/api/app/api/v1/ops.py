"""Operational controls: Master ON/OFF, account mode, flatten, engine heartbeat.

Telegram for /flatten, /off (master off), and stale heartbeat is sent only
when telegram_bot_token + chat id exist in runtime-settings.json.
Token is never written to git and never logged.

Master ON/OFF and account mode are persisted to runtime-settings.json (the
same file the live engine polls every cycle), so an API restart never
silently reverts an operator's decision back to the safe env default.

Switching to REAL (or PROP, from a different mode) requires an explicit
confirm_token — this is the 2-step confirmation required by
docs/PRODUCTION_HARDENING.md §3. It is enforced here, not just documented.
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, Settings
from app.api.deps import require_admin, get_current_user_id
from app.db.session import get_db
from app.models.user import User
from app.services.ops_notify import notify as telegram_notify
from app.services import runtime_settings as rs

router = APIRouter(prefix="/ops", tags=["ops"])


async def _engine_or_user(
    x_engine_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    user_id: int | None = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """GET /ops/state and /ops/heartbeat need to be readable both by a
    logged-in dashboard user AND by trading-engine's own polling loop
    (runner.py._poll_ops, which has no user session) -- accept either the
    shared engine token or a real user JWT, never neither."""
    if x_engine_token and settings.engine_internal_token and x_engine_token == settings.engine_internal_token:
        return
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

REAL_CONFIRM_TOKEN = "CONFIRM_REAL"
PROP_CONFIRM_TOKEN = "CONFIRM_PROP"

_rt = rs.load()
_master_on: bool = bool(_rt.get("master_bot_enabled", False))
_account_mode: str = str(_rt.get("trading_account_mode", "DEMO") or "DEMO").upper()
_flatten_seq: int = 0
_engine_pulse_at: datetime | None = None
_stale_notified: bool = False
HEARTBEAT_STALE_SEC = 90.0


def _persist() -> None:
    rs.save({"master_bot_enabled": _master_on, "trading_account_mode": _account_mode})


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


class LiveBody(BaseModel):
    confirm_token: str
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
        "live": mode == "REAL" and _master_on,
        "flatten_seq": _flatten_seq,
        "engine_pulse_at": _engine_pulse_at.isoformat() if _engine_pulse_at else None,
        "engine_alive": alive,
        "engine_stale_seconds": round(age, 1) if age is not None else None,
        "engine_stale_threshold_seconds": HEARTBEAT_STALE_SEC,
    }


@router.get("/state")
async def ops_state(
    settings: Settings = Depends(get_settings),
    _auth: None = Depends(_engine_or_user),
):
    _maybe_notify_dead()
    return _snapshot(settings)


@router.get("/heartbeat")
async def get_heartbeat(
    settings: Settings = Depends(get_settings),
    _auth: None = Depends(_engine_or_user),
):
    _maybe_notify_dead()
    out = _snapshot(settings)
    out["message"] = "engine alive" if out["engine_alive"] else "engine dead or never pulsed"
    return out


@router.post("/heartbeat")
async def post_heartbeat(
    x_engine_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    """Engine pulse. Requires the shared ENGINE_INTERNAL_TOKEN — the
    trading-engine container is the only caller and it is the only other
    holder of this token (injected from the same .env)."""
    if not x_engine_token or x_engine_token != settings.engine_internal_token:
        raise HTTPException(status_code=401, detail="invalid or missing engine token")
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
    _persist()
    out = _snapshot(settings)
    out["actor"] = body.actor or admin.email
    out["message"] = "Master " + ("ON" if _master_on else "OFF")
    telegram_notify(f"Molido master {'ON' if _master_on else 'OFF'} (by {out['actor']})")
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
    """Switch account mode. Moving to REAL always needs confirm_token=CONFIRM_REAL;
    moving into PROP from a different mode needs confirm_token=CONFIRM_PROP.
    Does NOT touch master_on — turning the bot on is a separate, explicit step
    (POST /ops/master) so going live is genuinely two confirmed actions."""
    global _account_mode
    if body.mode == "REAL" and body.confirm_token != REAL_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"REAL mode requires confirm_token={REAL_CONFIRM_TOKEN}",
        )
    if body.mode == "PROP" and _account_mode != "PROP" and body.confirm_token != PROP_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"PROP mode requires confirm_token={PROP_CONFIRM_TOKEN}",
        )
    previous = _account_mode
    _account_mode = body.mode
    _persist()
    out = _snapshot(settings)
    out["actor"] = body.actor or admin.email
    out["message"] = f"Mode set to {_account_mode}"
    if body.mode != previous:
        telegram_notify(f"Molido account mode {previous} → {_account_mode} (by {out['actor']})")
    return out


@router.post("/live")
async def enable_live(
    body: LiveBody,
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """One-call convenience for going live. Still requires confirm_token —
    this is the second confirmed step; POST /ops/mode (REAL) is normally the
    first. Forbidden by docs/PRODUCTION_HARDENING.md to ever happen implicitly
    on deploy, so there is no code path to REAL+master-ON without this token."""
    if body.confirm_token != REAL_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"Going live requires confirm_token={REAL_CONFIRM_TOKEN}",
        )
    global _account_mode, _master_on
    _account_mode = "REAL"
    _master_on = True
    _persist()
    out = _snapshot(settings)
    out["actor"] = body.actor or admin.email
    out["message"] = "LIVE enabled: REAL + master ON"
    telegram_notify(f"Molido LIVE enabled: REAL + master ON (by {out['actor']})")
    return out
