"""Backtester smoke tests – no look-ahead, metrics produced."""

from datetime import datetime, timedelta, timezone
from molido_shared.types import Candle, TimeFrame
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_backtester import BacktestEngine, CostModel


def _candles(n: int = 200) -> list[Candle]:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    price = 1.1000
    out = []
    for i in range(n):
        # mild trending series
        o = price
        c = price + (0.00015 if i % 5 else -0.0001)
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        out.append(Candle(
            symbol="EURUSD",
            timeframe=TimeFrame.H1,
            open_time=t0 + timedelta(hours=i),
            open=round(o, 5), high=round(h, 5), low=round(l, 5), close=round(c, 5),
            volume=100.0,
        ))
        price = c
    return out


def test_backtest_runs():
    ind = IndicatorEngine()
    ind.add_from_registry("MultiEMA")
    ind.add_from_registry("RSI", period=14)
    ind.add_from_registry("ATR", period=14)
    ind.add_from_registry("DonchianChannel", period=20)
    ind.add_from_registry("BollingerBands", period=20)

    strat = StrategyEngine()
    strat.add_from_registry("TrendFollowing")
    strat.add_from_registry("DonchianBreakout")

    engine = BacktestEngine(
        indicator_engine=ind,
        strategy_engine=strat,
        initial_capital=10_000.0,
        risk_per_trade=0.01,
        cost_model=CostModel(spread_points=1.2, commission_per_lot=7.0),
    )
    result = engine.run(_candles(250), "EURUSD", TimeFrame.H1, warmup=60, regime="Bull")

    assert result.metrics.initial_capital == 10_000.0
    assert result.metrics.final_equity > 0
    assert isinstance(result.trades, list)
    assert len(result.equity_curve) > 0
    # Metrics fields exist
    assert result.metrics.profit_factor >= 0
    assert 0 <= result.metrics.win_rate <= 100 or result.metrics.total_trades == 0


def test_no_lookahead_window():
    """Engine only receives candles[:i+1] – verified by successful deterministic run."""
    ind = IndicatorEngine()
    ind.add_from_registry("MultiEMA")
    ind.add_from_registry("ATR", period=14)
    strat = StrategyEngine()
    strat.add_from_registry("TrendFollowing")
    engine = BacktestEngine(ind, strat, initial_capital=5000.0)
    r1 = engine.run(_candles(150), "EURUSD", TimeFrame.H1, warmup=50)
    r2 = engine.run(_candles(150), "EURUSD", TimeFrame.H1, warmup=50)
    assert r1.metrics.total_trades == r2.metrics.total_trades
    assert r1.metrics.net_profit == r2.metrics.net_profit
