"""Read-only live portfolio status for the dashboard (positions/performance
pages). trading-engine writes /app/data/portfolio-status.json every cycle
(app/live/status_snapshot.py there); this endpoint just reads it back.
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.models.user import User

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_PATH = Path(os.getenv("PORTFOLIO_STATUS_PATH", "/app/data/portfolio-status.json"))


@router.get("/status")
async def portfolio_status(_user: User = Depends(require_user)):
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"as_of": None, "positions": [], "note": "engine has not written a snapshot yet"}
    except Exception:
        return {"as_of": None, "positions": [], "note": "snapshot unreadable"}
