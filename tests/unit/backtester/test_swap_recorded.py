"""Financing must be recorded on the trade, not only folded into pnl_net.

It was computed and subtracted at all three close paths but never stored, so
no study could attribute it. A long-vs-short comparison duly printed
"total financing charged: -0.0" and read as though swap had never been
applied -- while it had been, the whole time. A cost you cannot see is a cost
you will eventually re-derive wrongly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "backtester"))

from molido_backtester.models import BacktestTrade
from molido_backtester.costs import CostModel


def test_trade_has_a_swap_field_defaulting_to_zero():
    from datetime import datetime, timezone
    t = BacktestTrade(
        symbol="XAUUSD", side="BUY",
        entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc), exit_time=None,
        entry_price=4400.0, exit_price=None, volume=0.1,
        stop_loss=None, take_profit=None,
    )
    assert hasattr(t, "swap") and t.swap == 0.0


def test_every_close_path_populates_it():
    """Three paths close a position; all three must record the charge."""
    src = (Path(__file__).resolve().parents[3]
           / "packages" / "backtester" / "molido_backtester" / "engine.py").read_text(encoding="utf-8")
    assert src.count("swap=swap,") == 3, "a close path is not recording financing"
    assert src.count("swap = cost.swap_cost(") == 3


def test_the_sign_convention_is_a_positive_cost():
    """swap_cost returns a positive number that is then subtracted."""
    from datetime import datetime, timedelta, timezone
    cm = CostModel(spread_points=5.0)
    cm.swap_long_points, cm.swap_short_points = -60.0, 19.0
    cm = cm.for_symbol("XAUUSD")
    entry = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    exit_ = entry + timedelta(days=1)
    charged = cm.swap_cost("BUY", 1.0, entry, exit_)
    earned = cm.swap_cost("SELL", 1.0, entry, exit_)
    assert charged > 0, "a long paying -60 points should be a positive cost"
    assert earned < 0, "a short earning +19 points should be a negative cost"
