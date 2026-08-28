"""Pipeline integration test with Mock broker."""

import pytest
from datetime import datetime, timedelta, timezone
from molido_shared.types import Candle, TimeFrame
from molido_broker import create_broker, BrokerType
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_signals import SignalEngine
from molido_risk import RiskEngine, RiskLimits
from molido_execution import ExecutionEngine
from molido_portfolio import PositionManager, PortfolioManager, Reconciler

# Import path for trading-engine app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "trading-engine"))
from app.orchestration.pipeline import TradingPipeline


def _candles(n=120):
    t0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
    price = 1.0850
    out = []
    for i in range(n):
        o = price
        c = price + (0.0001 if i % 3 else -0.00008)
        out.append(Candle(
            symbol="EURUSD", timeframe=TimeFrame.M15,
            open_time=t0 + timedelta(minutes=15 * i),
            open=round(o, 5), high=round(max(o, c) + 0.00015, 5),
            low=round(min(o, c) - 0.00015, 5), close=round(c, 5), volume=50,
        ))
        price = c
    return out


@pytest.mark.asyncio
async def test_pipeline_full_path():
    broker = create_broker(BrokerType.MOCK, initial_balance=10_000)
    await broker.connect()

    ind = IndicatorEngine()
    ind.add_from_registry("MultiEMA")
    ind.add_from_registry("RSI", period=14)
    ind.add_from_registry("ATR", period=14)
    ind.add_from_registry("DonchianChannel", period=20)
    ind.add_from_registry("BollingerBands", period=20)

    strat = StrategyEngine()
    strat.add_from_registry("TrendFollowing")
    strat.add_from_registry("DonchianBreakout")
    strat.add_from_registry("RSIMeanReversion")

    pm = PositionManager(broker)
    await pm.sync_from_broker()
    port = PortfolioManager(broker, pm)
    rec = Reconciler(broker, pm)
    await rec.reconcile()

    pipeline = TradingPipeline(
        indicator_engine=ind,
        strategy_engine=strat,
        signal_engine=SignalEngine(accept_threshold=40.0),
        risk_engine=RiskEngine(RiskLimits(risk_per_trade=0.01)),
        execution_engine=ExecutionEngine(broker),
        position_manager=pm,
        portfolio_manager=port,
        reconciler=rec,
        account_mode="DEMO",
    )

    result = await pipeline.on_candles(
        symbol="EURUSD",
        timeframe=TimeFrame.M15,
        candles=_candles(),
        regime="Bull",
        master_bot_on=True,
    )
    # May or may not trade depending on signal – but must not crash
    assert result is not None
    # Master off should skip
    result2 = await pipeline.on_candles(
        "EURUSD", TimeFrame.M15, _candles(), master_bot_on=False
    )
    assert result2.skipped_reason == "Master bot is OFF"

    await broker.disconnect()
