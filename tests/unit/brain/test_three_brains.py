from molido_brain import DecisionBrain, Brain1Setup, Brain2Edge, Brain3Survival, clamp_size
from molido_signals.engine import FinalSignal
from molido_strategies.base import SignalSide
from datetime import datetime, timezone


def _sig(**kw):
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


def test_clamp_size_never_enlarges():
    assert clamp_size(2.0) == 1.0
    assert clamp_size(0.7) == 1.0
    assert clamp_size(0.4) == 0.5
    assert clamp_size(0.0) == 0.0
    assert clamp_size(-1) == 0.0


def test_brain1_vetoes_against_h1():
    b = DecisionBrain()
    d = b.decide(_sig(), h1_side="SELL")
    assert d.allow is False
    assert d.size_mult == 0.0
    assert any(v.name == "setup" and not v.allow for v in d.votes)


def test_brain1_vetoes_session_closed():
    b = DecisionBrain()
    d = b.decide(_sig(), h1_side="BUY", spread=0.00005, session_ok=False)
    assert d.allow is False
    assert any("session" in r.lower() for r in d.reasons)


def test_brain1_vetoes_bad_universe_score():
    b = DecisionBrain()
    d = b.decide(_sig(), h1_side="BUY", spread=0.00005, universe_score=-1.0)
    assert d.allow is False
    assert any("universe" in r.lower() for r in d.reasons)


def test_brain3_vetoes_correlation():
    b = DecisionBrain(min_p=0.0, min_ev=-10.0)
    d = b.decide(
        _sig(),
        h1_side="BUY",
        spread=0.00005,
        open_symbols=["GBPUSD"],
        symbol="EURUSD",
    )
    assert d.allow is False
    assert any("correlat" in r.lower() for r in d.reasons)
    assert any(v.name == "survival" and not v.allow for v in d.votes)


def test_brain3_vetoes_daily_loss():
    b = DecisionBrain(min_p=0.0, min_ev=-10.0)
    d = b.decide(
        _sig(),
        h1_side="BUY",
        spread=0.00005,
        daily_pnl=-250.0,
        equity=10_000.0,
        daily_loss_limit=0.02,
        open_symbols=[],
    )
    assert d.allow is False
    assert any("daily loss" in r.lower() for r in d.reasons)
    assert any(v.name == "survival" and not v.allow for v in d.votes)


def test_series_min_size_not_enlarge():
    b = DecisionBrain()
    d = b.decide(_sig(), h1_side="BUY", spread=0.00005, open_symbols=[])
    assert d.size_mult in (0.0, 0.5, 1.0)


def test_no_llm_direction_api():
    assert not hasattr(DecisionBrain, "chat")
    assert not hasattr(Brain1Setup, "llm")
    assert not hasattr(Brain2Edge, "llm")
    assert not hasattr(Brain3Survival, "llm")
