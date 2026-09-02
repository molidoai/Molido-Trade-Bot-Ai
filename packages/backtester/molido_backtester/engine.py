"""
Event-driven Backtester (Master Prompt §18).

- Walks candles oldest → newest (no look-ahead)
- Uses same Strategy + Indicator path as live
- Applies CostModel (spread, slippage, commission)
- Simple SL/TP exit simulation within each bar
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence, Any

from molido_shared.types import Candle, TimeFrame
from molido_indicators.engine import IndicatorEngine
from molido_strategies.engine import StrategyEngine
from molido_strategies.base import SignalSide
from molido_backtester.models import BacktestTrade, BacktestMetrics, BacktestResult
from molido_backtester.costs import CostModel


@dataclass
class _OpenPos:
    side: str
    volume: float
    entry_price: float
    entry_time: datetime
    stop_loss: float | None
    take_profit: float | None
    strategy: str
    entry_bar: int
    commission_paid: float = 0.0
    slippage_paid: float = 0.0


class BacktestEngine:
    def __init__(
        self,
        indicator_engine: IndicatorEngine,
        strategy_engine: StrategyEngine,
        initial_capital: float = 10_000.0,
        risk_per_trade: float = 0.005,
        cost_model: CostModel | None = None,
        max_open: int = 1,
        min_risk_reward: float = 0.0,
    ):
        self.indicators = indicator_engine
        self.strategies = strategy_engine
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.costs = cost_model or CostModel()
        self.max_open = max_open
        self.min_risk_reward = min_risk_reward
        self._regime_engine = None

    def run(
        self,
        candles: Sequence[Candle],
        symbol: str,
        timeframe: TimeFrame,
        warmup: int = 50,
        regime: str | None = "Bull",
    ) -> BacktestResult:
        if len(candles) < warmup + 10:
            return BacktestResult(
                metrics=BacktestMetrics(initial_capital=self.initial_capital, final_equity=self.initial_capital),
                symbol=symbol,
                timeframe=timeframe.value,
            )

        equity = self.initial_capital
        peak = equity
        max_dd = 0.0
        max_dd_val = 0.0
        open_pos: _OpenPos | None = None
        trades: list[BacktestTrade] = []
        equity_curve: list[float] = []
        returns: list[float] = []

        cost = self.costs.for_symbol(symbol)

        for i in range(warmup, len(candles)):
            window = candles[: i + 1]          # only past + current (no look-ahead)
            bar = candles[i]
            mid = bar.close

            # --- Manage open position (SL/TP check on this bar) ---
            if open_pos is not None:
                hit = self._check_exit(open_pos, bar)
                if hit:
                    exit_price, reason = hit
                    fill = cost.exit_cost_price(open_pos.side, exit_price)
                    pnl = self._pnl(open_pos.side, open_pos.entry_price, fill, open_pos.volume, symbol)
                    commission = cost.commission(open_pos.volume)
                    slip_cost = abs(fill - exit_price) * open_pos.volume * (100_000 if not symbol.startswith("XAU") else 100)
                    pnl_net = pnl - commission - open_pos.commission_paid

                    trades.append(BacktestTrade(
                        symbol=symbol,
                        side=open_pos.side,
                        entry_time=open_pos.entry_time,
                        exit_time=bar.open_time,
                        entry_price=open_pos.entry_price,
                        exit_price=fill,
                        volume=open_pos.volume,
                        stop_loss=open_pos.stop_loss,
                        take_profit=open_pos.take_profit,
                        pnl=pnl,
                        pnl_net=pnl_net,
                        commission=commission + open_pos.commission_paid,
                        slippage_cost=slip_cost + open_pos.slippage_paid,
                        strategy=open_pos.strategy,
                        exit_reason=reason,
                        bars_held=i - open_pos.entry_bar,
                    ))
                    equity += pnl_net
                    returns.append(pnl_net / self.initial_capital)
                    open_pos = None

            # --- Mark equity ---
            if open_pos is not None:
                u_pnl = self._pnl(open_pos.side, open_pos.entry_price, mid, open_pos.volume, symbol)
                equity_curve.append(equity + u_pnl)
            else:
                equity_curve.append(equity)

            if equity_curve[-1] > peak:
                peak = equity_curve[-1]
            dd_val = peak - equity_curve[-1]
            dd_pct = dd_val / peak * 100 if peak > 0 else 0
            if dd_pct > max_dd:
                max_dd = dd_pct
                max_dd_val = dd_val

            # --- New entries only if flat and under max_open ---
            if open_pos is not None:
                continue

            # Indicators on window only
            ind_latest = self.indicators.compute_latest(window)
            # regime="auto" classifies each bar instead of asserting one for
            # the whole run. Passing a fixed string bypassed the regime engine
            # entirely, so a regime filter could never be evaluated here -- the
            # backtest was measuring the strategies with that gate removed,
            # which is not what runs live.
            bar_regime = regime
            if regime == "auto":
                if self._regime_engine is None:
                    from molido_regime import MarketRegimeEngine
                    self._regime_engine = MarketRegimeEngine()
                bar_regime = self._regime_engine.classify(window, ind_latest)

            signals = self.strategies.evaluate_all(
                symbol=symbol,
                timeframe=timeframe,
                candles=window,
                indicators=ind_latest,
                regime=bar_regime,
                account_mode="DEMO",
            )
            actionable = [s for s in signals if s.side in (SignalSide.BUY, SignalSide.SELL) and s.stop_loss]

            if not actionable:
                continue

            # The live RiskEngine refuses anything under min_risk_reward, and
            # the backtester did not, so every walk-forward number so far was
            # measured on a wider set of trades than the bot actually takes.
            # 0.0 keeps the old behaviour.
            if self.min_risk_reward > 0:
                def _rr(x):
                    if x.stop_loss is None or x.take_profit is None or x.entry is None:
                        return None
                    risk = abs(x.entry - x.stop_loss)
                    return abs(x.take_profit - x.entry) / risk if risk else None
                actionable = [x for x in actionable
                              if (_rr(x) or 0) >= self.min_risk_reward]
                if not actionable:
                    continue

            sig = max(actionable, key=lambda s: s.confidence)
            entry_mid = mid
            fill = cost.entry_cost_price(sig.side.value, entry_mid)

            # Position size from risk
            if sig.stop_loss is None:
                continue
            stop_dist = abs(fill - sig.stop_loss)
            if stop_dist <= 0:
                continue
            risk_amount = equity * self.risk_per_trade
            pip = cost.point_size
            stop_pips = stop_dist / pip
            risk_per_lot = stop_pips * 10.0  # heuristic
            if risk_per_lot <= 0:
                continue
            volume = max(0.01, math.floor(risk_amount / risk_per_lot * 100) / 100)
            volume = min(volume, 5.0)

            commission = cost.commission(volume)
            slip = abs(fill - entry_mid) * volume * (100_000 if not symbol.startswith("XAU") else 100)

            open_pos = _OpenPos(
                side=sig.side.value,
                volume=volume,
                entry_price=fill,
                entry_time=bar.open_time,
                stop_loss=sig.stop_loss,
                take_profit=sig.take_profit,
                strategy=sig.strategy_name,
                entry_bar=i,
                commission_paid=commission,
                slippage_paid=slip,
            )

        # Force close at end
        if open_pos is not None:
            bar = candles[-1]
            fill = cost.exit_cost_price(open_pos.side, bar.close)
            pnl = self._pnl(open_pos.side, open_pos.entry_price, fill, open_pos.volume, symbol)
            commission = cost.commission(open_pos.volume)
            pnl_net = pnl - commission - open_pos.commission_paid
            trades.append(BacktestTrade(
                symbol=symbol,
                side=open_pos.side,
                entry_time=open_pos.entry_time,
                exit_time=bar.open_time,
                entry_price=open_pos.entry_price,
                exit_price=fill,
                volume=open_pos.volume,
                stop_loss=open_pos.stop_loss,
                take_profit=open_pos.take_profit,
                pnl=pnl,
                pnl_net=pnl_net,
                commission=commission + open_pos.commission_paid,
                strategy=open_pos.strategy,
                exit_reason="end_of_data",
                bars_held=len(candles) - 1 - open_pos.entry_bar,
            ))
            equity += pnl_net
            equity_curve.append(equity)

        metrics = self._compute_metrics(trades, equity, max_dd, max_dd_val, returns)
        return BacktestResult(
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            symbol=symbol,
            timeframe=timeframe.value,
            strategy=",".join(self.strategies.available()) if hasattr(self.strategies, "available") else "",
            params={
                "initial_capital": self.initial_capital,
                "risk_per_trade": self.risk_per_trade,
                "warmup": warmup,
            },
        )

    @staticmethod
    def _check_exit(pos: _OpenPos, bar: Candle) -> tuple[float, str] | None:
        """Intrabar SL/TP: conservative – assume SL hit first on adverse bars."""
        if pos.side == "BUY":
            if pos.stop_loss is not None and bar.low <= pos.stop_loss:
                return pos.stop_loss, "SL"
            if pos.take_profit is not None and bar.high >= pos.take_profit:
                return pos.take_profit, "TP"
        else:
            if pos.stop_loss is not None and bar.high >= pos.stop_loss:
                return pos.stop_loss, "SL"
            if pos.take_profit is not None and bar.low <= pos.take_profit:
                return pos.take_profit, "TP"
        return None

    @staticmethod
    def _pnl(side: str, entry: float, exit: float, volume: float, symbol: str) -> float:
        direction = 1.0 if side.upper() == "BUY" else -1.0
        move = (exit - entry) * direction
        # Approximate $ value
        if symbol.startswith("XAU"):
            return move * volume * 100  # rough
        return move * volume * 100_000

    def _compute_metrics(
        self,
        trades: list[BacktestTrade],
        final_equity: float,
        max_dd: float,
        max_dd_val: float,
        returns: list[float],
    ) -> BacktestMetrics:
        if not trades:
            return BacktestMetrics(
                initial_capital=self.initial_capital,
                final_equity=final_equity,
            )

        nets = [t.pnl_net for t in trades]
        wins = [x for x in nets if x > 0]
        losses = [x for x in nets if x <= 0]
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        # Sharpe / Sortino (simple, per-trade)
        avg_r = sum(returns) / len(returns) if returns else 0.0
        if len(returns) > 1:
            var = sum((r - avg_r) ** 2 for r in returns) / (len(returns) - 1)
            std = math.sqrt(var) if var > 0 else 1e-9
            sharpe = (avg_r / std) * math.sqrt(252) if std > 0 else 0.0
            downside = [r for r in returns if r < 0]
            if downside:
                dvar = sum(r ** 2 for r in downside) / len(downside)
                dstd = math.sqrt(dvar) if dvar > 0 else 1e-9
                sortino = (avg_r / dstd) * math.sqrt(252) if dstd > 0 else 0.0
            else:
                sortino = sharpe
        else:
            sharpe = sortino = 0.0

        return BacktestMetrics(
            net_profit=sum(nets),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / len(trades) * 100 if trades else 0.0,
            profit_factor=round(pf, 3),
            expectancy=sum(nets) / len(trades),
            max_drawdown_pct=round(max_dd, 3),
            max_drawdown_value=round(max_dd_val, 2),
            sharpe=round(sharpe, 3),
            sortino=round(sortino, 3),
            avg_trade=sum(nets) / len(trades),
            best_trade=max(nets),
            worst_trade=min(nets),
            avg_bars_held=sum(t.bars_held for t in trades) / len(trades),
            total_commission=sum(t.commission for t in trades),
            total_slippage=sum(t.slippage_cost for t in trades),
            final_equity=final_equity,
            initial_capital=self.initial_capital,
            return_pct=(final_equity - self.initial_capital) / self.initial_capital * 100,
        )
