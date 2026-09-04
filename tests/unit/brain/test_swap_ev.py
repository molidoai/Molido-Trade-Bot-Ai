from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from molido_brain.swap import overnight_swap_r, veto_weekend_hold, HEAVY_NEGATIVE_SWAP_R
from molido_brain import DecisionBrain
from molido_signals.engine import FinalSignal
from molido_strategies.base import SignalSide

NY = ZoneInfo("America/New_York")


def test_thursday_multiplies_weekend_swap():
    now = datetime(2026, 8, 27, 15, 0, tzinfo=NY)  # Thursday
    r = overnight_swap_r(now=now, base=0.03)
    assert r == 0.09


def test_heavy_negative_thursday_veto():
    now = datetime(2026, 8, 27, 15, 0, tzinfo=NY)
    ok, why = veto_weekend_hold(0.09, now)
    assert ok is True
    assert "Thursday" in why
    assert HEAVY_NEGATIVE_SWAP_R <= 0.09


def test_brain_ev_subtracts_swap():
    b = DecisionBrain()
    sig = FinalSignal(
        symbol="EURUSD",
        side=SignalSide.EXIT,
        timeframe="15m",
        strategy="TrendFollowing",
        timestamp=datetime(2026, 8, 27, 15, 0, tzinfo=NY),
        entry=1.08,
        stop_loss=1.07,
        take_profit=1.10,
        score=80,
        risk_reward=2,
        accepted=True,
    )
    # Pinned like the rest: an unpinned decide() reads the wall clock, and
    # the weekend-swap veto then makes the result depend on the weekday.
    d = b.decide(sig, now=datetime(2024, 1, 3, 13, 0, tzinfo=timezone.utc))
    assert d.allow is True
