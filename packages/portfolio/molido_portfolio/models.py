"""Portfolio / Position domain models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ManagedPosition:
    ticket: str
    symbol: str
    side: str
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    strategy: str | None = None
    opened_at: datetime | None = None
    account_id: int | None = None

    @property
    def risk_if_sl_hit(self) -> float:
        if self.stop_loss is None:
            return 0.0
        dist = abs(self.entry_price - self.stop_loss)
        try:
            from molido_risk.engine import RiskEngine
            pip = RiskEngine._estimate_pip_size(self.symbol, self.entry_price)
            pips = dist / pip if pip else 0.0
            return RiskEngine._risk_per_lot(self.symbol, self.entry_price, pips) * self.volume
        except Exception:
            pip = 0.01 if self.entry_price > 50 else 0.0001
            pips = dist / pip if pip else 0.0
            return pips * 10.0 * self.volume


@dataclass
class PortfolioSnapshot:
    balance: float
    equity: float
    margin_used: float = 0.0
    free_margin: float = 0.0
    margin_level: float | None = None
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    open_positions: int = 0
    portfolio_risk: float = 0.0
    symbol_exposure: dict[str, float] = field(default_factory=dict)
    currency_exposure: dict[str, float] = field(default_factory=dict)
    drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    account_mode: str = "DEMO"
    as_of: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    open_symbols: list[str] = field(default_factory=list)
    open_side_by_symbol: dict[str, str] = field(default_factory=dict)


@dataclass
class ReconcileReport:
    success: bool
    positions_synced: int = 0
    orders_synced: int = 0
    discrepancies: list[str] = field(default_factory=list)
    local_only_tickets: list[str] = field(default_factory=list)
    broker_only_tickets: list[str] = field(default_factory=list)
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
