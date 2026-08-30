from datetime import datetime, timedelta, timezone
from molido_shared.types import Candle, TimeFrame
from molido_shared.point_in_time import closed_bars, InsufficientDataError
from molido_shared.data_quality import score_candles


def _bars(n=40, closed=True):
    t0 = datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc)
    p = 1.08
    out = []
    for i in range(n):
        o = p
        c = p + 0.0001
        out.append(
            Candle(
                "EURUSD", TimeFrame.M15, t0 + timedelta(minutes=15 * i),
                o, max(o, c) + 0.0001, min(o, c) - 0.0001, c, 10,
                is_closed=closed,
            )
        )
        p = c
    return out


def test_closed_bars_drops_forming_candle():
    bars = _bars(40)
    as_of = bars[-1].open_time + timedelta(minutes=7)  # mid bar
    closed = closed_bars(bars, as_of=as_of, min_bars=10)
    assert closed[-1].open_time < bars[-1].open_time or (
        bars[-1].open_time + timedelta(minutes=15) <= as_of
    )


def test_insufficient_data():
    try:
        closed_bars(_bars(5), min_bars=30)
        assert False
    except InsufficientDataError:
        pass


def test_quality_refuses_junk():
    bars = _bars(40)
    bars[10] = Candle("EURUSD", TimeFrame.M15, bars[10].open_time, 1, 0.5, 2, 1, 1)
    report = score_candles(bars)
    assert report.tradeable is False
    assert report.findings


def test_quality_ok_on_clean():
    report = score_candles(_bars(40))
    assert report.tradeable is True
