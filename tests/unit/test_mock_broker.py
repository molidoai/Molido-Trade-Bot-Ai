"""Smoke tests for MockBroker and MarketDataEngine (no real MT5 needed)."""

import asyncio
import pytest
from molido_broker import create_broker, BrokerType
from molido_shared.types import Side, OrderType, OrderRequest, TimeFrame


@pytest.mark.asyncio
async def test_mock_broker_connect_and_account():
    broker = create_broker(BrokerType.MOCK, initial_balance=5000.0)
    assert await broker.connect() is True
    assert await broker.is_connected() is True

    info = await broker.get_account_info()
    assert info.balance == 5000.0
    assert info.account_type == "DEMO"

    symbols = await broker.get_symbols()
    assert "EURUSD" in symbols
    assert "XAUUSD" in symbols

    tick = await broker.get_tick("EURUSD")
    assert tick is not None
    assert tick.ask > tick.bid

    candles = await broker.get_candles("EURUSD", TimeFrame.M15, count=10)
    assert len(candles) == 10
    assert candles[0].high >= candles[0].low

    await broker.disconnect()
    assert await broker.is_connected() is False


@pytest.mark.asyncio
async def test_mock_place_and_close_order():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()

    result = await broker.place_order(
        OrderRequest(
            symbol="EURUSD",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            volume=0.1,
            client_order_id="test-001",
        )
    )
    assert result.success is True
    assert result.broker_order_id is not None

    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0].volume == 0.1

    close = await broker.close_position(result.broker_order_id)
    assert close.success is True

    positions = await broker.get_positions()
    assert len(positions) == 0

    await broker.disconnect()
