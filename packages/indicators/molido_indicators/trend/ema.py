from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, ema


class EMA(Indicator):
    name = "EMA"

    def __init__(self, period: int = 21):
        super().__init__(period=period)
        self.period = period
        self.required_bars = period

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        closes = [c.close for c in candles]
        values = ema(closes, self.period)
        return [IndicatorResult(values={"ema": v}) for v in values]


class MultiEMA(Indicator):
    """Common set: EMA 9 / 21 / 50 / 200."""
    name = "MultiEMA"

    def __init__(self, periods: list[int] | None = None):
        periods = periods or [9, 21, 50, 200]
        super().__init__(periods=periods)
        self.periods = periods
        self.required_bars = max(periods)

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        closes = [c.close for c in candles]
        series = {p: ema(closes, p) for p in self.periods}
        results = []
        for i in range(len(candles)):
            results.append(IndicatorResult(
                values={f"ema_{p}": series[p][i] for p in self.periods}
            ))
        return results
