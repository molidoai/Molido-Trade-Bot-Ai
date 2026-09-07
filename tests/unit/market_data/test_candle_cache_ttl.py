"""The candle cache must not serve stale bars.

It previously had no expiry of any kind: the first fetch of a
(symbol, timeframe) was returned unchanged for the life of the process. The
only reader is the H1 trend filter behind Brain1Setup's hard veto, so a frozen
series meant live signals were judged against a stale trend -- the cause of
30 of 30 XAUUSD BUY signals being vetoed as "against H1 filter (SELL)" on
2026-09-07 while the strategy was looking at a fresh up-cross.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "trading-engine"))

from app.data.market_data import MarketDataEngine
from molido_shared.types import Candle, TimeFrame


def _bars(close: float, n: int = 100) -> list[Candle]:
    t0 = datetime(2026, 9, 7, tzinfo=timezone.utc)
    return [
        Candle(symbol="XAUUSD", timeframe=TimeFrame.H1,
               open_time=t0 + timedelta(hours=i),
               open=close, high=close + 1, low=close - 1, close=close, volume=1.0)
        for i in range(n)
    ]


class _Broker:
    """Hands back a different price on every call, so a stale read is visible."""

    def __init__(self):
        self.calls = 0

    async def get_candles(self, symbol, timeframe, count=100):
        self.calls += 1
        return _bars(100.0 + self.calls)


def _engine():
    return MarketDataEngine(broker=_Broker(), symbols=["XAUUSD"])


@pytest.mark.asyncio
async def test_cache_is_reused_within_its_ttl():
    """The cache still has to do its job -- one series per cycle, not per call."""
    eng = _engine()
    a = await eng.get_candles("XAUUSD", TimeFrame.H1, count=80)
    b = await eng.get_candles("XAUUSD", TimeFrame.H1, count=80)
    assert a[-1].close == b[-1].close
    assert eng.broker.calls == 1


@pytest.mark.asyncio
async def test_cache_expires_and_refetches():
    """Past the TTL the bars must come from the broker again, not from memory."""
    eng = _engine()
    first = await eng.get_candles("XAUUSD", TimeFrame.H1, count=80)

    # Age the entry past its TTL rather than sleeping.
    bars, fetched_at = eng._candle_cache[("XAUUSD", TimeFrame.H1)]
    ttl = MarketDataEngine._cache_ttl(TimeFrame.H1)
    eng._candle_cache[("XAUUSD", TimeFrame.H1)] = (bars, fetched_at - ttl - 1.0)

    second = await eng.get_candles("XAUUSD", TimeFrame.H1, count=80)
    assert eng.broker.calls == 2
    assert second[-1].close != first[-1].close, "stale bars were served after the TTL"


@pytest.mark.asyncio
async def test_uncached_fetch_refreshes_the_stored_timestamp():
    """use_cache=False writes through; the entry it leaves must look fresh."""
    eng = _engine()
    await eng.get_candles("XAUUSD", TimeFrame.H1, count=80)
    bars, fetched_at = eng._candle_cache[("XAUUSD", TimeFrame.H1)]
    eng._candle_cache[("XAUUSD", TimeFrame.H1)] = (bars, fetched_at - 999.0)

    fresh = await eng.get_candles("XAUUSD", TimeFrame.H1, count=160, use_cache=False)
    cached, _ = eng._candle_cache[("XAUUSD", TimeFrame.H1)]
    assert cached[-1].close == fresh[-1].close

    again = await eng.get_candles("XAUUSD", TimeFrame.H1, count=80)
    assert again[-1].close == fresh[-1].close
    assert eng.broker.calls == 2, "the write-through entry should still be reusable"


def test_ttl_is_bounded_for_every_timeframe():
    """A bound that is hours long would reintroduce the bug it was added to stop."""
    for tf in TimeFrame:
        ttl = MarketDataEngine._cache_ttl(tf)
        assert 5.0 <= ttl <= 30.0, f"{tf} ttl {ttl} outside the bound"
