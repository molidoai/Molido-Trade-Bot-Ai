from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult


class RSI(Indicator):
    name = "RSI"

    def __init__(self, period: int = 14):
        super().__init__(period=period)
        self.period = period
        self.required_bars = period + 1

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        n = len(candles)
        results = [IndicatorResult(values={"rsi": None}) for _ in range(n)]
        if n < self.required_bars:
            return results

        changes = [candles[i].close - candles[i - 1].close for i in range(1, n)]
        gains = [max(c, 0.0) for c in changes]
        losses = [max(-c, 0.0) for c in changes]

        avg_gain = sum(gains[:self.period]) / self.period
        avg_loss = sum(losses[:self.period]) / self.period

        def _rsi(g: float, l: float) -> float:
            if l == 0:
                return 100.0
            rs = g / l
            return 100.0 - (100.0 / (1.0 + rs))

        # First RSI at index = period (because changes start at index 1)
        idx = self.period
        results[idx] = IndicatorResult(values={"rsi": _rsi(avg_gain, avg_loss)})

        for i in range(self.period, len(changes)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            results[i + 1] = IndicatorResult(values={"rsi": _rsi(avg_gain, avg_loss)})

        return results
