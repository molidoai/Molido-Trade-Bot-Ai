from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult


class DonchianChannel(Indicator):
    name = "DonchianChannel"

    def __init__(self, period: int = 20):
        super().__init__(period=period)
        self.period = period
        self.required_bars = period

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        n = len(candles)
        results = []
        for i in range(n):
            if i < self.period - 1:
                results.append(IndicatorResult(values={
                    "upper": None, "lower": None, "middle": None
                }))
                continue
            window = candles[i - self.period + 1: i + 1]
            upper = max(c.high for c in window)
            lower = min(c.low for c in window)
            results.append(IndicatorResult(values={
                "upper": upper,
                "lower": lower,
                "middle": (upper + lower) / 2,
            }))
        return results
