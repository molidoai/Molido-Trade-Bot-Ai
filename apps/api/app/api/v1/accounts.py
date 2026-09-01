"""Manage the trading accounts the engine runs.

The engine reads the "accounts" list from runtime-settings.json every cycle
(app.live.accounts.load_accounts) and supervises one LiveRunner per enabled
entry. Until now the only way to add one was /opt/mt5/setup-account2.sh on the
server, so there was no way to see, disable or remove an account from the
dashboard at all.

Safety rules kept identical to the rest of the ops surface:
  * writes are admin-only;
  * passwords are never returned, and an unchanged mask leaves the stored one
    alone;
  * a new account is always created disabled and in DEMO, so adding one can
    never start live trading as a side effect. Going live stays a separate,
    deliberate step through the confirm-token gates in /ops.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import require_admin, require_user
from app.models.user import User
from app.services import runtime_settings as rs

router = APIRouter(prefix="/accounts", tags=["accounts"])

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MASK = "••••"


class AccountIn(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=64)
    mt5_login: str = Field(min_length=1, max_length=32)
    mt5_password: str = Field(default="", max_length=128)
    mt5_server: str = Field(min_length=1, max_length=64)
    mt5_path: str | None = None
    rpc_host: str | None = None
    rpc_port: int = Field(default=8002, ge=1, le=65535)
    symbols: str | None = None
    timeframe: str | None = None
    strategy_names: list[str] | None = None
    # Prop-challenge floor: the engine refuses to trade below
    # prop_initial_balance * (1 - prop_max_loss_pct). 0 disables it.
    prop_initial_balance: float = Field(default=0.0, ge=0)
    prop_max_loss_pct: float = Field(default=0.10, gt=0, lt=1)


def _accounts(settings: dict) -> list[dict]:
    raw = settings.get("accounts")
    return [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []


def _mask_one(entry: dict) -> dict:
    out = dict(entry)
    val = str(out.get("mt5_password") or "")
    out["mt5_password"] = MASK if val else ""
    out["mt5_password_set"] = bool(val)
    return out


def _persist(accounts: list[dict]) -> None:
    """Write the list back directly. rs.save() only accepts keys present in
    DEFAULTS, and "accounts" deliberately is not one of them."""
    current = rs.load()
    current["accounts"] = accounts
    with rs._LOCK:  # type: ignore[attr-defined]
        rs._ensure_parent()  # type: ignore[attr-defined]
        tmp = rs._PATH.with_suffix(".tmp")  # type: ignore[attr-defined]
        tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
        tmp.replace(rs._PATH)  # type: ignore[attr-defined]


def _implicit_default(settings: dict) -> dict:
    """What the engine synthesises when no explicit list exists."""
    return {
        "id": "default",
        "name": "Account 1",
        "enabled": True,
        "trading_account_mode": settings.get("trading_account_mode", "DEMO"),
        "mt5_login": settings.get("mt5_login") or settings.get("mt5_real_login") or "",
        "mt5_password": settings.get("mt5_password") or settings.get("mt5_real_password") or "",
        "mt5_server": settings.get("mt5_server") or settings.get("mt5_real_server") or "",
        "rpc_port": 8001,
    }


@router.get("")
async def list_accounts(_user: User = Depends(require_user)) -> dict[str, Any]:
    settings = rs.load()
    accounts = _accounts(settings)
    implicit = False
    if not accounts:
        # No explicit list yet: the engine still trades a single account built
        # from the flat mt5_* fields, so report that rather than implying
        # nothing is running.
        accounts = [_implicit_default(settings)]
        implicit = True
    return {"accounts": [_mask_one(a) for a in accounts], "implicit": implicit}


@router.post("")
async def upsert_account(body: AccountIn, admin: User = Depends(require_admin)) -> dict[str, Any]:
    if not _ID_RE.match(body.id):
        raise HTTPException(422, "id must be lowercase letters, digits, '-' or '_'")

    settings = rs.load()
    accounts = _accounts(settings)
    if not accounts:
        # Promote the current single-account settings to entry 1 first, so
        # introducing the list never changes what the running account does.
        accounts = [_implicit_default(settings)]

    existing = next((a for a in accounts if a.get("id") == body.id), None)
    clash = next(
        (a for a in accounts if a.get("id") != body.id and a.get("rpc_port") == body.rpc_port),
        None,
    )
    if clash is not None:
        raise HTTPException(
            409, f"rpc_port {body.rpc_port} is already used by account '{clash.get('id')}'"
        )

    entry = dict(existing or {})
    entry.update(
        {k: v for k, v in body.model_dump(exclude_none=True).items() if k != "mt5_password"}
    )
    # Blank, or the mask returned by a GET, means "leave the stored password".
    if body.mt5_password and body.mt5_password != MASK:
        entry["mt5_password"] = body.mt5_password
    elif existing is None:
        entry["mt5_password"] = ""

    if existing is None:
        # Never enable, and never go live, as a side effect of adding.
        entry["enabled"] = False
        entry["trading_account_mode"] = "DEMO"
    else:
        entry.setdefault("enabled", False)
        entry.setdefault("trading_account_mode", "DEMO")

    accounts = [a for a in accounts if a.get("id") != body.id] + [entry]
    _persist(accounts)
    return {
        "ok": True,
        "actor": admin.email,
        "created": existing is None,
        "account": _mask_one(entry),
        "note": "created disabled and in DEMO" if existing is None else "updated",
    }


@router.post("/{account_id}/enabled")
async def set_enabled(
    account_id: str, on: bool, admin: User = Depends(require_admin)
) -> dict[str, Any]:
    settings = rs.load()
    accounts = _accounts(settings) or [_implicit_default(settings)]
    entry = next((a for a in accounts if a.get("id") == account_id), None)
    if entry is None:
        raise HTTPException(404, f"no account '{account_id}'")
    if on and not (entry.get("mt5_login") and entry.get("mt5_password") and entry.get("mt5_server")):
        raise HTTPException(400, "account is missing login, password or server")
    entry["enabled"] = bool(on)
    _persist(accounts)
    return {"ok": True, "actor": admin.email, "id": account_id, "enabled": bool(on)}


@router.delete("/{account_id}")
async def delete_account(account_id: str, admin: User = Depends(require_admin)) -> dict[str, Any]:
    if account_id == "default":
        raise HTTPException(400, "the default account cannot be removed here")
    settings = rs.load()
    accounts = _accounts(settings)
    if not any(a.get("id") == account_id for a in accounts):
        raise HTTPException(404, f"no account '{account_id}'")
    _persist([a for a in accounts if a.get("id") != account_id])
    return {"ok": True, "actor": admin.email, "removed": account_id}
