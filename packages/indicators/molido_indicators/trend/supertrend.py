from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, true_range, ema


class Supertrend(Indicator):
    """
    Supertrend indicator.
    direction: 1 = bullish (price above line), -1 = bearish
    """
    name = "Supertrend"

    def __init__(self, period: int = 10, multiplier: float = 3.0):
        super().__init__(period=period, multiplier=multiplier)
        self.period = period
        self.multiplier = multiplier
        self.required_bars = period + 1

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        n = len(candles)
        results = [IndicatorResult(values={"supertrend": None, "direction": None}) for _ in range(n)]
        if n < self.required_bars:
            return results

        tr = true_range(candles)
        atr = ema(tr, self.period)  # using EMA of TR as ATR approximation

        final_ub = [0.0] * n
        final_lb = [0.0] * n
        direction = [1] * n
        supertrend = [0.0] * n

        for i in range(n):
            if atr[i] is None:
                continue
            mid = (candles[i].high + candles[i].low) / 2
            basic_ub = mid + self.multiplier * atr[i]
            basic_lb = mid - self.multiplier * atr[i]

            if i == 0 or atr[i - 1] is None:
                final_ub[i] = basic_ub
                final_lb[i] = basic_lb
                supertrend[i] = basic_lb
                direction[i] = 1
                continue

            # Final bands
            final_ub[i] = basic_ub if (basic_ub < final_ub[i - 1] or candles[i - 1].close > final_ub[i - 1]) else final_ub[i - 1]
            final_lb[i] = basic_lb if (basic_lb > final_lb[i - 1] or candles[i - 1].close < final_lb[i - 1]) else final_lb[i - 1]

            if direction[i - 1] == 1:
                if candles[i].close < final_lb[i]:
                    direction[i] = -1
                    supertrend[i] = final_ub[i]
                else:
                    direction[i] = 1
                    supertrend[i] = final_lb[i]
            else:
                if candles[i].close > final_ub[i]:
                    direction[i] = 1
                    supertrend[i] = final_lb[i]
                else:
                    direction[i] = -1
                    supertrend[i] = final_ub[i]

            results[i] = IndicatorResult(values={
                "supertrend": supertrend[i],
                "direction": float(direction[i]),
            })
        return results
