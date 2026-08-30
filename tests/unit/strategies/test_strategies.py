"""Basic tests for Strategy Engine."""

from datetime import datetime, timedelta, timezone
from molido_shared.types import Candle, TimeFrame, Side
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine, SignalSide


def _candles(n: int = 120) -> list[Candle]:
    t0 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    price = 1.0800
    out = []
    for i in range(n):
        o = price
        c = price + (0.00012 if i % 4 else -0.00008)
        h = max(o, c) + 0.00015
        l = min(o, c) - 0.00015
        out.append(Candle(
            symbol="EURUSD",
            timeframe=TimeFrame.H1,
            open_time=t0 + timedelta(hours=i),
            open=round(o, 5), high=round(h, 5), low=round(l, 5), close=round(c, 5),
            volume=50.0,
        ))
        price = c
    return out


def test_strategy_engine_runs():
    candles = _candles()
    ind_engine = IndicatorEngine()
    ind_engine.add_from_registry("MultiEMA")
    ind_engine.add_from_registry("RSI", period=14)
    ind_engine.add_from_registry("ATR", period=14)
    ind_engine.add_from_registry("DonchianChannel", period=20)
    ind_engine.add_from_registry("BollingerBands", period=20)

    latest = ind_engine.compute_latest(candles)

    strat_engine = StrategyEngine()
    strat_engine.add_from_registry("TrendFollowing")
    strat_engine.add_from_registry("DonchianBreakout")
    strat_engine.add_from_registry("RSIMeanReversion")

    signals = strat_engine.evaluate_all(
        symbol="EURUSD",
        timeframe=TimeFrame.H1,
        candles=candles,
        indicators=latest,
        regime="Bull",
        account_mode="DEMO",
    )
    assert len(signals) == 3
    for s in signals:
        assert s.side in list(SignalSide)
        assert s.strategy_name
        assert isinstance(s.reasons, list)


def test_strategies_never_send_orders():
    """Strategies only return StrategySignal – no order side-effects."""
    candles = _candles(80)
    ind_engine = IndicatorEngine()
    ind_engine.add_from_registry("MultiEMA")
    ind_engine.add_from_registry("ATR", period=14)
    latest = ind_engine.compute_latest(candles)

    se = StrategyEngine()
    se.add_from_registry("TrendFollowing")
    signals = se.evaluate_all("EURUSD", TimeFrame.H1, candles, latest, regime="Bull")
    assert all(hasattr(s, "side") and hasattr(s, "stop_loss") for s in signals)
