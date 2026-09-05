"""
Strategy Engine – registry and evaluation orchestrator.
Strategies only produce signals; they never send orders.

Live default enables ONLY TrendFollowing until a DEMO journal says otherwise.
DonchianBreakout and RSIMeanReversion stay in the registry, disabled.
"""

from __future__ import annotations
from typing import Any, Sequence

from molido_shared.types import Candle, TimeFrame, Side
from molido_indicators.base import IndicatorResult
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide

from molido_strategies.trend.trend_following import TrendFollowingStrategy
from molido_strategies.trend.trend_pullback import TrendPullback
from molido_strategies.trend.ensemble import EnsembleTrend, EnsembleADXTrend
from molido_strategies.mean_reversion.strength_reversion import StrengthReversion
from molido_strategies.breakout.donchian_breakout import DonchianBreakoutStrategy
from molido_strategies.mean_reversion.rsi_reversion import RSIMeanReversionStrategy


# Registered is not enabled. Everything here can be selected by name from
# settings so it can be measured; DEFAULT_LIVE_STRATEGIES decides what actually
# trades, and the per-symbol map narrows that further.
#
# The three below have been measured to a conclusion and refuted, and are kept
# for the same reason TrendPullback is: a candidate that was tested and lost is
# more useful in the registry than deleted, because the next person asking
# "has anyone tried an ADX ensemble?" can re-run it in one command instead of
# rewriting it. The numbers are in proven_edges.json.
STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "TrendFollowing": TrendFollowingStrategy,
    # Candidate replacement; registered so it can be measured, not enabled.
    "TrendPullback": TrendPullback,
    # Filters are switchable so combinations can be measured, not argued.
    "EnsembleTrend": EnsembleTrend,
    # The ADX25 + 50/200 preset. Refuted 2026-09-04 once the harness actually
    # computed ADX: 1.12 on 28 trades (under the 30 minimum) and 6/16 folds,
    # then 0.95, 0.51, 0.41. Before that fix it returned zero trades and was
    # recorded as "no edge" on the strength of a number about the harness.
    "EnsembleADXTrend": EnsembleADXTrend,
    # The only signal to beat its own shuffled control. Still refuted on
    # returns: 0.69 to 0.98 across all eleven symbols, never above 1.0.
    "StrengthReversion": StrengthReversion,
    "DonchianBreakout": DonchianBreakoutStrategy,
    "RSIMeanReversion": RSIMeanReversionStrategy,
}

DEFAULT_LIVE_STRATEGIES = ["TrendFollowing"]


def parse_strategy_names(raw: Any) -> list[str]:
    if raw is None:
        return list(DEFAULT_LIVE_STRATEGIES)
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        return parts or list(DEFAULT_LIVE_STRATEGIES)
    if isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw if str(p).strip()]
        return parts or list(DEFAULT_LIVE_STRATEGIES)
    return list(DEFAULT_LIVE_STRATEGIES)


def parse_symbol_strategies(raw: Any) -> dict[str, set[str]]:
    """{"XAUUSD": ["TrendFollowing"], "EURUSD": "RSIMeanReversion"} -> sets.

    Symbols are upper-cased; a symbol with an empty list means "nothing may
    trade here", which is a legitimate thing to say about an instrument every
    strategy lost on. Anything malformed is ignored rather than raised: a bad
    dashboard entry must not take the engine down.
    """
    out: dict[str, set[str]] = {}
    if not isinstance(raw, dict):
        return out
    for sym, names in raw.items():
        key = str(sym).strip().upper()
        if not key:
            continue
        if isinstance(names, str):
            parts = [p.strip() for p in names.replace(";", ",").split(",") if p.strip()]
        elif isinstance(names, (list, tuple)):
            parts = [str(p).strip() for p in names if str(p).strip()]
        else:
            continue
        out[key] = set(parts)
    return out


class StrategyEngine:
    def __init__(self):
        self._strategies: dict[str, Strategy] = {}
        # Per-symbol restriction on top of the enabled set. The walk-forward
        # of 2026-09-03 showed no strategy with an edge on every symbol but
        # most symbols with one strategy that held up out of sample, so the
        # unit of configuration has to be (symbol, strategy), not strategy.
        # A symbol absent from the map runs every enabled strategy, so a
        # deployment that never sets this behaves exactly as before.
        self._symbol_allow: dict[str, set[str]] = {}

    def configure_symbol_map(self, mapping: dict[str, set[str]] | None) -> None:
        self._symbol_allow = {k: set(v) for k, v in (mapping or {}).items()}

    def symbol_map(self) -> dict[str, set[str]]:
        return {k: set(v) for k, v in self._symbol_allow.items()}

    def allowed_for(self, symbol: str) -> list[str]:
        """Enabled strategies that may trade `symbol`."""
        allow = self._symbol_allow.get(str(symbol).upper())
        return [n for n, s in self._strategies.items()
                if s.enabled and (allow is None or n in allow)]

    def get(self, name: str) -> Strategy | None:
        """The live instance under this name, or None."""
        return self._strategies.get(name)

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

    def configure_live(self, names: list[str] | None = None) -> None:
        """Register every class; enable only `names` (default TrendFollowing)."""
        enabled = parse_strategy_names(names)
        for key in STRATEGY_REGISTRY:
            if key not in self._strategies:
                self.add_from_registry(key)
            if key in enabled:
                self.enable(key)
            else:
                self.disable(key)

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

    def enabled_names(self) -> list[str]:
        return [name for name, s in self._strategies.items() if s.enabled]

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
        allow = self._symbol_allow.get(str(symbol).upper())
        for name, strategy in self._strategies.items():
            if not strategy.enabled:
                continue
            if allow is not None and name not in allow:
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
