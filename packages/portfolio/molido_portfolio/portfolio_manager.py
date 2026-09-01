"""
Portfolio Manager (Master Prompt §17).
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

from molido_broker.base import BrokerAdapter
from molido_portfolio.position_manager import PositionManager
from molido_portfolio.models import PortfolioSnapshot

logger = logging.getLogger(__name__)


class PortfolioManager:
    def __init__(
        self,
        broker: BrokerAdapter,
        position_manager: PositionManager,
        account_mode: str = "DEMO",
    ):
        self.broker = broker
        self.positions = position_manager
        self.account_mode = account_mode
        self._peak_equity: float = 0.0
        self._daily_realized: float = 0.0

    async def snapshot(self) -> PortfolioSnapshot:
        info = await self.broker.get_account_info()
        equity = info.equity
        if equity > self._peak_equity:
            self._peak_equity = equity

        peak = self._peak_equity or equity
        dd = ((peak - equity) / peak * 100.0) if peak > 0 else 0.0

        symbol_exp = self.positions.symbol_risk_map()
        currency: dict[str, float] = {}
        open_symbols: list[str] = []
        sides: dict[str, str] = {}
        for p in self.positions.get_all():
            open_symbols.append(p.symbol)
            sides[p.symbol] = p.side.upper()
            if len(p.symbol) >= 6:
                base, quote = p.symbol[:3], p.symbol[3:6]
                sign = 1.0 if p.side.upper() == "BUY" else -1.0
                notional = p.volume * 100_000
                currency[base] = currency.get(base, 0.0) + sign * notional
                currency[quote] = currency.get(quote, 0.0) - sign * notional

        return PortfolioSnapshot(
            balance=info.balance,
            equity=equity,
            margin_used=info.margin,
            free_margin=info.free_margin,
            margin_level=info.margin_level,
            unrealized_pnl=info.profit,
            realized_pnl_today=self._realized_today(info.balance),
            open_positions=self.positions.count(),
            portfolio_risk=self.positions.total_risk(),
            symbol_exposure=symbol_exp,
            currency_exposure=currency,
            drawdown_pct=round(dd, 3),
            peak_equity=peak,
            account_mode=self.account_mode,
            as_of=datetime.now(timezone.utc),
            open_symbols=open_symbols,
            open_side_by_symbol=sides,
        )

    def record_realized(self, pnl: float) -> None:
        self._daily_realized += pnl

    def reset_daily(self) -> None:
        self._daily_realized = 0.0
        self._day_open_balance: float | None = None
        self._day = None
        self._day_open_balance = None
        self._day = None

    def _realized_today(self, balance: float) -> float:
        """Today's realised PnL, derived from the broker's own balance.

        record_realized() exists but nothing in the codebase has ever called
        it, so _daily_realized stayed 0.0 for the life of the process. That
        left daily_pnl equal to the *unrealized* PnL alone: the moment a losing
        position closed, the loss vanished from it and the daily-loss circuit
        breaker went back to seeing zero. On 2026-09-01 the demo account gave
        back 2.6% in closed trades and kept trading straight through a 2% cap.

        Balance only moves when a trade is realised (or on a deposit), so the
        delta from the day's opening balance is the realised figure, and it
        survives a restart mid-session in a way an in-memory counter does not.
        A deposit would read as profit here, which is the harmless direction --
        it can only ever loosen a limit the operator just funded, never tighten
        one unexpectedly.
        """
        today = datetime.now(timezone.utc).date()
        if self._day != today or self._day_open_balance is None:
            self._day = today
            # Opening balance for a day that starts mid-session is the balance
            # right now, less anything already floating -- not the equity.
            self._day_open_balance = balance - self._daily_realized
        return round(balance - self._day_open_balance + self._daily_realized, 2)

    def to_account_state(self, snap: PortfolioSnapshot, last_trade_at=None):
        """Convert snapshot to RiskEngine AccountState shape."""
        from molido_risk.models import AccountState
        return AccountState(
            equity=snap.equity,
            balance=snap.balance,
            daily_pnl=snap.realized_pnl_today + snap.unrealized_pnl,
            weekly_pnl=0.0,
            peak_equity=snap.peak_equity,
            open_positions=snap.open_positions,
            symbol_exposure=snap.symbol_exposure,
            portfolio_risk=snap.portfolio_risk,
            account_mode=snap.account_mode,
            last_trade_at=last_trade_at,
            open_symbols=list(snap.open_symbols),
            margin_level=snap.margin_level,
            free_margin=snap.free_margin,
            margin_used=snap.margin_used,
            open_side_by_symbol=dict(snap.open_side_by_symbol),
        )
