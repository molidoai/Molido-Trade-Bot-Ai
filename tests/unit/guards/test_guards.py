from datetime import datetime, timezone, timedelta
from molido_guards import TradingHoursGuard, NewsBlackoutGuard, CalendarEvent, MasterSwitchStore
from molido_guards.config_drift import ConfigDriftDetector
from molido_regime import MarketRegimeEngine
from molido_shared.types import Candle, TimeFrame


def test_weekend_block():
    g = TradingHoursGuard(block_weekends=True)
    sat = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
    ok, reason = g.allow_new_entries(sat)
    assert ok is False


def test_news_blackout():
    g = NewsBlackoutGuard(minutes_before=15, minutes_after=15)
    now = datetime.now(timezone.utc)
    g.set_events([CalendarEvent("NFP", "USD", "high", now + timedelta(minutes=5))])
    ok, reason = g.allow_new_entries("EURUSD", now)
    assert ok is False
    assert "NFP" in reason


def test_master_switch_real_confirm():
    store = MasterSwitchStore()
    try:
        store.set_mode("REAL", confirm_token="wrong")
        assert False
    except PermissionError:
        pass
    st = store.set_mode("REAL", confirm_token="CONFIRM_REAL")
    assert st.account_mode == "REAL"


def test_config_drift():
    d = ConfigDriftDetector()
    d.set_baseline({"risk": 0.005, "mode": "DEMO"})
    r = d.check({"risk": 0.01, "mode": "DEMO"})
    assert r.drifted is True


def test_regime():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    p = 1.1
    for i in range(60):
        candles.append(Candle("EURUSD", TimeFrame.H1, t0, p, p + 0.001, p - 0.001, p + 0.0005, 1))
        p += 0.0003
    r = MarketRegimeEngine().classify(candles)
    assert isinstance(r, str)
