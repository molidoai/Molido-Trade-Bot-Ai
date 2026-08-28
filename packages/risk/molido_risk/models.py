"""Risk domain models."""

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
    """Configurable hard limits. PROP mode overrides daily/drawdown from firm rules."""
    risk_per_trade: float = 0.005          # 0.5% of equity
    max_daily_loss: float = 0.02           # 2%
    max_weekly_loss: float = 0.05          # 5%
    max_drawdown: float = 0.05             # 5%
    max_open_positions: int = 5
    max_portfolio_exposure: float = 0.10   # 10% of equity at risk
    max_symbol_exposure: float = 0.03      # 3% per symbol
    max_lot_size: float = 2.0
    min_lot_size: float = 0.01
    lot_step: float = 0.01
    max_leverage: float = 100.0
    min_risk_reward: float = 1.0
    max_spread_points: float = 30.0        # reject if spread too wide
    max_slippage_points: float = 10.0
    require_stop_loss: bool = True
    cooldown_seconds: int = 60
    # Volatility scaling
    high_vol_risk_mult: float = 0.5        # cut risk in half in high vol
    extreme_vol_block: bool = True


@dataclass
class AccountState:
    equity: float
    balance: float
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    peak_equity: float = 0.0
    open_positions: int = 0
    symbol_exposure: dict[str, float] = field(default_factory=dict)  # symbol → $ at risk
    portfolio_risk: float = 0.0            # total $ at risk across positions
    leverage_used: float = 0.0
    account_mode: str = "DEMO"             # DEMO / PROP / REAL
    last_trade_at: datetime | None = None


@dataclass
class RiskContext:
    """Everything Risk Engine needs for one decision."""
    symbol: str
    side: str                              # BUY / SELL / EXIT
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    signal_score: float = 0.0
    risk_reward: float | None = None
    spread_points: float | None = None
    atr: float | None = None
    regime: str | None = None
    account: AccountState = field(default_factory=lambda: AccountState(equity=0, balance=0))
    limits: RiskLimits = field(default_factory=RiskLimits)
    is_exit: bool = False


@dataclass
class RiskResult:
    decision: RiskDecision
    lot_size: float = 0.0
    risk_amount: float = 0.0               # $ risked if SL hit
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision in (RiskDecision.ALLOW, RiskDecision.REDUCE)
