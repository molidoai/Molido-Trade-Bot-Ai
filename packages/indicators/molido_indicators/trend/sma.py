from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, sma


class SMA(Indicator):
    name = "SMA"

    def __init__(self, period: int = 50):
        super().__init__(period=period)
        self.period = period
        self.required_bars = period

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        closes = [c.close for c in candles]
        values = sma(closes, self.period)
        return [IndicatorResult(values={"sma": v}) for v in values]
