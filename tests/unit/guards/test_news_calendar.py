from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from molido_guards import (
    NewsBlackoutGuard,
    CalendarEvent,
    static_high_impact_events,
    in_fail_closed_window,
    refresh_calendar,
)

NY = ZoneInfo("America/New_York")


def test_set_events_still_blocks():
    g = NewsBlackoutGuard(minutes_before=15, minutes_after=15)
    now = datetime.now(timezone.utc)
    g.set_events([CalendarEvent("NFP", "USD", "high", now + timedelta(minutes=5))])
    ok, reason = g.allow_new_entries("EURUSD", now)
    assert ok is False
    assert "NFP" in reason


def test_stale_fail_closed_us_data_hour(tmp_path):
    g = NewsBlackoutGuard(calendar_path=str(tmp_path / "cal.json"))
    now = datetime(2026, 8, 26, 8, 30, tzinfo=NY)  # Wednesday 08:30 NY
    ok, reason = g.allow_new_entries("EURUSD", now)
    assert ok is False
    assert "fail-closed" in reason


def test_stale_allow_outside_high_impact_hours(tmp_path):
    g = NewsBlackoutGuard(calendar_path=str(tmp_path / "cal.json"))
    now = datetime(2026, 8, 26, 21, 0, tzinfo=NY)  # Wednesday evening NY
    ok, reason = g.allow_new_entries("EURUSD", now)
    assert ok is True


def test_static_table_has_nfp():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    events = static_high_impact_events(now=now, days=14)
    titles = " ".join(e.title.lower() for e in events)
    assert "payroll" in titles or "nfp" in titles or "cpi" in titles or "fomc" in titles or "rate" in titles


def test_refresh_writes_file(tmp_path):
    path = tmp_path / "news_calendar.json"
    payload = refresh_calendar(path=str(path), url="")
    assert path.exists()
    assert payload["source"] in ("static", "static-fallback")
    assert isinstance(payload["events"], list)
    g = NewsBlackoutGuard(calendar_path=str(path))
    assert g.load_from_disk()
    assert g.is_stale() is False
