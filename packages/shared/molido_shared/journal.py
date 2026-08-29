"""Append-only JSONL trade journal. Never invents prices."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def default_journal_path() -> str:
    rt = os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")
    d = os.path.dirname(rt) or "/app/data"
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = "/tmp"
    return os.path.join(d, "journal.jsonl")


class TradeJournal:
    def __init__(self, path: str | None = None):
        self.path = path or default_journal_path()
        self._open: dict[str, dict[str, Any]] = {}

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        for k, v in fields.items():
            if v is not None:
                rec[k] = v
        line = json.dumps(rec, default=str)
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        ticket = rec.get("ticket")
        if event in ("fill", "accept") and ticket is not None:
            self._open[str(ticket)] = {
                "mae": rec.get("mae", 0.0),
                "mfe": rec.get("mfe", 0.0),
                "entry": rec.get("entry"),
                "side": rec.get("side"),
            }
        if event in ("close", "flatten", "exit") and ticket is not None:
            self._open.pop(str(ticket), None)
        return rec

    def update_mae_mfe(
        self,
        ticket: str | int,
        *,
        price: float | None,
        entry: float | None,
        side: str | None,
        stop_distance: float | None,
    ) -> dict[str, Any] | None:
        """Update open-ticket MAE/MFE from a real price. Skip if price unknown."""
        if price is None or entry is None or not stop_distance:
            return None
        st = self._open.setdefault(str(ticket), {"mae": 0.0, "mfe": 0.0})
        direction = 1.0 if str(side or "").upper() == "BUY" else -1.0
        r = (float(price) - float(entry)) * direction / float(stop_distance)
        st["mae"] = min(float(st.get("mae", 0.0)), r)
        st["mfe"] = max(float(st.get("mfe", 0.0)), r)
        st["entry"] = entry
        st["side"] = side
        st["last_price"] = price
        return self.append(
            "open_mark",
            ticket=str(ticket),
            price=price,
            mae=round(st["mae"], 4),
            mfe=round(st["mfe"], 4),
        )

    def last_closed_r(self, n: int = 20) -> list[float]:
        rows = self._read()
        out: list[float] = []
        for rec in reversed(rows):
            if rec.get("event") not in ("close", "exit", "flatten"):
                continue
            r = rec.get("r_multiple")
            if r is None:
                r = rec.get("r")
            if r is None:
                continue
            try:
                out.append(float(r))
            except (TypeError, ValueError):
                continue
            if len(out) >= n:
                break
        out.reverse()
        return out

    def journal_stats(self, n: int = 20) -> dict[str, float | int] | None:
        rs = self.last_closed_r(n)
        if not rs:
            return None
        return {"mean_r": sum(rs) / len(rs), "n": len(rs)}

    def _read(self) -> list[dict[str, Any]]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                rows = []
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                return rows
        except FileNotFoundError:
            return []
