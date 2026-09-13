"""The backtest must be able to run the decision layer the live bot runs.

Without this the backtester measured the strategy while the bot traded a
brain-selected subset of it: 7,291 of 9,196 recorded vetoes came from the
brain layer against 264 accepts, so a backtest reporting 267 trades described
roughly thirty times more trading than the bot would do, chosen differently.
Every profit factor produced that way describes a system nobody is running.
"""

from datetime import datetime, timedelta, timezone

from molido_shared.types import Candle, TimeFrame
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide
from molido_backtester import BacktestEngine, CostModel


def _candles(n: int = 160) -> list[Candle]:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    px, out = 1.1000, []
    for i in range(n):
        o = px
        c = px + (0.0004 if i % 3 else -0.0002)
        out.append(Candle(symbol="EURUSD", timeframe=TimeFrame.M15,
                          open_time=t0 + timedelta(minutes=15 * i),
                          open=round(o, 5), high=round(max(o, c) + 0.0003, 5),
                          low=round(min(o, c) - 0.0003, 5), close=round(c, 5),
                          volume=100.0))
        px = c
    return out


class _AlwaysBuy(Strategy):
    name = "_AlwaysBuy"
    strategy_type = "test"
    allowed_regimes = ["Bull", "Bear", "Strong Bull", "Strong Bear",
                       "Sideways", "Low Volatility", "High Volatility"]

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        if ctx.open_position_side is not None or not ctx.candles:
            return StrategySignal(symbol=ctx.symbol, side=SignalSide.NO_TRADE,
                                  timeframe=ctx.timeframe, strategy_name=self.name)
        px = ctx.candles[-1].close
        return StrategySignal(
            symbol=ctx.symbol, side=SignalSide.BUY, timeframe=ctx.timeframe,
            strategy_name=self.name, entry=px,
            stop_loss=round(px - 0.0050, 5), take_profit=round(px + 0.0150, 5),
            confidence=90.0, score=90.0)


class _Verdict:
    def __init__(self, allow, size_mult=1.0):
        self.allow, self.size_mult = allow, size_mult
        self.p_win, self.expected_r, self.reasons, self.votes = 0.6, 0.5, [], []


class _Brain:
    def __init__(self, allow=True, size_mult=1.0):
        self._allow, self._mult = allow, size_mult
        self.calls = 0

    def decide(self, signal, **kw):
        self.calls += 1
        self.seen = kw
        return _Verdict(self._allow, self._mult)


class _ExplodingBrain:
    def decide(self, signal, **kw):
        raise RuntimeError("brain is broken")


def _run(brain):
    strat = StrategyEngine()
    strat.register("_AlwaysBuy", _AlwaysBuy())
    strat.enable("_AlwaysBuy")
    eng = BacktestEngine(
        indicator_engine=IndicatorEngine(), strategy_engine=strat,
        cost_model=CostModel(spread_points=0.0, slippage_points=0.0,
                             commission_per_lot=0.0),
        brain=brain)
    return eng.run(_candles(), "EURUSD", TimeFrame.M15, warmup=20,
                   regime="Sideways"), eng


def test_without_a_brain_nothing_changes():
    res, _ = _run(None)
    assert res.trades, "the baseline must still trade"


def test_an_approving_brain_is_consulted_and_lets_trades_through():
    res, _ = _run(_Brain(allow=True))
    assert res.trades


def test_a_vetoing_brain_stops_every_trade():
    res, _ = _run(_Brain(allow=False))
    assert res.trades == [], "a veto must prevent entries, not merely resize"


def test_zero_size_counts_as_a_veto():
    """The live path treats size_mult <= 0 as a refusal; so must this."""
    res, _ = _run(_Brain(allow=True, size_mult=0.0))
    assert res.trades == []


def test_a_throwing_brain_vetoes_rather_than_approves():
    """A crashing brain must not silently restore no-brain numbers."""
    res, _ = _run(_ExplodingBrain())
    assert res.trades == []


def test_the_brain_receives_the_context_it_needs_to_veto_on_trend():
    """The hardest live veto is 'against H1 filter'. If h1_side never reaches
    the brain, the backtest approves trades the bot refuses."""
    _, eng = _run(_Brain(allow=True))
    assert "h1_side" in eng.brain.seen
    assert "regime" in eng.brain.seen
    assert "candles" in eng.brain.seen
