"""Rolling log of the latest DecisionBrain verdicts (Brain1/2/3), written to
the shared runtime_data volume so the API/dashboard can read them without a
network hop back into the trading-engine container.

Not a trade journal (see molido_shared.journal.TradeJournal for that) — this
is a small, bounded ring buffer purely for the live "what are the brains
seeing right now" dashboard panel.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_PATH = Path(os.getenv("BRAIN_DECISIONS_PATH", "/app/data/brain-decisions.json"))
_LOCK = Lock()
_MAX_ENTRIES = 30


def record_decision(
    *,
    symbol: str,
    side: str | None,
    allow: bool,
    size_mult: float | None,
    p_win: float | None,
    expected_r: float | None,
    skipped_reason: str | None,
    brains: list[dict],
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side,
        "allow": bool(allow),
        "size_mult": size_mult,
        "p_win": p_win,
        "expected_r": expected_r,
        "skipped_reason": skipped_reason,
        "brains": brains,
    }
    try:
        with _LOCK:
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            try:
                existing = json.loads(_PATH.read_text(encoding="utf-8"))
                entries = existing.get("decisions", []) if isinstance(existing, dict) else []
            except Exception:
                entries = []
            entries.append(entry)
            entries = entries[-_MAX_ENTRIES:]
            tmp = _PATH.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"updated_at": entry["ts"], "decisions": entries}, indent=2),
                encoding="utf-8",
            )
            tmp.replace(_PATH)
    except Exception:
        logger.exception("decision log write failed")
