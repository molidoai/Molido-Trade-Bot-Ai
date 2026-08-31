"""Per-cycle portfolio status snapshot, written to the shared runtime_data
volume so the API/dashboard can show live equity and open positions without
a network hop back into this container (same pattern as decision_log.py).

Written every cycle — including session-closed ones — so the dashboard
stays current around the clock, not just while entries are allowed.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_PATH = Path(os.getenv("PORTFOLIO_STATUS_PATH", "/app/data/portfolio-status.json"))
_LOCK = Lock()


def write_status(
    *,
    path: str | None = None,
    account_id: str = "default",
    account_name: str = "Default",
    snapshot,  # molido_portfolio.models.PortfolioSnapshot
    positions,  # list[molido_portfolio.models.ManagedPosition]
    master_on: bool,
    account_mode: str,
    session_note: str,
    active_sessions: list[str],
) -> None:
    payload = {
        "account_id": account_id,
        "account_name": account_name,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "master_on": bool(master_on),
        "account_mode": account_mode,
        "session_note": session_note,
        "active_sessions": active_sessions,
        "balance": snapshot.balance,
        "equity": snapshot.equity,
        "free_margin": snapshot.free_margin,
        "margin_level": snapshot.margin_level,
        "unrealized_pnl": snapshot.unrealized_pnl,
        "open_positions": snapshot.open_positions,
        "drawdown_pct": snapshot.drawdown_pct,
        "peak_equity": snapshot.peak_equity,
        "positions": [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "side": p.side,
                "volume": p.volume,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "unrealized_pnl": p.unrealized_pnl,
                "swap": p.swap,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                "strategy": p.strategy,
            }
            for p in positions
        ],
    }
    target = Path(path) if path else _PATH
    try:
        with _LOCK:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(target)
    except Exception:
        logger.exception("portfolio status write failed")
