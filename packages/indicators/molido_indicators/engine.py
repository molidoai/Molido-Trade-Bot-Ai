"""
Indicator Engine – registry and batch computation.
"""

from __future__ import annotations
from typing import Sequence, Any
from molido_shared.types import Candle
from molido_indicators.base import Indicator, IndicatorResult

# Import concrete indicators
from molido_indicators.trend.ema import EMA, MultiEMA
from molido_indicators.trend.sma import SMA
from molido_indicators.trend.supertrend import Supertrend
from molido_indicators.momentum.rsi import RSI
from molido_indicators.momentum.macd import MACD
from molido_indicators.momentum.stochastic import Stochastic
from molido_indicators.volatility.atr import ATR
from molido_indicators.volatility.bollinger import BollingerBands
from molido_indicators.volatility.donchian import DonchianChannel
from molido_indicators.structure.swings import SwingPoints


# Registry of available indicators (name → class)
INDICATOR_REGISTRY: dict[str, type[Indicator]] = {
    "EMA": EMA,
    "MultiEMA": MultiEMA,
    "SMA": SMA,
    "Supertrend": Supertrend,
    "RSI": RSI,
    "MACD": MACD,
    "Stochastic": Stochastic,
    "ATR": ATR,
    "BollingerBands": BollingerBands,
    "DonchianChannel": DonchianChannel,
    "SwingPoints": SwingPoints,
}


class IndicatorEngine:
    """
    Manages a set of enabled indicators and computes them on candle series.
    """

    def __init__(self):
        self._indicators: dict[str, Indicator] = {}

    def add(self, name: str, indicator: Indicator) -> None:
        self._indicators[name] = indicator

    def add_from_registry(self, key: str, instance_name: str | None = None, **params: Any) -> None:
        if key not in INDICATOR_REGISTRY:
            raise ValueError(f"Unknown indicator: {key}. Available: {list(INDICATOR_REGISTRY)}")
        cls = INDICATOR_REGISTRY[key]
        inst = cls(**params)
        self._indicators[instance_name or key] = inst

    def remove(self, name: str) -> None:
        self._indicators.pop(name, None)

    def enable(self, name: str) -> None:
        if name in self._indicators:
            self._indicators[name].enabled = True

    def disable(self, name: str) -> None:
        if name in self._indicators:
            self._indicators[name].enabled = False

    def list_indicators(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "class": ind.name,
                "enabled": ind.enabled,
                "params": ind.params,
                "required_bars": ind.required_bars,
            }
            for name, ind in self._indicators.items()
        ]

    def compute_all(self, candles: Sequence[Candle]) -> dict[str, list[IndicatorResult]]:
        """
        Compute every enabled indicator.
        Returns {indicator_name: [result_per_bar]}
        """
        output: dict[str, list[IndicatorResult]] = {}
        for name, ind in self._indicators.items():
            if not ind.enabled:
                continue
            output[name] = ind.compute(candles)
        return output

    def compute_latest(self, candles: Sequence[Candle]) -> dict[str, IndicatorResult]:
        """Return only the latest value of each enabled indicator."""
        all_res = self.compute_all(candles)
        return {name: results[-1] for name, results in all_res.items() if results}

    @staticmethod
    def available() -> list[str]:
        return list(INDICATOR_REGISTRY.keys())
