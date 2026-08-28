from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult, sma
import math


class BollingerBands(Indicator):
    name = "BollingerBands"

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__(period=period, std_dev=std_dev)
        self.period = period
        self.std_dev = std_dev
        self.required_bars = period

    def compute(self, candles: Sequence[Candle]) -> list[IndicatorResult]:
        closes = [c.close for c in candles]
        mid = sma(closes, self.period)
        results = []

        for i in range(len(closes)):
            if mid[i] is None:
                results.append(IndicatorResult(values={
                    "middle": None, "upper": None, "lower": None, "width": None, "percent_b": None
                }))
                continue
            window = closes[i - self.period + 1: i + 1]
            mean = mid[i]
            variance = sum((x - mean) ** 2 for x in window) / self.period
            std = math.sqrt(variance)
            upper = mean + self.std_dev * std
            lower = mean - self.std_dev * std
            width = (upper - lower) / mean if mean else None
            percent_b = (closes[i] - lower) / (upper - lower) if (upper - lower) else None
            results.append(IndicatorResult(values={
                "middle": mean,
                "upper": upper,
                "lower": lower,
                "width": width,
                "percent_b": percent_b,
            }))
        return results
