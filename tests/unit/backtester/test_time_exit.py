"""The holding-horizon exit.

These exist because the feature was once described in a strategy docstring,
passed as an environment variable by a study script, and reported on in three
result rows -- while no code anywhere read it. Every number in that study was
the no-time-exit case wearing three different labels. A test that asserts the
exit actually fires is the thing that would have caught it, so here it is.
"""

from datetime import datetime, timedelta, timezone

from molido_shared.types import Candle, TimeFrame
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide
from molido_backtester import BacktestEngine, CostModel


def _flat_candles(n: int = 120, drift: float = 0.0) -> list[Candle]:
    """A series that never reaches a distant stop or target, so the only exit
    available is the passage of time."""
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    price = 1.1000
    out = []
    for i in range(n):
        o = price
        c = price + drift
        out.append(Candle(
            symbol="EURUSD", timeframe=TimeFrame.H1,
            open_time=t0 + timedelta(hours=i),
            open=round(o, 5), high=round(max(o, c) + 0.00005, 5),
            low=round(min(o, c) - 0.00005, 5), close=round(c, 5), volume=100.0,
        ))
        price = c
    return out


class _AlwaysBuy(Strategy):
    """Buys on every flat bar with stops far enough away never to be touched."""

    name = "_AlwaysBuy"
    strategy_type = "test"
    allowed_regimes = ["Bull", "Bear", "Strong Bull", "Strong Bear",
                       "Sideways", "Low Volatility", "High Volatility"]

    def __init__(self, max_hold_bars: int = 0, **kw):
        super().__init__(**kw)
        self.max_hold_bars = max_hold_bars

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        if ctx.open_position_side is not None or not ctx.candles:
            return StrategySignal(symbol=ctx.symbol, side=SignalSide.NO_TRADE,
                                  timeframe=ctx.timeframe, strategy_name=self.name)
        px = ctx.candles[-1].close
        return StrategySignal(
            symbol=ctx.symbol, side=SignalSide.BUY, timeframe=ctx.timeframe,
            strategy_name=self.name, entry=px,
            stop_loss=round(px - 0.05, 5), take_profit=round(px + 0.05, 5),
            confidence=90.0, score=90.0,
        )


def _run(hold_on_strategy: int, engine_override: int = 0, drift: float = 0.0):
    strat = StrategyEngine()
    strat.register("_AlwaysBuy", _AlwaysBuy(max_hold_bars=hold_on_strategy))
    strat.enable("_AlwaysBuy")
    engine = BacktestEngine(
        indicator_engine=IndicatorEngine(),
        strategy_engine=strat,
        cost_model=CostModel(spread_points=0.0, slippage_points=0.0,
                             commission_per_lot=0.0),
        max_hold_bars=engine_override,
    )
    return engine.run(_flat_candles(120, drift), "EURUSD", TimeFrame.H1,
                      warmup=10, regime="Sideways")


def test_no_horizon_means_the_position_survives_to_the_end():
    # Without a time exit and with unreachable stops, one position is opened
    # and only the end of the data closes it.
    res = _run(hold_on_strategy=0)
    assert len(res.trades) == 1
    assert res.trades[0].exit_reason == "end_of_data"


def test_the_horizon_actually_closes_the_position():
    res = _run(hold_on_strategy=10)
    assert len(res.trades) > 1, "a 10-bar horizon over 110 bars must recycle"
    assert all(t.exit_reason == "time" for t in res.trades[:-1])
    assert all(t.bars_held == 10 for t in res.trades[:-1])


def test_engine_override_beats_the_strategy_setting():
    # A study sweeping the horizon must not be silently overruled by the
    # strategy's own default -- that is how a sweep reports one number three
    # times.
    res = _run(hold_on_strategy=10, engine_override=25)
    timed = [t for t in res.trades if t.exit_reason == "time"]
    assert timed, "override produced no timed exits"
    assert all(t.bars_held == 25 for t in timed)


def test_different_horizons_give_different_results():
    """The regression test for the actual bug: two horizons must not agree."""
    short = _run(hold_on_strategy=5)
    long = _run(hold_on_strategy=40)
    assert len(short.trades) != len(long.trades)


def test_a_stop_hit_on_the_expiry_bar_still_counts_as_a_stop():
    """The stop is a resting order and executes intrabar; the time exit is a
    decision taken at the close. If the time exit won ties, losing trades would
    escape at the close and the measured result would flatter itself."""
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    px = 1.1000
    bars = []
    for i in range(30):
        # Bar 15 plunges through any stop placed below.
        if i == 15:
            o, c, lo, hi = px, px - 0.0010, px - 0.0100, px + 0.00005
        else:
            o, c, lo, hi = px, px, px - 0.00005, px + 0.00005
        bars.append(Candle(
            symbol="EURUSD", timeframe=TimeFrame.H1,
            open_time=t0 + timedelta(hours=i),
            open=round(o, 5), high=round(hi, 5), low=round(lo, 5),
            close=round(c, 5), volume=100.0))
        px = c

    class _TightStop(_AlwaysBuy):
        name = "_TightStop"

        def evaluate(self, ctx):
            sig = super().evaluate(ctx)
            if sig.side is not SignalSide.NO_TRADE:
                sig.stop_loss = round(sig.entry - 0.0050, 5)
            return sig

    strat = StrategyEngine()
    # Enters on bar 10 (warmup), expires on bar 15 -- the same bar the stop is
    # blown through.
    strat.register("_TightStop", _TightStop(max_hold_bars=5))
    strat.enable("_TightStop")
    engine = BacktestEngine(
        indicator_engine=IndicatorEngine(), strategy_engine=strat,
        cost_model=CostModel(spread_points=0.0, slippage_points=0.0,
                             commission_per_lot=0.0))
    res = engine.run(bars, "EURUSD", TimeFrame.H1, warmup=10, regime="Sideways")
    first = res.trades[0]
    assert first.bars_held == 5
    assert first.exit_reason == "SL", "the time exit must not rescue a stopped trade"
