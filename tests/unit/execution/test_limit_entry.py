import uuid
import pytest
from molido_broker import create_broker, BrokerType
from molido_execution import ExecutionEngine, ExecRequest, ExecStatus, entry_limit_price


@pytest.mark.asyncio
async def test_new_entry_is_limit_at_bid_for_buy():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    tick = await broker.get_tick("EURUSD")
    engine = ExecutionEngine(broker)
    req = ExecRequest(
        symbol="EURUSD", side="BUY", volume=0.1, order_type="MARKET",
        stop_loss=1.07, take_profit=1.10, client_order_id=str(uuid.uuid4()),
    )
    result = await engine.execute(req)
    assert result.success is True
    assert req.order_type == "LIMIT"
    assert abs(req.price - tick.bid) < 1e-8
    await broker.disconnect()


@pytest.mark.asyncio
async def test_sell_limit_at_ask():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    tick = await broker.get_tick("EURUSD")
    px = entry_limit_price("SELL", tick)
    assert abs(px - tick.ask) < 1e-8
    engine = ExecutionEngine(broker)
    req = ExecRequest(
        symbol="EURUSD", side="SELL", volume=0.1, stop_loss=1.10,
        client_order_id=str(uuid.uuid4()),
    )
    result = await engine.execute(req)
    assert result.success is True
    assert req.order_type == "LIMIT"
    assert abs(req.price - tick.ask) < 1e-8
    await broker.disconnect()


@pytest.mark.asyncio
async def test_mandatory_sl_rejects_entry():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    engine = ExecutionEngine(broker, max_spread_points=1000)
    req = ExecRequest(symbol="EURUSD", side="BUY", volume=0.1, client_order_id=str(uuid.uuid4()))
    result = await engine.execute(req)
    assert result.success is False
    assert result.status == ExecStatus.REJECTED
    assert "stop loss" in result.message.lower()
    await broker.disconnect()


@pytest.mark.asyncio
async def test_close_still_market_path():
    broker = create_broker(BrokerType.MOCK)
    await broker.connect()
    engine = ExecutionEngine(broker)
    opened = await engine.execute(ExecRequest(
        symbol="EURUSD", side="BUY", volume=0.1, stop_loss=1.07, client_order_id=str(uuid.uuid4()),
    ))
    assert opened.success
    closed = await engine.execute(ExecRequest(
        symbol="EURUSD", side="EXIT", volume=0.1, reduce_only=True,
        position_ticket=opened.broker_order_id, client_order_id=str(uuid.uuid4()),
    ))
    assert closed.success is True
    await broker.disconnect()
