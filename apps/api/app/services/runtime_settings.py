"""Runtime settings stored on the server, never in git.
Editable from the dashboard. Defaults are DEMO + tight risk for the trial week.
symbols/timeframe empty or 'auto' → brain universe picker.
"""

from __future__ import annotations
import json
import os
import secrets
from pathlib import Path
from threading import Lock

_PATH = Path(os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json"))
_LOCK = Lock()

DEFAULTS = {
    "trading_account_mode": "DEMO",
    "master_bot_enabled": False,
    "mt5_login": "",
    "mt5_password": "",
    "mt5_server": "",
    "mt5_path": "",
    "mt5_real_login": "",
    "mt5_real_password": "",
    "mt5_real_server": "",
    "mt5_real_path": "",
    "symbols": "auto",
    "timeframe": "AUTO",
    "telegram_bot_token": "",
    "telegram_admin_chat_id": "",
    "telegram_allowed_chat_ids": "",
    "default_risk_per_trade": 0.0025,
    "max_daily_loss": 0.02,
    "max_weekly_loss": 0.06,
    "max_drawdown": 0.04,
    "max_open_positions": 3,
    "max_entries_per_day": 4,
    "session_overlap_only": False,
    "strategy_names": ["TrendFollowing"],
}

SECRET_KEYS = {
    "mt5_password",
    "mt5_real_password",
    "telegram_bot_token",
}


def _ensure_parent() -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    with _LOCK:
        if not _PATH.exists():
            data = dict(DEFAULTS)
            _ensure_parent()
            _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        try:
            data = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        out = dict(DEFAULTS)
        out.update({k: v for k, v in data.items() if k in DEFAULTS})
        if not out.get("mt5_login") and out.get("mt5_real_login"):
            out["mt5_login"] = out["mt5_real_login"]
        if not out.get("mt5_password") and out.get("mt5_real_password"):
            out["mt5_password"] = out["mt5_real_password"]
        if not out.get("mt5_server") and out.get("mt5_real_server"):
            out["mt5_server"] = out["mt5_real_server"]
        if not out.get("mt5_path") and out.get("mt5_real_path"):
            out["mt5_path"] = out["mt5_real_path"]
        return out


def save(data: dict) -> dict:
    current = load()
    for key, value in data.items():
        if key not in DEFAULTS:
            continue
        if key in SECRET_KEYS and (value is None or value == "" or value == "••••"):
            continue
        current[key] = value
        if key == "mt5_login":
            current["mt5_real_login"] = value
        if key == "mt5_password":
            current["mt5_real_password"] = value
        if key == "mt5_server":
            current["mt5_real_server"] = value
        if key == "mt5_path":
            current["mt5_real_path"] = value
    with _LOCK:
        _ensure_parent()
        tmp = _PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
        tmp.replace(_PATH)
    return current


def mask(data: dict) -> dict:
    out = dict(data)
    for key in SECRET_KEYS:
        val = str(out.get(key) or "")
        out[key + "_set"] = bool(val)
        out[key] = "••••" if val else ""
    return out


def generate_secret_key() -> str:
    return secrets.token_hex(32)
