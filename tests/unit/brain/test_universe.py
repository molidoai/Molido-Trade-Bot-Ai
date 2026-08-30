from molido_brain.universe import (
    DEFAULT_UNIVERSE,
    UniversePicker,
    CheapCandidate,
    resolve_universe,
    resolve_trade_timeframe,
    cheap_score,
)
from molido_shared.types import TimeFrame


def test_auto_and_empty_use_universe():
    assert resolve_universe("auto") == list(DEFAULT_UNIVERSE)
    assert resolve_universe("") == list(DEFAULT_UNIVERSE)
    assert resolve_universe("EURUSD, GBPUSD") == ["EURUSD", "GBPUSD"]
    assert "XAUUSD" in DEFAULT_UNIVERSE
    assert "EURGBP" in DEFAULT_UNIVERSE
    assert len(DEFAULT_UNIVERSE) == 11


def test_never_m1_auto_m15_primary():
    assert resolve_trade_timeframe("AUTO", overlap=False, spread_ok=True) == TimeFrame.M15
    assert resolve_trade_timeframe("M1", overlap=True, spread_ok=True) == TimeFrame.M15
    assert resolve_trade_timeframe("auto", overlap=True, spread_ok=True) == TimeFrame.M5
    assert resolve_trade_timeframe("AUTO", overlap=True, spread_ok=False) == TimeFrame.M15


def test_picker_caps_new_and_skips_open():
    picker = UniversePicker(max_new=2, max_open=3)
    rows = [
        CheapCandidate("EURUSD", 3.0),
        CheapCandidate("GBPUSD", 2.5),
        CheapCandidate("USDJPY", 2.0),
        CheapCandidate("XAUUSD", -1.0),
    ]
    picked = picker.select(picker.rank(rows), open_symbols=["EURUSD"])
    assert [p.symbol for p in picked] == ["GBPUSD", "USDJPY"]
    picked2 = picker.select(picker.rank(rows), open_symbols=["EURUSD", "GBPUSD", "USDCHF"])
    assert picked2 == []


def test_wide_spread_skipped():
    score, reasons, ok = cheap_score(
        session_ok=True, overlap=True, spread=0.01, mid=1.10, h1_side="BUY"
    )
    assert score < 0
    assert ok is False
