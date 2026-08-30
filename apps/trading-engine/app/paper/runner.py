"""
Paper / Demo trading runner (PHASE 10).

Uses MockBroker by default (pure paper) or can point to real DEMO MT5
credentials when available.

Runs the full pipeline on a timer / candle cycle without risking real capital.
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from molido_broker import create_broker, BrokerType
from molido_shared.types import TimeFrame
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_signals import SignalEngine
from molido_risk import RiskEngine, RiskLimits
from molido_execution import ExecutionEngine
from molido_portfolio import PositionManager, PortfolioManager, Reconciler
from app.orchestration.pipeline import TradingPipeline
from app.data.market_data import MarketDataEngine

logger = logging.getLogger(__name__)


class PaperRunner:
    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframe: TimeFrame = TimeFrame.M15,
        initial_balance: float = 10_000.0,
        account_mode: str = "DEMO",
        broker_type: BrokerType = BrokerType.MOCK,
        cycle_seconds: float = 15.0,
        master_bot_on: bool = True,
        # Optional real DEMO MT5 credentials
        mt5_login: int | None = None,
        mt5_password: str | None = None,
        mt5_server: str | None = None,
        mt5_path: str | None = None,
    ):
        self.symbols = symbols or ["EURUSD", "GBPUSD", "XAUUSD"]
        self.timeframe = timeframe
        self.cycle_seconds = cycle_seconds
        self.master_bot_on = master_bot_on
        self.account_mode = account_mode
        self._running = False

        # Broker
        if broker_type == BrokerType.MT5 and mt5_login:
            self.broker = create_broker(
                BrokerType.MT5,
                login=mt5_login,
                password=mt5_password,
                server=mt5_server,
                path=mt5_path,
            )
        else:
            self.broker = create_broker(
                BrokerType.MOCK,
                initial_balance=initial_balance,
                account_type=account_mode,
            )

        # Engines
        self.indicators = IndicatorEngine()
        self.indicators.add_from_registry("MultiEMA")
        self.indicators.add_from_registry("RSI", period=14)
        self.indicators.add_from_registry("ATR", period=14)
        self.indicators.add_from_registry("MACD")
        self.indicators.add_from_registry("BollingerBands", period=20)
        self.indicators.add_from_registry("DonchianChannel", period=20)
        self.indicators.add_from_registry("Supertrend", period=10, multiplier=3.0)

        self.strategies = StrategyEngine()
        self.strategies.add_from_registry("TrendFollowing")
        self.strategies.add_from_registry("DonchianBreakout")
        self.strategies.add_from_registry("RSIMeanReversion")

        self.signals = SignalEngine(accept_threshold=55.0)
        self.risk = RiskEngine(RiskLimits(risk_per_trade=0.005, max_open_positions=3))
        self.execution = ExecutionEngine(self.broker)
        self.positions = PositionManager(self.broker)
        self.portfolio = PortfolioManager(self.broker, self.positions, account_mode=account_mode)
        self.reconciler = Reconciler(self.broker, self.positions)

        self.pipeline = TradingPipeline(
            indicator_engine=self.indicators,
            strategy_engine=self.strategies,
            signal_engine=self.signals,
            risk_engine=self.risk,
            execution_engine=self.execution,
            position_manager=self.positions,
            portfolio_manager=self.portfolio,
            reconciler=self.reconciler,
            account_mode=account_mode,
        )

        self.market_data = MarketDataEngine(
            broker=self.broker,
            symbols=self.symbols,
            stale_threshold_seconds=60.0,
        )

    async def start(self) -> None:
        logger.info(
            "PaperRunner starting | mode=%s | symbols=%s | tf=%s",
            self.account_mode, self.symbols, self.timeframe.value,
        )
        await self.broker.connect()
        await self.reconciler.reconcile()
        await self.market_data.start()
        self._running = True

        try:
            while self._running:
                await self._cycle()
                await asyncio.sleep(self.cycle_seconds)
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._running = False
        await self.market_data.stop()
        await self.broker.disconnect()
        logger.info("PaperRunner stopped")

    def set_master(self, on: bool) -> None:
        self.master_bot_on = on
        logger.info("Master bot → %s", "ON" if on else "OFF")

    async def _cycle(self) -> None:
        snap = await self.portfolio.snapshot()
        logger.info(
            "Equity=%.2f | Positions=%d | DD=%.2f%% | Mode=%s | Master=%s",
            snap.equity, snap.open_positions, snap.drawdown_pct,
            self.account_mode, "ON" if self.master_bot_on else "OFF",
        )

        for symbol in self.symbols:
            try:
                candles = await self.market_data.get_candles(
                    symbol, self.timeframe, count=150
                )
                if not candles:
                    continue

                result = await self.pipeline.on_candles(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    candles=candles,
                    regime=None,  # regime engine comes in later phase
                    master_bot_on=self.master_bot_on,
                )

                if result.skipped_reason:
                    logger.debug("%s skipped: %s", symbol, result.skipped_reason)
                    continue

                if result.exec_result and result.exec_result.success:
                    logger.info(
                        "%s EXECUTED %s %.2f lots @ %s | strategy=%s score=%.1f",
                        symbol,
                        result.signal.side.value if result.signal else "?",
                        result.lot_size,
                        result.exec_result.fill_price,
                        result.signal.strategy if result.signal else "",
                        result.signal.score if result.signal else 0,
                    )
                elif result.exec_result and not result.exec_result.success:
                    logger.warning(
                        "%s exec failed: %s", symbol, result.exec_result.message
                    )
                elif result.signal and not result.risk_allowed:
                    logger.info("%s risk denied: %s", symbol, result.skipped_reason)

            except Exception:
                logger.exception("Cycle error on %s", symbol)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    runner = PaperRunner(
        symbols=["EURUSD", "GBPUSD"],
        timeframe=TimeFrame.M15,
        initial_balance=10_000.0,
        account_mode="DEMO",
        cycle_seconds=10.0,
        master_bot_on=True,
    )
    try:
        # Run a few cycles then stop (demo)
        task = asyncio.create_task(runner.start())
        await asyncio.sleep(35)  # ~3 cycles
        await runner.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    except KeyboardInterrupt:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
