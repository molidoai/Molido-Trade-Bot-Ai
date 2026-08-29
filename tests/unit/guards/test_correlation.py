from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from molido_guards.correlation import correlated_block
from molido_guards.sessions import SessionCalendar


def test_correlated_block_eur_cluster():
    ok, why = correlated_block("GBPUSD", ["EURUSD"])
    assert ok is False
    assert "correlated" in why


def test_uncorrelated_ok():
    ok, why = correlated_block("XAUUSD", ["EURUSD"])
    assert ok is True


def test_thursday_after_16_ny_blocks():
    cal = SessionCalendar()
    thu = datetime(2024, 1, 4, 21, 5, tzinfo=timezone.utc)
    assert thu.astimezone(ZoneInfo("America/New_York")).weekday() == 3
    ok, why = cal.allow_new_entries(thu)
    assert ok is False
    assert "Thursday" in why


def test_friday_flatten():
    cal = SessionCalendar()
    fri = datetime(2024, 1, 5, 21, 5, tzinfo=timezone.utc)
    yes, why = cal.should_flatten(fri)
    assert yes is True
    assert "Friday" in why
