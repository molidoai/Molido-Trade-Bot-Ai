"""Tests for Signal Engine scoring and thresholding."""

from datetime import datetime, timezone
from molido_shared.types import TimeFrame
from molido_strategies.base import StrategySignal, SignalSide
from molido_signals import SignalEngine, ScoringWeights
from molido_indicators.base import IndicatorResult


def _raw(side=SignalSide.BUY, conf=70.0, sl=1.07, tp=1.10, rr=2.0) -> StrategySignal:
    return StrategySignal(
        symbol="EURUSD",
        side=side,
        timeframe=TimeFrame.H1,
        strategy_name="TrendFollowing",
        timestamp=datetime.now(timezone.utc),
        entry=1.0850,
        stop_loss=sl,
        take_profit=tp,
        confidence=conf,
        score=conf,
        reasons=["EMA cross"],
        market_regime="Bull",
        risk_reward=rr,
    )


def test_accept_above_threshold():
    engine = SignalEngine(accept_threshold=50.0)
    indicators = {
        "MultiEMA": IndicatorResult(values={"ema_9": 1.086, "ema_21": 1.084, "ema_50": 1.080}),
        "RSI": IndicatorResult(values={"rsi": 55.0}),
        "ATR": IndicatorResult(values={"atr": 0.0012}),
        "MACD": IndicatorResult(values={"histogram": 0.0001}),
    }
    finals = engine.process([_raw()], indicators=indicators, mtf_factor=0.7, volume_factor=0.6)
    assert len(finals) == 1
    assert finals[0].side == SignalSide.BUY
    assert "score_breakdown" in finals[0].__dict__ or finals[0].score_breakdown
    assert finals[0].score > 0


def test_reject_missing_sl():
    engine = SignalEngine(accept_threshold=40.0, require_sl=True)
    raw = _raw(sl=None)
    finals = engine.process([raw], indicators={})
    assert finals[0].accepted is False
    assert finals[0].reject_reason is not None
    assert "Stop-Loss" in (finals[0].reject_reason or "")


def test_reject_low_rr():
    engine = SignalEngine(accept_threshold=40.0, min_rr=1.5)
    raw = _raw(rr=1.0)
    finals = engine.process([raw], indicators={})
    assert finals[0].accepted is False


def test_no_trade_passthrough():
    engine = SignalEngine()
    raw = StrategySignal(
        symbol="EURUSD",
        side=SignalSide.NO_TRADE,
        timeframe=TimeFrame.H1,
        strategy_name="TrendFollowing",
        reasons=["Regime not allowed"],
    )
    finals = engine.process([raw])
    assert finals[0].side == SignalSide.NO_TRADE
    assert finals[0].accepted is False


def test_exit_accepted():
    engine = SignalEngine()
    raw = StrategySignal(
        symbol="EURUSD",
        side=SignalSide.EXIT,
        timeframe=TimeFrame.H1,
        strategy_name="TrendFollowing",
        confidence=80.0,
        reasons=["EMA cross exit"],
    )
    finals = engine.process([raw])
    assert finals[0].accepted is True
    assert finals[0].side == SignalSide.EXIT
