"""Risk domain models. Conservative defaults: small losses, never a profit claim."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RiskDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REDUCE = "REDUCE"  # allow but with smaller size


@dataclass
class RiskLimits:
    """Hard limits. Sized so a bad week hurts little, not so the bot 'cannot lose'."""
    risk_per_trade: float = 0.0025         # 0.25% of equity
    max_daily_loss: float = 0.02           # 2% then circuit
    max_weekly_loss: float = 0.06          # 6% then circuit
    max_drawdown: float = 0.04             # 4%
    max_open_positions: int = 3
    max_entries_per_day: int = 4
    max_consecutive_losses: int = 3
    consecutive_loss_pause_seconds: int = 4 * 3600
    max_portfolio_exposure: float = 0.05   # 5% of equity at risk
    max_symbol_exposure: float = 0.015     # 1.5% per symbol
    max_lot_size: float = 0.50
    min_lot_size: float = 0.01
    lot_step: float = 0.01
    max_leverage: float = 100.0
    min_risk_reward: float = 1.5
    max_spread_points: float = 20.0
    max_slippage_points: float = 8.0
    require_stop_loss: bool = True
    cooldown_seconds: int = 180
    high_vol_risk_mult: float = 0.25
    extreme_vol_block: bool = True
    # Optional ML volatility-warning signal (packages/regime/ml_engine.py).
    # Reuses high_vol_risk_mult above -- an ML high-vol call reduces size the
    # same way a rule-based "High Volatility" regime does, never differently.
    ml_high_vol_threshold: float = 0.5
    block_correlated: bool = True
    min_margin_level: float = 300.0
    min_free_margin_ratio: float = 0.3
    deny_average_down: bool = True
    pause_on_negative_journal: bool = True
    dead_atr_ratio: float = 0.0003
    atr_vs_stop_max: float = 1.2


@dataclass
class AccountState:
    equity: float
    balance: float
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    peak_equity: float = 0.0
    open_positions: int = 0
    symbol_exposure: dict[str, float] = field(default_factory=dict)
    portfolio_risk: float = 0.0
    leverage_used: float = 0.0
    account_mode: str = "DEMO"
    last_trade_at: datetime | None = None
    consecutive_losses: int = 0
    entries_today: int = 0
    open_symbols: list[str] = field(default_factory=list)
    last_loss_at: datetime | None = None
    margin_level: float | None = None
    free_margin: float | None = None
    margin_used: float | None = None
    open_side_by_symbol: dict[str, str] = field(default_factory=dict)


@dataclass
class RiskContext:
    """Everything Risk Engine needs for one decision."""
    symbol: str
    side: str
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    signal_score: float = 0.0
    risk_reward: float | None = None
    spread_points: float | None = None
    atr: float | None = None
    # Timeframe `atr` was measured on -- dead_atr_ratio is calibrated for
    # M15, so the gate rescales it for other bar sizes (see
    # molido_shared.volatility). None keeps the unscaled M15 behavior.
    timeframe: str | None = None
    regime: str | None = None
    # P(model's "HighVol" label) from molido_regime.MLVolatilityDetector, or
    # None if no model is loaded / not enough history -- None must behave
    # identically to "no ML signal", never as 0.0 (which would be a claim).
    ml_high_vol_prob: float | None = None
    account: AccountState = field(default_factory=lambda: AccountState(equity=0, balance=0))
    # None (not a fresh RiskLimits()) so RiskEngine.evaluate()'s
    # `ctx.limits or self.limits` actually falls back to the engine's own
    # configured limits when the caller doesn't explicitly override them —
    # a default-constructed RiskLimits() here would silently ignore
    # RiskEngine(limits=...) for any caller that forgets to re-thread it.
    limits: RiskLimits | None = None
    is_exit: bool = False


@dataclass
class RiskResult:
    decision: RiskDecision
    lot_size: float = 0.0
    risk_amount: float = 0.0
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision in (RiskDecision.ALLOW, RiskDecision.REDUCE)
