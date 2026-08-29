"""Execution Engine tests with MockBroker."""

import pytest
import uuid
from molido_broker import create_broker, BrokerType
from molido_execution import ExecutionEngine, ExecRequest, ExecStatus


@pytest.mark.asyncio
async def test_market_order_idempotent():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    engine = ExecutionEngine(broker)

    cid = str(uuid.uuid4())
    req = ExecRequest(
        symbol="EURUSD",
        side="BUY",
        volume=0.1,
        stop_loss=1.07,
        take_profit=1.10,
        client_order_id=cid,
        strategy="TrendFollowing",
    )
    r1 = await engine.execute(req)
    r2 = await engine.execute(req)  # same client_order_id

    assert r1.success is True
    assert r1.status == ExecStatus.FILLED
    assert r2.client_order_id == r1.client_order_id
    assert r2.broker_order_id == r1.broker_order_id  # idempotent
    assert req.order_type == "LIMIT"

    positions = await broker.get_positions()
    assert len(positions) == 1
    await broker.disconnect()


@pytest.mark.asyncio
async def test_reject_wide_spread():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    engine = ExecutionEngine(broker, max_spread_points=0.01)  # impossibly tight

    req = ExecRequest(
        symbol="EURUSD",
        side="BUY",
        volume=0.1,
        stop_loss=1.07,
        client_order_id=str(uuid.uuid4()),
    )
    result = await engine.execute(req)
    assert result.success is False
    assert result.status == ExecStatus.REJECTED
    await broker.disconnect()


@pytest.mark.asyncio
async def test_close_position():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    engine = ExecutionEngine(broker)

    open_req = ExecRequest(
        symbol="EURUSD", side="BUY", volume=0.1,
        stop_loss=1.07,
        client_order_id=str(uuid.uuid4()),
    )
    opened = await engine.execute(open_req)
    assert opened.success

    close_req = ExecRequest(
        symbol="EURUSD",
        side="EXIT",
        volume=0.1,
        reduce_only=True,
        position_ticket=opened.broker_order_id,
        client_order_id=str(uuid.uuid4()),
    )
    closed = await engine.execute(close_req)
    assert closed.success is True
    assert closed.status == ExecStatus.FILLED

    positions = await broker.get_positions()
    assert len(positions) == 0
    await broker.disconnect()
