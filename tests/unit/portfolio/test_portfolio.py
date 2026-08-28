"""Tests for Position / Portfolio / Reconciliation."""

import pytest
from molido_broker import create_broker, BrokerType
from molido_shared.types import Side, OrderType, OrderRequest
from molido_portfolio import PositionManager, PortfolioManager, Reconciler


@pytest.mark.asyncio
async def test_sync_and_snapshot():
    broker = create_broker(BrokerType.MOCK, initial_balance=10_000.0)
    await broker.connect()

    # Open a position via broker
    await broker.place_order(OrderRequest(
        symbol="EURUSD", side=Side.BUY, order_type=OrderType.MARKET, volume=0.2,
        client_order_id="t1",
    ))

    pm = PositionManager(broker)
    count = await pm.sync_from_broker()
    assert count == 1
    assert pm.is_synced is True
    assert pm.count() == 1
    assert pm.get_all()[0].symbol == "EURUSD"

    port = PortfolioManager(broker, pm, account_mode="DEMO")
    snap = await port.snapshot()
    assert snap.balance == 10_000.0
    assert snap.open_positions == 1
    assert snap.account_mode == "DEMO"

    await broker.disconnect()


@pytest.mark.asyncio
async def test_reconcile_adopts_broker():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    await broker.place_order(OrderRequest(
        symbol="GBPUSD", side=Side.SELL, order_type=OrderType.MARKET, volume=0.1,
        client_order_id="t2",
    ))

    pm = PositionManager(broker)
    rec = Reconciler(broker, pm)

    # Before reconcile – not synced
    assert pm.is_synced is False
    ok, reason = rec.can_accept_new_entries()
    assert ok is False

    report = await rec.reconcile()
    assert report.success is True
    assert report.positions_synced == 1
    assert pm.is_synced is True
    assert rec.entries_paused is False

    ok, reason = rec.can_accept_new_entries()
    assert ok is True

    await broker.disconnect()


@pytest.mark.asyncio
async def test_pause_on_unknown():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    pm = PositionManager(broker)
    await pm.sync_from_broker()
    rec = Reconciler(broker, pm)

    rec.pause_entries("unknown order state")
    assert rec.entries_paused is True
    ok, _ = rec.can_accept_new_entries()
    assert ok is False

    await broker.disconnect()
