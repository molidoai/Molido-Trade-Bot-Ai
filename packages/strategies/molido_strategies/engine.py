"""
Strategy Engine – registry and evaluation orchestrator.
Strategies only produce signals; they never send orders.
"""

from __future__ import annotations
from typing import Any, Sequence

from molido_shared.types import Candle, TimeFrame, Side
from molido_indicators.base import IndicatorResult
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide

from molido_strategies.trend.trend_following import TrendFollowingStrategy
from molido_strategies.breakout.donchian_breakout import DonchianBreakoutStrategy
from molido_strategies.mean_reversion.rsi_reversion import RSIMeanReversionStrategy


STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "TrendFollowing": TrendFollowingStrategy,
    "DonchianBreakout": DonchianBreakoutStrategy,
    "RSIMeanReversion": RSIMeanReversionStrategy,
}


class StrategyEngine:
    def __init__(self):
        self._strategies: dict[str, Strategy] = {}

    def register(self, name: str, strategy: Strategy) -> None:
        self._strategies[name] = strategy

    def add_from_registry(self, key: str, instance_name: str | None = None, **params: Any) -> None:
        if key not in STRATEGY_REGISTRY:
            raise ValueError(f"Unknown strategy: {key}. Available: {list(STRATEGY_REGISTRY)}")
        cls = STRATEGY_REGISTRY[key]
        self._strategies[instance_name or key] = cls(**params)

    def enable(self, name: str) -> None:
        if name in self._strategies:
            self._strategies[name].enabled = True

    def disable(self, name: str) -> None:
        if name in self._strategies:
            self._strategies[name].enabled = False

    def list_strategies(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "class": s.name,
                "type": s.strategy_type,
                "enabled": s.enabled,
                "timeframe": s.default_timeframe.value,
                "allowed_regimes": s.allowed_regimes,
                "risk_profile": s.risk_profile,
                "params": s.params,
            }
            for name, s in self._strategies.items()
        ]

    def evaluate_all(
        self,
        symbol: str,
        timeframe: TimeFrame,
        candles: Sequence[Candle],
        indicators: dict[str, IndicatorResult],
        regime: str | None = None,
        account_mode: str = "DEMO",
        open_position_side: Side | None = None,
    ) -> list[StrategySignal]:
        """
        Run every enabled strategy and return their signals.
        """
        ctx = StrategyContext(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            indicators=indicators,
            regime=regime,
            account_mode=account_mode,
            open_position_side=open_position_side,
        )
        signals: list[StrategySignal] = []
        for name, strategy in self._strategies.items():
            if not strategy.enabled:
                continue
            try:
                sig = strategy.evaluate(ctx)
                signals.append(sig)
            except Exception as e:
                signals.append(StrategySignal(
                    symbol=symbol,
                    side=SignalSide.NO_TRADE,
                    timeframe=timeframe,
                    strategy_name=name,
                    reasons=[f"Strategy error: {e}"],
                ))
        return signals

    def best_actionable(self, signals: list[StrategySignal]) -> StrategySignal | None:
        """Pick the highest-confidence actionable signal (BUY/SELL/EXIT)."""
        actionable = [s for s in signals if s.is_actionable()]
        if not actionable:
            return None
        return max(actionable, key=lambda s: s.confidence)

    @staticmethod
    def available() -> list[str]:
        return list(STRATEGY_REGISTRY.keys())
