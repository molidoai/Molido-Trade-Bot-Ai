"""Walk-forward evaluation with spread + commission (not clean mid candles)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from molido_shared.types import Candle, TimeFrame
from molido_indicators.engine import IndicatorEngine
from molido_strategies.engine import StrategyEngine
from molido_backtester.engine import BacktestEngine
from molido_backtester.costs import CostModel
from molido_backtester.models import BacktestResult, BacktestTrade, BacktestMetrics


@dataclass
class WalkForwardFold:
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    oos: BacktestResult


@dataclass
class WalkForwardResult:
    folds: list[WalkForwardFold] = field(default_factory=list)
    oos_trades: list[BacktestTrade] = field(default_factory=list)
    metrics: BacktestMetrics | None = None
    symbol: str = ""
    timeframe: str = ""
    notes: list[str] = field(default_factory=list)


def _default_engines() -> tuple[IndicatorEngine, StrategyEngine]:
    ind = IndicatorEngine()
    ind.add_from_registry("MultiEMA")
    ind.add_from_registry("RSI", period=14)
    ind.add_from_registry("ATR", period=14)
    strat = StrategyEngine()
    strat.configure_live(["TrendFollowing"])
    return ind, strat


def walk_forward(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: TimeFrame,
    *,
    train_bars: int = 40,
    test_bars: int = 12,
    warmup: int = 20,
    step: int | None = None,
    cost_model: CostModel | None = None,
    indicator_engine: IndicatorEngine | None = None,
    strategy_engine: StrategyEngine | None = None,
    initial_capital: float = 10_000.0,
    risk_per_trade: float = 0.0025,
    regime: str = "Bull",
    min_risk_reward: float = 0.0,
) -> WalkForwardResult:
    step = step or test_bars
    costs = cost_model or CostModel(spread_points=1.2, slippage_points=0.5, commission_per_lot=7.0)
    if indicator_engine is None or strategy_engine is None:
        d_ind, d_strat = _default_engines()
        indicator_engine = indicator_engine or d_ind
        strategy_engine = strategy_engine or d_strat
    n = len(candles)
    result = WalkForwardResult(symbol=symbol, timeframe=timeframe.value)
    if n < train_bars + test_bars:
        result.notes.append(f"not enough bars ({n}) for train={train_bars} test={test_bars}")
        result.metrics = BacktestMetrics(initial_capital=initial_capital, final_equity=initial_capital)
        return result
    engine = BacktestEngine(
        indicator_engine=indicator_engine, strategy_engine=strategy_engine,
        initial_capital=initial_capital, risk_per_trade=risk_per_trade,
        cost_model=costs, max_open=1,
        min_risk_reward=min_risk_reward,
    )
    i = 0
    while True:
        train_start = i
        train_end = i + train_bars
        test_start = train_end
        test_end = min(n, test_start + test_bars)
        if test_end - test_start < max(4, test_bars // 3):
            break
        oos_window = list(candles[:test_end])
        oos_warmup = max(warmup, train_end - 1)
        if oos_warmup >= test_end - 2:
            oos_warmup = max(10, test_start - 5)
        # regime was hardcoded to "Bull", which silently excluded every strategy
        # whose allowed_regimes does not contain it -- RSIMeanReversion is
        # Sideways/Low-Volatility only, so it produced zero trades across
        # twenty folds and looked like it had no edge when it had never been
        # allowed to run. Live computes the regime per bar; here the caller
        # names the regime it wants a strategy judged in.
        oos = engine.run(oos_window, symbol, timeframe, warmup=min(oos_warmup, test_end - 5), regime=regime)
        test_open = candles[test_start].open_time
        test_close = candles[test_end - 1].open_time
        kept = [t for t in oos.trades if t.entry_time is not None and test_open <= t.entry_time <= test_close]
        fold_result = BacktestResult(metrics=oos.metrics, trades=kept, equity_curve=oos.equity_curve, symbol=symbol, timeframe=timeframe.value)
        result.folds.append(WalkForwardFold(train_start, train_end, test_start, test_end, fold_result))
        result.oos_trades.extend(kept)
        i += step
        if test_end >= n:
            break
    nets = [t.pnl_net for t in result.oos_trades]
    equity = initial_capital + sum(nets)
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    result.metrics = BacktestMetrics(
        net_profit=sum(nets) if nets else 0.0,
        gross_profit=sum(wins) if wins else 0.0,
        gross_loss=abs(sum(losses)) if losses else 0.0,
        total_trades=len(result.oos_trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=(len(wins) / len(result.oos_trades) * 100) if result.oos_trades else 0.0,
        final_equity=equity,
        initial_capital=initial_capital,
        total_commission=sum(t.commission for t in result.oos_trades),
        total_slippage=sum(t.slippage_cost for t in result.oos_trades),
        return_pct=(equity - initial_capital) / initial_capital * 100 if initial_capital else 0.0,
    )
    result.notes.append("costs=spread+commission (not clean mid)")
    return result
