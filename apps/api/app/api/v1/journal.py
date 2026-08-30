"""Read-only view of the trade journal (molido_shared.journal.TradeJournal),
for the dashboard journal/orders pages. The file lives on the same shared
runtime_data volume trading-engine writes to -- this endpoint only reads it.
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.models.user import User

router = APIRouter(prefix="/journal", tags=["journal"])

_PATH = Path(os.getenv("JOURNAL_PATH", "/app/data/journal.jsonl"))
_MAX_RETURN = 200


@router.get("/recent")
async def recent_entries(_user: User = Depends(require_user)):
    if not _PATH.exists():
        return {"count": 0, "entries": []}
    entries: list[dict] = []
    try:
        lines = _PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return {"count": 0, "entries": []}
    for line in lines[-_MAX_RETURN:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    entries.reverse()  # newest first

    closed_r = [
        float(e["r_multiple"]) for e in entries
        if e.get("event") in ("close", "exit", "flatten") and e.get("r_multiple") is not None
    ]
    wins = sum(1 for r in closed_r if r > 0)
    stats = None
    if closed_r:
        stats = {
            "n": len(closed_r),
            "win_rate": round(wins / len(closed_r), 4),
            "mean_r": round(sum(closed_r) / len(closed_r), 4),
            "sum_r": round(sum(closed_r), 4),
        }

    return {"count": len(entries), "entries": entries, "stats": stats}
