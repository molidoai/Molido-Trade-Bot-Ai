"""Replay walks closed M15 bars with spread; does not invent a winrate."""

from datetime import datetime, timedelta, timezone

from molido_shared.types import Candle, TimeFrame
from molido_backtester.replay import replay_m15


def _synth(n: int = 120) -> list[Candle]:
    t0 = datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc)
    p = 1.1000
    out = []
    for i in range(n):
        o = p
        c = p + (0.0002 if i % 2 == 0 else -0.00015)
        out.append(
            Candle(
                symbol="EURUSD",
                timeframe=TimeFrame.M15,
                open_time=t0 + timedelta(minutes=15 * i),
                open=round(o, 5),
                high=round(max(o, c) + 0.0002, 5),
                low=round(min(o, c) - 0.0002, 5),
                close=round(c, 5),
                volume=50.0,
                is_closed=True,
            )
        )
        p = c
    return out


def test_replay_applies_spread_costs():
    candles = _synth()
    res = replay_m15(candles, spread_points=1.2, point_size=0.0001)
    assert res.bars == len(candles)
    assert res.cost_paid > 0
    if res.trades == 0:
        assert res.winrate is None
    else:
        assert 0.0 <= res.winrate <= 1.0
    res2 = replay_m15(candles, spread_points=1.2, point_size=0.0001)
    assert res.net_pnl == res2.net_pnl
    assert res.trades == res2.trades


def test_replay_no_lookahead_uses_closed_window():
    seen = []

    def sig(window, i):
        seen.append(len(window))
        assert len(window) == i + 1
        return None

    replay_m15(_synth(40), signal_fn=sig, hold_bars=2)
    assert seen
    assert seen[0] == 2 or seen[0] >= 2
