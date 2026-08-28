"""
Trading Engine entry point (Phase 2 – Market Data + Broker).
Later phases will add Strategy, Risk, Execution loops here.
"""

from __future__ import annotations
import asyncio
import logging
import signal
import sys

from molido_broker import create_broker, BrokerType
from app.data.market_data import MarketDataEngine
from molido_shared.types import TimeFrame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("trading-engine")

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]


async def on_tick(tick):
    # Example subscriber – later this will feed Indicator / Signal engines
    if tick.symbol == "EURUSD":
        logger.debug(
            "EURUSD  bid=%.5f  ask=%.5f  spread=%.5f",
            tick.bid, tick.ask, tick.spread,
        )


async def run():
    logger.info("Starting Molido Trading Engine – PHASE 2 (Market Data)")
    broker = create_broker(BrokerType.MOCK, initial_balance=10_000.0, account_type="DEMO")
    mde = MarketDataEngine(broker=broker, symbols=SYMBOLS, stale_threshold_seconds=15.0)
    mde.subscribe(on_tick)

    await mde.start()

    # Demonstrate account + candles
    account = await broker.get_account_info()
    logger.info(
        "Account: balance=%.2f  equity=%.2f  type=%s",
        account.balance, account.equity, account.account_type,
    )

    candles = await mde.get_candles("EURUSD", TimeFrame.M15, count=5)
    logger.info("Last 5 M15 candles for EURUSD:")
    for c in candles:
        logger.info(
            "  %s  O=%.5f H=%.5f L=%.5f C=%.5f",
            c.open_time.strftime("%H:%M"), c.open, c.high, c.low, c.close,
        )

    # Keep running until interrupted
    stop_event = asyncio.Event()

    def _shutdown():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    logger.info("Market data streaming… (Ctrl+C to stop)")
    await stop_event.wait()
    await mde.stop()
    logger.info("Trading Engine stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
