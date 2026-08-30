"""
Base classes for the Indicator Engine.
All indicators are pure functions / classes that only look at past + current data
(no look-ahead bias).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from molido_shared.types import Candle


@dataclass
class IndicatorResult:
    """Standard output of any indicator for a single bar."""
    values: dict[str, float | None] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: float | None = None) -> float | None:
        return self.values.get(key, default)


class Indicator(ABC):
    """
    Abstract indicator.
    - `compute` receives a sequence of candles (oldest → newest)
    - Must only use data up to index i when producing result for bar i
    - Deterministic: same input → same output
    """

    name: str = "base"
    required_bars: int = 1  # minimum history needed before producing valid values

    def __init__(self, **params: Any):
        self.params = params
        self.enabled: bool = True

    @abstractmethod
    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        """
        Return one IndicatorResult per candle (same length as input).
        Early bars that lack enough history should contain None values.
        """
        ...

    def last(self, candles: Sequence[Candle]) -> IndicatorResult | None:
        """Convenience: compute and return only the latest result."""
        if not candles:
            return None
        results = self.compute(candles)
        return results[-1] if results else None


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple Moving Average – pure Python, no look-ahead."""
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Exponential Moving Average."""
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1)
    # Seed with SMA
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def true_range(candles: Sequence[Candle]) -> list[float]:
    """True Range series."""
    tr: list[float] = []
    for i, c in enumerate(candles):
        if i == 0:
            tr.append(c.high - c.low)
        else:
            prev_close = candles[i - 1].close
            tr.append(max(
                c.high - c.low,
                abs(c.high - prev_close),
                abs(c.low - prev_close),
            ))
    return tr
