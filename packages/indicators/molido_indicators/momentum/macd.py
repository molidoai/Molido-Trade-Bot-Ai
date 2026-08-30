from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, ema


class MACD(Indicator):
    name = "MACD"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(fast=fast, slow=slow, signal=signal)
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.required_bars = slow + signal

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        closes = [c.close for c in candles]
        fast_ema = ema(closes, self.fast)
        slow_ema = ema(closes, self.slow)

        macd_line: list[float | None] = [None] * len(closes)
        for i in range(len(closes)):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                macd_line[i] = fast_ema[i] - slow_ema[i]

        # Signal = EMA of MACD line (only on valid values)
        valid_macd = [v if v is not None else 0.0 for v in macd_line]
        signal_line = ema(valid_macd, self.signal_period)

        results = []
        for i in range(len(closes)):
            m = macd_line[i]
            s = signal_line[i] if macd_line[i] is not None else None
            hist = (m - s) if (m is not None and s is not None) else None
            results.append(IndicatorResult(values={
                "macd": m,
                "signal": s,
                "histogram": hist,
            }))
        return results
