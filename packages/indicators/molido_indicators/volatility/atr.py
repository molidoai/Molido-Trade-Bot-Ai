from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, true_range, ema


class ATR(Indicator):
    name = "ATR"

    def __init__(self, period: int = 14):
        super().__init__(period=period)
        self.period = period
        self.required_bars = period

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        tr = true_range(candles)
        atr_vals = ema(tr, self.period)
        return [IndicatorResult(values={"atr": v}) for v in atr_vals]
