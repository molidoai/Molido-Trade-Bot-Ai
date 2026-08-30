"""Read-only view of incoming TradingView webhook alerts, for the dashboard.

The webhook receiver itself (webhooks/tv_hook.py on the VPS host, outside
Docker -- systemd service molido-tv-hook) only validates the token and
appends the raw POST body to a JSONL log; it does not touch the trading
pipeline. This endpoint just reads that log back. No trading action here.
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.models.user import User

router = APIRouter(prefix="/tv-alerts", tags=["tv-alerts"])

_PATH = Path(os.getenv("TV_ALERTS_LOG_PATH", "/app/tv-logs/tv-alerts.jsonl"))
_MAX_RETURN = 50


@router.get("/recent")
async def recent_alerts(_user: User = Depends(require_user)):
    if not _PATH.exists():
        return {"count": 0, "alerts": []}
    alerts: list[dict] = []
    try:
        lines = _PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return {"count": 0, "alerts": []}
    for line in lines[-_MAX_RETURN:]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        body = rec.get("body")
        parsed_body = body
        if isinstance(body, str):
            try:
                parsed_body = json.loads(body)
            except Exception:
                parsed_body = body
        alerts.append({"ts": rec.get("ts"), "body": parsed_body})
    alerts.reverse()  # newest first
    return {"count": len(alerts), "alerts": alerts}
