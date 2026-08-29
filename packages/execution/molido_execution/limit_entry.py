"""Limit-entry helpers. New entries are LIMIT at bid (buy) / ask (sell)."""

from __future__ import annotations
from typing import Any


def entry_limit_price(side: str, tick: Any) -> float | None:
    """Buy limit at bid, sell limit at ask. None if no book."""
    if tick is None:
        return None
    s = str(side).upper()
    if s == "BUY":
        bid = getattr(tick, "bid", None)
        return float(bid) if bid is not None else None
    if s == "SELL":
        ask = getattr(tick, "ask", None)
        return float(ask) if ask is not None else None
    return None


def is_exit_side(side: str, reduce_only: bool = False) -> bool:
    return reduce_only or str(side).upper() in ("EXIT", "CLOSE", "FLATTEN")
