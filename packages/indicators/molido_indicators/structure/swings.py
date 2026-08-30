from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult


class SwingPoints(Indicator):
    """
    Detect swing highs and swing lows with a simple fractal / pivot method.
    lookback = number of bars on each side.
    """
    name = "SwingPoints"

    def __init__(self, lookback: int = 3):
        super().__init__(lookback=lookback)
        self.lookback = lookback
        self.required_bars = lookback * 2 + 1

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        n = len(candles)
        results = [IndicatorResult(values={
            "swing_high": None, "swing_low": None, "is_swing_high": 0.0, "is_swing_low": 0.0
        }) for _ in range(n)]

        lb = self.lookback
        for i in range(lb, n - lb):
            high = candles[i].high
            low = candles[i].low
            is_sh = all(high >= candles[i - j].high for j in range(1, lb + 1)) and \
                    all(high >= candles[i + j].high for j in range(1, lb + 1))
            is_sl = all(low <= candles[i - j].low for j in range(1, lb + 1)) and \
                    all(low <= candles[i + j].low for j in range(1, lb + 1))

            results[i] = IndicatorResult(values={
                "swing_high": high if is_sh else None,
                "swing_low": low if is_sl else None,
                "is_swing_high": 1.0 if is_sh else 0.0,
                "is_swing_low": 1.0 if is_sl else 0.0,
            })
        return results
