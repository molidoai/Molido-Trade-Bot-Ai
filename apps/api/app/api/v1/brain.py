"""Read-only view of the latest DecisionBrain (Brain1 Setup / Brain2 Edge /
Brain3 Survival) verdicts, for the live dashboard panel.

The trading-engine writes these to a small JSON file on the shared
runtime_data volume (see app/live/decision_log.py there); this endpoint just
reads it back. No trading action happens here.
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.models.user import User

router = APIRouter(prefix="/brain", tags=["brain"])

_PATH = Path(os.getenv("BRAIN_DECISIONS_PATH", "/app/data/brain-decisions.json"))


@router.get("/decisions")
async def brain_decisions(_user: User = Depends(require_user)):
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": None, "decisions": []}
    decisions = data.get("decisions", []) if isinstance(data, dict) else []
    return {
        "updated_at": data.get("updated_at") if isinstance(data, dict) else None,
        # newest first
        "decisions": list(reversed(decisions)),
    }
