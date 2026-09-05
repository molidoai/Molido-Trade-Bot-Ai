"""The live holding-horizon exit.

The backtester closes a StrengthReversion position after the 32 bars its edge
was measured over. If the live bot does not do the same thing, the study is
measuring a bet the bot does not place. These tests pin the two together.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from molido_portfolio.trade_manager import TradeManager
from molido_shared.journal import TradeJournal


class _Pos:
    def __init__(self, ticket, symbol="EURUSD", side="BUY", opened_at=None):
        self.ticket = ticket
        self.symbol = symbol
        self.side = side
        self.volume = 0.10
        self.entry_price = 1.1000
        self.stop_loss = 1.0950
        self.take_profit = 1.1100
        self.opened_at = opened_at


class _Broker:
    def __init__(self):
        self.closed = []

    async def close_position(self, ticket, volume=None):
        self.closed.append((ticket, volume))
        return type("R", (), {"success": True, "message": "ok"})()

    async def modify_position(self, ticket, sl=None, tp=None):
        return True


class _Positions:
    def __init__(self, positions):
        self._p = positions

    def get_all(self):
        return list(self._p)

    def by_symbol(self, symbol):
        return [p for p in self._p if p.symbol == symbol]


class _Strat:
    def __init__(self, max_hold_bars):
        self.max_hold_bars = max_hold_bars


class _Strategies:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, name):
        return self._m.get(name)


class _Candle:
    def __init__(self, t):
        self.open_time = t
        self.close = 1.1000
        self.high = 1.1005
        self.low = 1.0995


def _candles(n, start):
    return [_Candle(start + timedelta(minutes=15 * i)) for i in range(n)]


def _journal_with(tmp_path, ticket, strategy):
    j = TradeJournal(path=str(tmp_path / "journal.jsonl"))
    j.append("fill", ticket=ticket, strategy=strategy, symbol="EURUSD",
             risk_amount=50.0, entry=1.1000, stop_loss=1.0950)
    return j


def _mgr(tmp_path, horizon, ticket="777", strategy="StrengthReversion",
         positions=None):
    broker = _Broker()
    pos = positions or [_Pos(ticket, opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc))]
    mgr = TradeManager(
        broker, _Positions(pos),
        journal=_journal_with(tmp_path, ticket, strategy),
        strategies=_Strategies({strategy: _Strat(horizon)}),
    )
    return mgr, broker, pos[0]


@pytest.mark.asyncio
async def test_position_is_closed_once_its_horizon_is_reached(tmp_path):
    mgr, broker, pos = _mgr(tmp_path, horizon=32)
    bars = _candles(40, datetime(2024, 1, 1, tzinfo=timezone.utc))
    await mgr.manage_symbol("EURUSD", candles=bars, atr=0.001,
                            timeframe="M15", price=1.1040)  # +0.8R: a winner, but under the 1R partial
    assert broker.closed == [("777", None)], "a winner past its horizon must still close"


@pytest.mark.asyncio
async def test_position_is_left_alone_before_its_horizon(tmp_path):
    mgr, broker, pos = _mgr(tmp_path, horizon=32)
    bars = _candles(20, datetime(2024, 1, 1, tzinfo=timezone.utc))
    await mgr.manage_symbol("EURUSD", candles=bars, atr=0.001,
                            timeframe="M15", price=1.1040)
    assert broker.closed == []


@pytest.mark.asyncio
async def test_strategy_without_a_declared_horizon_is_untouched(tmp_path):
    mgr, broker, pos = _mgr(tmp_path, horizon=0, strategy="TrendFollowing")
    bars = _candles(200, datetime(2024, 1, 1, tzinfo=timezone.utc))
    await mgr.manage_symbol("EURUSD", candles=bars, atr=0.001,
                            timeframe="M15", price=1.1040)
    assert broker.closed == [], "no declared horizon means no horizon exit"


@pytest.mark.asyncio
async def test_horizon_survives_an_engine_restart(tmp_path):
    """The regression that motivated reading from the journal.

    The watchdog restarts the engine whenever the MT5 bridge drops. A ticket
    map held in memory would come back empty and the exit would silently stop
    firing while everything still looked healthy -- so build a completely
    fresh TradeManager over the same journal and require the rule to work.
    """
    ticket = "777"
    journal_path = tmp_path / "journal.jsonl"
    j = TradeJournal(path=str(journal_path))
    j.append("fill", ticket=ticket, strategy="StrengthReversion",
             symbol="EURUSD", risk_amount=50.0, entry=1.1000, stop_loss=1.0950)

    # ... engine dies here; nothing in memory survives ...

    broker = _Broker()
    pos = [_Pos(ticket, opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc))]
    fresh = TradeManager(
        broker, _Positions(pos),
        journal=TradeJournal(path=str(journal_path)),
        strategies=_Strategies({"StrengthReversion": _Strat(32)}),
    )
    bars = _candles(40, datetime(2024, 1, 1, tzinfo=timezone.utc))
    await fresh.manage_symbol("EURUSD", candles=bars, atr=0.001,
                              timeframe="M15", price=1.1040)
    assert broker.closed == [(ticket, None)]


@pytest.mark.asyncio
async def test_no_journal_or_no_registry_disables_the_rule_quietly(tmp_path):
    broker = _Broker()
    pos = [_Pos("777", opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc))]
    mgr = TradeManager(broker, _Positions(pos))  # the old two-argument form
    bars = _candles(200, datetime(2024, 1, 1, tzinfo=timezone.utc))
    await mgr.manage_symbol("EURUSD", candles=bars, atr=0.001,
                            timeframe="M15", price=1.1040)
    assert broker.closed == []
