"""
Strategy Engine base classes.

Rules (Master Prompt §8):
- Strategies are plugin-like
- They produce Signals only – NEVER send orders
- Must declare entry/exit rules, timeframes, allowed regimes, risk profile
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence

from molido_shared.types import Candle, Side, TimeFrame
from molido_indicators.base import IndicatorResult


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


@dataclass
class StrategySignal:
    """
    Standardized signal output (Master Prompt §9).
    """
    symbol: str
    side: SignalSide
    timeframe: TimeFrame
    strategy_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence: float = 0.0          # 0–100
    score: float = 0.0               # composite score
    reasons: list[str] = field(default_factory=list)
    market_regime: str | None = None
    risk_reward: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def is_actionable(self) -> bool:
        return self.side in (SignalSide.BUY, SignalSide.SELL, SignalSide.EXIT)


@dataclass
class StrategyContext:
    """
    Everything a strategy needs to make a decision.
    Provided by the engine – strategy never fetches data itself.
    """
    symbol: str
    timeframe: TimeFrame
    candles: Sequence[Candle]
    indicators: dict[str, IndicatorResult]   # latest values keyed by indicator name
    regime: str | None = None
    account_mode: str = "DEMO"               # DEMO / PROP / REAL
    open_position_side: Side | None = None   # if already in a position


class Strategy(ABC):
    """
    Abstract strategy plugin.
    """
    name: str = "base"
    strategy_type: str = "generic"           # trend / breakout / momentum / mean_reversion / ...
    default_timeframe: TimeFrame = TimeFrame.M15
    allowed_regimes: list[str] = field(default_factory=lambda: ["Bull", "Bear", "Sideways", "Unknown"])
    risk_profile: str = "normal"             # conservative / normal / aggressive
    cooldown_bars: int = 0                   # min bars between signals

    def __init__(self, **params: Any):
        self.params = params
        self.enabled: bool = True
        self._last_signal_bar_time: datetime | None = None

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        """
        Produce a signal for the current context.
        Must be deterministic and free of look-ahead.
        """
        ...

    def _no_trade(self, ctx: StrategyContext, reason: str) -> StrategySignal:
        return StrategySignal(
            symbol=ctx.symbol,
            side=SignalSide.NO_TRADE,
            timeframe=ctx.timeframe,
            strategy_name=self.name,
            reasons=[reason],
            market_regime=ctx.regime,
        )

    def _hold(self, ctx: StrategyContext, reason: str = "No clear edge") -> StrategySignal:
        return StrategySignal(
            symbol=ctx.symbol,
            side=SignalSide.HOLD,
            timeframe=ctx.timeframe,
            strategy_name=self.name,
            reasons=[reason],
            market_regime=ctx.regime,
        )

    def is_regime_allowed(self, regime: str | None) -> bool:
        if regime is None:
            return True
        return regime in self.allowed_regimes
