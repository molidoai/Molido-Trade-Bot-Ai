"""Brain gate: veto / size_mult never > 1, no LLM direction."""

from datetime import datetime, timedelta, timezone

from molido_brain import DecisionBrain, BrainDecision
from molido_signals.engine import FinalSignal
from molido_strategies.base import SignalSide
from molido_shared.types import Candle, TimeFrame

# A fixed clock. The weekend-swap veto reads the wall clock when no `now` is
# given, so on a Friday it fires first and masks whatever a test was actually
# checking -- these tests passed Monday to Thursday and failed on Friday.
# Wednesday is chosen because it trips neither the Thursday-NY nor the Friday
# branch of veto_weekend_hold.
MIDWEEK = datetime(2024, 1, 3, 13, 0, tzinfo=timezone.utc)



def _sig(**kw) -> FinalSignal:
    d = dict(
        symbol="EURUSD",
        side=SignalSide.BUY,
        timeframe="15m",
        strategy="TrendFollowing",
        timestamp=datetime(2024, 1, 3, 15, 0, tzinfo=timezone.utc),
        entry=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        score=80.0,
        risk_reward=2.0,
        accepted=True,
        market_regime="Bull",
    )
    d.update(kw)
    return FinalSignal(**d)


def _candles(n: int = 80, start=1.08, step=0.0002) -> list[Candle]:
    t0 = datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc)
    p = start
    out = []
    for i in range(n):
        o = p
        c = p + step
        out.append(
            Candle(
                symbol="EURUSD",
                timeframe=TimeFrame.M15,
                open_time=t0 + timedelta(minutes=15 * i),
                open=o,
                high=max(o, c) + 0.0003,
                low=min(o, c) - 0.0003,
                close=c,
                volume=100,
                is_closed=True,
            )
        )
        p = c
    return out


def test_exit_always_allowed():
    b = DecisionBrain()
    d = b.decide(_sig(side=SignalSide.EXIT), now=MIDWEEK)
    assert d.allow is True
    assert d.size_mult == 1.0


def test_against_h1_hard_veto():
    b = DecisionBrain()
    d = b.decide(_sig(side=SignalSide.BUY), h1_side="SELL", candles=_candles(), now=MIDWEEK)
    assert d.allow is False
    assert d.size_mult == 0.0
    assert any("H1" in r for r in d.reasons)


def test_spread_vs_stop_veto():
    b = DecisionBrain()
    d = b.decide(_sig(), spread=0.002, candles=_candles(), now=MIDWEEK)
    assert d.allow is False
    assert any("spread" in r.lower() for r in d.reasons)


def test_journal_negative_expectancy_veto():
    b = DecisionBrain(pause_on_negative_journal=True)
    d = b.decide(
        _sig(),
        journal_stats={"mean_r": -0.2, "n": 20},
        candles=_candles(),
        h1_side="BUY",
        spread=0.0001, now=MIDWEEK)
    assert d.allow is False
    assert d.size_mult == 0.0
    assert any("journal" in r.lower() or "expectancy" in r.lower() for r in d.reasons)


def test_size_mult_never_above_one():
    b = DecisionBrain()
    d = b.decide(_sig(), candles=_candles(), h1_side="BUY", spread=0.00005, now=MIDWEEK)
    assert d.size_mult <= 1.0
    assert d.size_mult in (0.0, 0.5, 1.0)


def test_dead_atr_veto():
    b = DecisionBrain()
    candles = []
    t0 = datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc)
    p = 1.1000
    for i in range(80):
        candles.append(
            Candle(
                symbol="EURUSD",
                timeframe=TimeFrame.M15,
                open_time=t0 + timedelta(minutes=15 * i),
                open=p,
                high=p + 0.0000001,
                low=p - 0.0000001,
                close=p,
                volume=1.0,
                is_closed=True,
            )
        )
    d = b.decide(_sig(entry=1.10, stop_loss=1.0990), candles=candles, h1_side="BUY", spread=0.0, now=MIDWEEK)
    assert d.allow is False
    assert any("dead" in r.lower() or "ATR" in r for r in d.reasons)


def test_unknown_high_vol_veto():
    b = DecisionBrain()
    candles = _candles(80, start=1.08, step=0.01)
    d = b.decide(
        _sig(market_regime="Unknown", entry=candles[-1].close, stop_loss=candles[-1].close - 0.02),
        regime="Unknown",
        candles=candles,
        h1_side="BUY",
        spread=0.0001, now=MIDWEEK)
    assert d.allow is False
    assert any("unknown" in r.lower() for r in d.reasons)


def test_compatible_positional_args():
    b = DecisionBrain()
    d = b.decide(_sig(), {}, "Bull", 1, now=MIDWEEK)
    assert isinstance(d, BrainDecision)
    assert d.size_mult <= 1.0
