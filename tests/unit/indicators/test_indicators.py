"""Unit tests for Indicator Engine – verify no look-ahead and basic correctness."""

import pytest
from datetime import datetime, timedelta, timezone
from molido_shared.types import Candle, TimeFrame
from molido_indicators import (
    IndicatorEngine, EMA, RSI, ATR, BollingerBands, MACD, Supertrend, SwingPoints
)


def _make_candles(n: int = 100, start_price: float = 1.1000) -> list[Candle]:
    """Generate deterministic synthetic candles."""
    candles = []
    price = start_price
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        o = price
        c = price + (0.0001 if i % 3 != 0 else -0.00015)
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        candles.append(Candle(
            symbol="EURUSD",
            timeframe=TimeFrame.M15,
            open_time=t0 + timedelta(minutes=15 * i),
            open=round(o, 5),
            high=round(h, 5),
            low=round(l, 5),
            close=round(c, 5),
            volume=100.0,
        ))
        price = c
    return candles


def test_ema_length_and_none_prefix():
    candles = _make_candles(50)
    ind = EMA(period=10)
    results = ind.compute(candles)
    assert len(results) == 50
    # First 9 should be None
    for i in range(9):
        assert results[i].get("ema") is None
    assert results[9].get("ema") is not None
    assert results[-1].get("ema") is not None


def test_rsi_range():
    candles = _make_candles(80)
    ind = RSI(period=14)
    results = ind.compute(candles)
    for r in results:
        v = r.get("rsi")
        if v is not None:
            assert 0.0 <= v <= 100.0


def test_atr_positive():
    candles = _make_candles(60)
    ind = ATR(period=14)
    results = ind.compute(candles)
    for r in results:
        v = r.get("atr")
        if v is not None:
            assert v >= 0.0


def test_bollinger_order():
    candles = _make_candles(60)
    ind = BollingerBands(period=20, std_dev=2.0)
    results = ind.compute(candles)
    for r in results:
        mid = r.get("middle")
        upper = r.get("upper")
        lower = r.get("lower")
        if mid is not None:
            assert upper >= mid >= lower


def test_engine_registry_and_latest():
    engine = IndicatorEngine()
    engine.add_from_registry("EMA", "ema21", period=21)
    engine.add_from_registry("RSI", "rsi14", period=14)
    engine.add_from_registry("ATR", "atr14", period=14)

    candles = _make_candles(100)
    latest = engine.compute_latest(candles)

    assert "ema21" in latest
    assert "rsi14" in latest
    assert "atr14" in latest
    assert latest["ema21"].get("ema") is not None
    assert latest["rsi14"].get("rsi") is not None


def test_deterministic():
    """Same input must produce same output."""
    candles = _make_candles(40)
    ind = MACD()
    r1 = ind.compute(candles)
    r2 = ind.compute(candles)
    for a, b in zip(r1, r2):
        assert a.values == b.values


def test_no_lookahead_ema():
    """
    Truncating the series and recomputing must give the same value
    for the overlapping bars (classic look-ahead check).
    """
    candles = _make_candles(60)
    ind = EMA(period=10)
    full = ind.compute(candles)
    partial = ind.compute(candles[:40])
    for i in range(40):
        assert full[i].get("ema") == partial[i].get("ema")
