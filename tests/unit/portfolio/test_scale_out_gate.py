"""Break-even / partial / trail must be off unless explicitly enabled.

Walk-forward in the live configuration: fixed 3R exits PF 1.27, +1343, 15/22
folds; this scale-out PF 1.18, +795, 10/22 folds. Live ran the scale-out while
every published result assumed fixed exits.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for pkg in ("portfolio", "shared", "broker"):
    sys.path.insert(0, str(ROOT / "packages" / pkg))

from molido_portfolio.trade_manager import TradeManager


class Broker:
    def __init__(self):
        self.modified, self.closed = [], []

    async def modify_position(self, ticket, sl=None, tp=None):
        self.modified.append((ticket, sl))
        return True

    async def close_position(self, ticket, volume=None):
        self.closed.append((ticket, volume))
        return SimpleNamespace(success=True)


class Positions:
    def __init__(self, pos):
        self.pos = pos

    def by_symbol(self, symbol):
        return [self.pos]

    def get_all(self):
        return [self.pos]


def position():
    return SimpleNamespace(ticket=1, side="BUY", entry_price=100.0, stop_loss=90.0,
                           take_profit=130.0, volume=0.10,
                           opened_at=datetime(2026, 9, 7, tzinfo=timezone.utc))


def run(tm, price):
    return asyncio.run(tm.manage_symbol("XAUUSD", candles=None, atr=2.0, timeframe="1h", price=price))


def test_off_by_default_nothing_is_touched_even_at_two_r():
    broker = Broker()
    tm = TradeManager(broker, Positions(position()))
    assert tm.scale_out is False
    run(tm, 120.0)
    assert broker.modified == [] and broker.closed == []


def test_on_moves_stop_to_entry_and_closes_half_at_one_r():
    broker = Broker()
    tm = TradeManager(broker, Positions(position()))
    tm.scale_out = True
    run(tm, 110.0)
    assert (1, 100.0) in broker.modified
    assert (1, 0.05) in broker.closed


def test_below_one_r_nothing_happens_either_way():
    for flag in (False, True):
        broker = Broker()
        tm = TradeManager(broker, Positions(position()))
        tm.scale_out = flag
        run(tm, 105.0)
        assert broker.modified == [] and broker.closed == []
