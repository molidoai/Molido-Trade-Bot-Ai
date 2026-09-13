"""compute_latest works on a bounded tail; prove that changes no value.

It used to pass the whole series to compute_all on every call and keep only
the last element, which made a per-bar backtest O(n^2) -- one study row over
12,500 H1 bars took about an hour. Bounding the window is what makes the
research queue tractable, but EMA, Wilder ATR and Supertrend are recursive and
therefore depend, in principle, on every bar that came before. So the bound is
only legitimate if the numbers it produces are the numbers full history would
have produced.

That is what this file checks, on a synthetic series with trend, noise and a
regime break, at many positions, for every indicator the live engine enables.
"""

import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "indicators"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "shared"))

from molido_indicators.engine import IndicatorEngine
from molido_shared.types import Candle, TimeFrame


def series(n: int = 6000) -> list[Candle]:
    """Trend, noise, and a regime break, so a truncated window has something
    to get wrong if it is going to."""
    rnd = random.Random(20260908)
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = 1000.0
    for i in range(n):
        drift = 0.35 if i < n // 2 else -0.2          # the break
        price = max(1.0, price + drift + rnd.gauss(0, 4.0))
        hi = price + abs(rnd.gauss(0, 2.0))
        lo = price - abs(rnd.gauss(0, 2.0))
        op = lo + (hi - lo) * rnd.random()
        out.append(Candle(symbol="TEST", timeframe=TimeFrame.H1,
                          open_time=t0 + timedelta(hours=i),
                          open=op, high=hi, low=lo, close=price,
                          volume=float(rnd.randint(1, 1000))))
    return out


def engine() -> IndicatorEngine:
    """Exactly what the live engine and the studies enable."""
    ind = IndicatorEngine()
    for name, kw in (("MultiEMA", {}), ("RSI", {"period": 14}), ("ATR", {"period": 14}),
                     ("DonchianChannel", {"period": 20}), ("BollingerBands", {"period": 20}),
                     ("MACD", {}), ("Supertrend", {"period": 10, "multiplier": 3.0})):
        ind.add_from_registry(name, **kw)
    return ind


BARS = series()


def _full_latest(eng: IndicatorEngine, candles):
    """What compute_latest did before: whole series, keep the last."""
    return {n: r[-1] for n, r in eng.compute_all(candles).items() if r}


@pytest.mark.parametrize("upto", [1600, 2500, 3500, 4200, 5000, 6000])
def test_bounded_tail_matches_full_history(upto):
    eng = engine()
    window = BARS[:upto]
    bounded = eng.compute_latest(window)
    full = _full_latest(eng, window)

    assert set(bounded) == set(full), "an indicator vanished under the bound"

    for name in full:
        got, want = bounded[name].values, full[name].values
        assert set(got) == set(want), f"{name}: different keys"
        for key in want:
            a, b = got[key], want[key]
            if a is None or b is None:
                assert a is b, f"{name}.{key}: {a!r} vs {b!r}"
                continue
            scale = max(1.0, abs(b))
            assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6 * scale), (
                f"{name}.{key} drifted at {upto} bars: bounded={a!r} full={b!r}"
            )


def test_the_window_is_actually_bounded():
    """If the tail still grows with history, the O(n^2) cost is still there."""
    eng = engine()
    long_tail = eng._tail(BARS)                 # 6000 bars available
    longer = eng._tail(BARS + BARS)             # 12000
    assert len(long_tail) == len(longer), "window grew with the series"
    assert len(long_tail) < len(BARS), "no truncation happened at all"


def test_short_series_is_passed_through_untouched():
    eng = engine()
    short = BARS[:200]
    assert len(eng._tail(short)) == 200


def test_tail_covers_the_longest_lookback():
    """MultiEMA defaults to a 200 period; a window under that returns nothing."""
    eng = engine()
    need = max(i.required_bars for i in eng._indicators.values())
    assert len(eng._tail(BARS)) >= need * 10
