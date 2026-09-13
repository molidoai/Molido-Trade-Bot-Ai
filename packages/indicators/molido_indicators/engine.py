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

    # How much history the latest value is computed over, as a multiple of the
    # longest lookback any enabled indicator declares, with a floor.
    #
    # The recursive indicators -- EMA, Wilder ATR, Supertrend -- technically
    # depend on all history, so a truncated window is an approximation. The
    # multiple is what makes the approximation irrelevant: an EMA seed decays
    # by (1 - 2/(p+1)) per bar, so with 10x its period behind it the seed
    # carries a weight of about e^-20. tests/unit/indicators/ pins this by
    # comparing bounded output against full-history output on real series.
    _TAIL_MULTIPLE = 10
    _TAIL_FLOOR = 1500

    def _tail(self, candles: Sequence[Candle]) -> Sequence[Candle]:
        need = 0
        for ind in self._indicators.values():
            if ind.enabled:
                need = max(need, int(getattr(ind, "required_bars", 1) or 1))
        window = max(self._TAIL_FLOOR, need * self._TAIL_MULTIPLE)
        return candles if len(candles) <= window else candles[-window:]

    def compute_latest(self, candles: Sequence[Candle]) -> dict[str, IndicatorResult]:
        """Return only the latest value of each enabled indicator.

        Computed over a bounded tail rather than the whole series. This used to
        hand the entire history to compute_all on every call and then throw all
        but the last element away, so a backtest that calls it once per bar did
        O(n^2) work: one decisive study row over 12,500 H1 bars took about an
        hour, which put a 15-cell parameter sweep out of reach at 15 hours and
        made the research queue the real bottleneck, not the research.
        """
        all_res = self.compute_all(self._tail(candles))
        return {name: results[-1] for name, results in all_res.items() if results}

    @staticmethod
    def available() -> list[str]:
        return list(INDICATOR_REGISTRY.keys())
