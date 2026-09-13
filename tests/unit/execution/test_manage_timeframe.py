"""Trade management must follow the bar size the entry was made on.

Entries sweep M15 and M5, or are pinned by the account setting. Management
read a separate field that was hardcoded to M15, so an M5 entry was managed on
M15 bars -- and since the holding horizon counts bars, the horizon was wrong
by the ratio between the two. Pinning an account to H1 had the same shape of
bug: entries moved, exits did not.
"""

import pytest

from molido_shared.types import TimeFrame
from molido_shared.journal import TradeJournal


def _journal(tmp_path):
    return TradeJournal(str(tmp_path / "j.jsonl"))


def test_timeframe_is_recorded_and_read_back(tmp_path):
    j = _journal(tmp_path)
    j.append("fill", ticket="111", symbol="XAUUSD", strategy="TrendFollowing",
             timeframe="H1")
    j.append("fill", ticket="222", symbol="EURUSD", strategy="RSIMeanReversion",
             timeframe="M5")
    assert j.timeframe_by_ticket() == {"111": "H1", "222": "M5"}


def test_a_fill_without_a_timeframe_is_simply_absent(tmp_path):
    """Fills written before this was tracked must not fabricate a value --
    the caller falls back, so an old position keeps the behaviour it was
    opened under instead of silently changing mid-trade."""
    j = _journal(tmp_path)
    j.append("fill", ticket="333", symbol="GBPUSD", strategy="DonchianBreakout")
    assert j.timeframe_by_ticket() == {}


def test_non_fill_events_are_ignored(tmp_path):
    j = _journal(tmp_path)
    j.append("veto", ticket="444", symbol="XAUUSD", timeframe="H4")
    j.append("skip", ticket="555", timeframe="D1")
    assert j.timeframe_by_ticket() == {}


@pytest.mark.parametrize("override,expected", [
    ("H1", TimeFrame.H1),
    ("h1", TimeFrame.H1),
    ("M5", TimeFrame.M5),
    ("AUTO", TimeFrame.M15),   # auto sweeps M15/M5 and opens on M15
    ("auto", TimeFrame.M15),
    (None, TimeFrame.M15),
    ("", TimeFrame.M15),
    ("NONSENSE", TimeFrame.M15),
])
def test_default_timeframe_follows_the_account_setting(override, expected):
    from app.live.runner import _default_timeframe
    assert _default_timeframe(override) is expected


def test_pinning_the_account_to_h1_moves_the_management_default():
    """The regression: an explicit H1 used to move entries only, leaving
    management on M15."""
    from app.live.runner import _default_timeframe
    assert _default_timeframe("H1") is not TimeFrame.M15
