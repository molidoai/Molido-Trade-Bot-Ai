"""Timeframe-aware scaling for volatility thresholds.

The dead_atr_ratio defaults (0.0003) were calibrated against M15 bars. ATR
scales roughly with the square root of bar duration, so applying an M15
threshold unchanged to M5 bars rejects perfectly normal markets: measured
2026-08-31 during the London/NY overlap, GBPUSD read 0.000431 on M15 (fine)
but 0.000252 on M5 (below the threshold) -- the same market, same instant.

That mattered because resolve_trade_timeframe() deliberately switches to M5
during the London/NY overlap, so every major FX pair was being auto-vetoed
as a "dead market" precisely during the window the bot is meant to be most
active in. Only XAUUSD, volatile enough to clear the M15 threshold on M5
bars, ever got through.

Scaling the threshold by sqrt(bar_minutes / 15) keeps "dead" meaning the
same thing on every timeframe.
"""

from __future__ import annotations
from math import sqrt
from typing import Any

# Bar duration in minutes, keyed by TimeFrame.value (see molido_shared.types).
TF_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# The timeframe the default thresholds were tuned on.
BASELINE_TF_MINUTES = 15


def timeframe_minutes(timeframe: Any) -> int | None:
    """Bar duration in minutes for a TimeFrame, its .value, or a raw string.
    None when unrecognised, so callers can fall back to unscaled behavior."""
    if timeframe is None:
        return None
    if isinstance(timeframe, int):
        return timeframe or None
    value = getattr(timeframe, "value", timeframe)
    return TF_MINUTES.get(str(value).strip().lower())


def scale_atr_threshold(base: float, timeframe: Any) -> float:
    """Scale an M15-calibrated ATR ratio threshold to `timeframe`.

    Unknown/None timeframe returns `base` unchanged -- callers keep the old
    behavior rather than silently loosening a risk gate on bad input.
    """
    mins = timeframe_minutes(timeframe)
    if not mins or mins == BASELINE_TF_MINUTES:
        return base
    return base * sqrt(mins / BASELINE_TF_MINUTES)
