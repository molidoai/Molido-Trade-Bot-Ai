"""Live trading state, read from the shared runtime_data volume.

The bot runs in its own container with no link to the engine, and BotState was
a plain dataclass nobody ever populated -- so /status, /balance and /positions
answered with its zero defaults no matter what the account was doing. The
engine writes its snapshot, journal and brain votes to the same volume the bot
mounts read-only, so read them from there.

Everything here is defensive: a missing or half-written file must degrade to
"unknown", never raise inside a command handler.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

DATA_DIR = os.path.dirname(
    os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")
) or "/app/data"

TEHRAN_OFFSET_HOURS = 3.5


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def settings() -> dict:
    data = _read_json(os.path.join(DATA_DIR, "runtime-settings.json"))
    return data if isinstance(data, dict) else {}


def account_ids() -> list[str]:
    accounts = settings().get("accounts")
    if isinstance(accounts, list):
        ids = [str(a.get("id")) for a in accounts if isinstance(a, dict) and a.get("id")]
        if ids:
            return ids
    return ["default"]


def portfolio(account_id: str = "default") -> dict:
    for name in (f"portfolio-status-{account_id}.json", "portfolio-status.json"):
        data = _read_json(os.path.join(DATA_DIR, name))
        if isinstance(data, dict):
            return data
    return {}


def all_portfolios() -> list[dict]:
    out = []
    for aid in account_ids():
        p = portfolio(aid)
        if p:
            p.setdefault("account_id", aid)
            out.append(p)
    return out


def journal_lines(account_id: str = "default", limit: int = 400) -> list[dict]:
    for name in (f"journal-{account_id}.jsonl", "journal.jsonl"):
        path = os.path.join(DATA_DIR, name)
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()[-limit:]
        except Exception:
            continue
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        if out:
            return out
    return []


def brain_decisions(account_id: str = "default", limit: int = 5) -> list[dict]:
    for name in (f"brain-decisions-{account_id}.json", "brain-decisions.json"):
        data = _read_json(os.path.join(DATA_DIR, name))
        if isinstance(data, dict):
            ds = data.get("decisions")
            if isinstance(ds, list):
                return ds[-limit:]
    return []


def tehran(ts: str | None) -> str:
    """Format a UTC ISO timestamp in Tehran time."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = dt.timestamp() + TEHRAN_OFFSET_HOURS * 3600
        return datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%H:%M:%S")
    except Exception:
        return "—"


def age_seconds(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None


def money(v: Any, digits: int = 2) -> str:
    try:
        return f"{float(v):,.{digits}f}"
    except Exception:
        return "—"


def blockers(account_id: str = "default", limit: int = 400) -> list[tuple[str, int]]:
    """Why entries are not happening, most common first."""
    counts: dict[str, int] = {}
    total = 0
    for d in journal_lines(account_id, limit):
        event = d.get("event")
        if event == "open_mark":
            continue
        reason = str(d.get("reason") or "")
        total += 1
        if event in ("accept", "fill"):
            key = "معامله انجام شد"
        elif reason == "HOLD":
            key = "ستاپ معتبری نیست"
        elif "drifted" in reason:
            key = "قیمت از سیگنال دور شده"
        elif "H1 filter" in reason:
            key = "وتوی مغز ۱: خلاف روند H1"
        elif "ATR dead" in reason:
            key = "وتوی مغز ۳: نوسان بسیار کم"
        elif event == "veto":
            key = "وتوی مغزها"
        elif "TradingHours" in reason:
            key = "خارج از ساعات معاملاتی"
        elif "Master bot is OFF" in reason:
            key = "مستر خاموش است"
        else:
            key = reason[:38] or str(event)
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
