"""Read-only live portfolio status for the dashboard.

trading-engine writes one snapshot file per account each cycle
(app/live/status_snapshot.py there, named portfolio-status-<account_id>.json).
This endpoint reads them back and aggregates. No trading action here.
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.models.user import User

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_DATA_DIR = Path(os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")).parent
# Pre-multi-account deployments wrote a single unsuffixed file; still read it
# so a dashboard doesn't go blank between the engine and API being upgraded.
_LEGACY_PATH = Path(os.getenv("PORTFOLIO_STATUS_PATH", str(_DATA_DIR / "portfolio-status.json")))


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _load_all() -> list[dict]:
    accounts: list[dict] = []
    for path in sorted(_DATA_DIR.glob("portfolio-status-*.json")):
        data = _read(path)
        if data:
            data.setdefault("account_id", path.stem.replace("portfolio-status-", ""))
            accounts.append(data)
    if not accounts:
        legacy = _read(_LEGACY_PATH)
        if legacy:
            legacy.setdefault("account_id", "default")
            legacy.setdefault("account_name", "Default")
            accounts.append(legacy)
    return accounts


def _totals(accounts: list[dict]) -> dict:
    def total(field: str) -> float:
        return round(sum(float(a.get(field) or 0.0) for a in accounts), 2)

    return {
        "accounts": len(accounts),
        "equity": total("equity"),
        "balance": total("balance"),
        "unrealized_pnl": total("unrealized_pnl"),
        "open_positions": int(sum(int(a.get("open_positions") or 0) for a in accounts)),
        # Any account still trading means the bot as a whole is live.
        "master_on": any(bool(a.get("master_on")) for a in accounts),
    }


@router.get("/status")
async def portfolio_status(_user: User = Depends(require_user)):
    """Aggregate across accounts, plus the flat single-account fields the
    existing dashboard pages already read (taken from the first account) so
    they keep working unchanged."""
    accounts = _load_all()
    if not accounts:
        return {
            "as_of": None,
            "positions": [],
            "accounts": [],
            "totals": _totals([]),
            "note": "engine has not written a snapshot yet",
        }

    primary = accounts[0]
    out = dict(primary)
    out["accounts"] = accounts
    out["totals"] = _totals(accounts)
    # Positions across every account, tagged so the UI can group them.
    out["positions"] = [
        {**p, "account_id": a.get("account_id"), "account_name": a.get("account_name")}
        for a in accounts
        for p in (a.get("positions") or [])
    ]
    out["as_of"] = max((a.get("as_of") or "" for a in accounts), default=None) or None
    return out


@router.get("/accounts")
async def portfolio_accounts(_user: User = Depends(require_user)):
    """One row per account: what it is and how it is doing right now."""
    accounts = _load_all()
    return {
        "count": len(accounts),
        "totals": _totals(accounts),
        "accounts": [
            {
                "account_id": a.get("account_id"),
                "account_name": a.get("account_name"),
                "account_mode": a.get("account_mode"),
                "master_on": a.get("master_on"),
                "as_of": a.get("as_of"),
                "equity": a.get("equity"),
                "balance": a.get("balance"),
                "unrealized_pnl": a.get("unrealized_pnl"),
                "open_positions": a.get("open_positions"),
                "drawdown_pct": a.get("drawdown_pct"),
                "session_note": a.get("session_note"),
            }
            for a in accounts
        ],
    }
