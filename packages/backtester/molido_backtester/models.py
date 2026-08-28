"""Backtest result models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BacktestTrade:
    symbol: str
    side: str
    entry_time: datetime
    exit_time: datetime | None
    entry_price: float
    exit_price: float | None
    volume: float
    stop_loss: float | None
    take_profit: float | None
    pnl: float = 0.0
    pnl_net: float = 0.0          # after costs
    commission: float = 0.0
    slippage_cost: float = 0.0
    strategy: str = ""
    exit_reason: str = ""
    bars_held: int = 0


@dataclass
class BacktestMetrics:
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_value: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    avg_trade: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_bars_held: float = 0.0
    total_commission: float = 0.0
    total_slippage: float = 0.0
    final_equity: float = 0.0
    initial_capital: float = 0.0
    return_pct: float = 0.0


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    symbol: str = ""
    timeframe: str = ""
    strategy: str = ""
