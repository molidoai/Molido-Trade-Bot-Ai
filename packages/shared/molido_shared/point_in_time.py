"""Point-in-time bar reads. The only sanctioned way to use history for a decision."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Sequence

from molido_shared.types import Candle, TimeFrame

_BAR_LEN = {
    TimeFrame.M1: timedelta(minutes=1),
    TimeFrame.M5: timedelta(minutes=5),
    TimeFrame.M15: timedelta(minutes=15),
    TimeFrame.H1: timedelta(hours=1),
    TimeFrame.H4: timedelta(hours=4),
    TimeFrame.D1: timedelta(days=1),
}


class InsufficientDataError(ValueError):
    pass


def bar_close_time(candle: Candle) -> datetime:
    delta = _BAR_LEN.get(candle.timeframe, timedelta(minutes=15))
    t = candle.open_time
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t + delta


def closed_bars(
    candles: Sequence[Candle],
    as_of: datetime | None = None,
    min_bars: int = 30,
) -> list[Candle]:
    """Drop any bar that has not closed at or before as_of (no lookahead)."""
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    out: list[Candle] = []
    for c in candles:
        close_at = bar_close_time(c)
        if close_at.tzinfo is None:
            close_at = close_at.replace(tzinfo=timezone.utc)
        if close_at <= as_of and (c.is_closed or True):
            if close_at <= as_of:
                out.append(c)
    if len(out) < min_bars:
        raise InsufficientDataError(f"need {min_bars} closed bars, got {len(out)}")
    return out
