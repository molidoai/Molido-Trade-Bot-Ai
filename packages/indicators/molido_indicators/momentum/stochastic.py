from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, sma


class Stochastic(Indicator):
    name = "Stochastic"

    def __init__(self, k_period: int = 14, d_period: int = 3):
        super().__init__(k_period=k_period, d_period=d_period)
        self.k_period = k_period
        self.d_period = d_period
        self.required_bars = k_period + d_period

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        n = len(candles)
        raw_k: list[float | None] = [None] * n

        for i in range(self.k_period - 1, n):
            window = candles[i - self.k_period + 1: i + 1]
            highest = max(c.high for c in window)
            lowest = min(c.low for c in window)
            if highest == lowest:
                raw_k[i] = 50.0
            else:
                raw_k[i] = 100.0 * (candles[i].close - lowest) / (highest - lowest)

        # %D = SMA of %K
        k_vals = [v if v is not None else 0.0 for v in raw_k]
        d_vals = sma(k_vals, self.d_period)

        results = []
        for i in range(n):
            results.append(IndicatorResult(values={
                "k": raw_k[i],
                "d": d_vals[i] if raw_k[i] is not None else None,
            }))
        return results
