"""
LIVE trading runner.

REAL account + MT5. RiskEngine is still mandatory.
Requires MT5_REAL_LOGIN / MT5_REAL_PASSWORD / MT5_REAL_SERVER.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import urllib.request
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


def _env_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _poll_ops_master(default: bool) -> bool:
    url = os.getenv("OPS_STATE_URL", "http://api:8000/api/v1/ops/state")
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return bool(data.get("master_on", default))
    except Exception:
        logger.debug("ops state poll failed; keeping master=%s", default)
        return default


class LiveRunner:
    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframe: TimeFrame = TimeFrame.M15,
        cycle_seconds: float = 15.0,
    ):
        self.symbols = symbols or ["EURUSD", "GBPUSD", "XAUUSD"]
        self.timeframe = timeframe
        self.cycle_seconds = cycle_seconds
        self.account_mode = os.getenv("TRADING_ACCOUNT_MODE", "REAL").upper() or "REAL"
        self.master_bot_on = _env_bool("MASTER_BOT_ENABLED", True)
        self._running = False

        login = _env_int("MT5_REAL_LOGIN")
        password = os.getenv("MT5_REAL_PASSWORD") or None
        server = os.getenv("MT5_REAL_SERVER") or None
        path = os.getenv("MT5_REAL_PATH") or None

        if not login or not password or not server:
            raise RuntimeError(
                "LIVE requires MT5_REAL_LOGIN, MT5_REAL_PASSWORD, MT5_REAL_SERVER in .env"
            )

        self.broker = create_broker(
            BrokerType.MT5,
            login=login,
            password=password,
            server=server,
            path=path,
        )

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
        self.portfolio = PortfolioManager(self.broker, self.positions, account_mode=self.account_mode)
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
            account_mode=self.account_mode,
        )

        self.market_data = MarketDataEngine(
            broker=self.broker,
            symbols=self.symbols,
            stale_threshold_seconds=60.0,
        )

    async def start(self) -> None:
        logger.info(
            "LIVE runner starting | mode=%s | master=%s | symbols=%s",
            self.account_mode,
            "ON" if self.master_bot_on else "OFF",
            self.symbols,
        )
        ok = await self.broker.connect()
        if not ok:
            raise RuntimeError(
                "LIVE MT5 connect failed. Need a running MT5 terminal (Windows or Wine) plus valid REAL credentials."
            )
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
        logger.info("LIVE runner stopped")

    def set_master(self, on: bool) -> None:
        self.master_bot_on = on
        logger.info("Master bot → %s", "ON" if on else "OFF")

    async def _cycle(self) -> None:
        self.master_bot_on = _poll_ops_master(self.master_bot_on)
        snap = await self.portfolio.snapshot()
        logger.info(
            "LIVE equity=%.2f | positions=%d | DD=%.2f%% | master=%s",
            snap.equity,
            snap.open_positions,
            snap.drawdown_pct,
            "ON" if self.master_bot_on else "OFF",
        )
        for symbol in self.symbols:
            try:
                candles = await self.market_data.get_candles(symbol, self.timeframe, count=150)
                if not candles:
                    continue
                result = await self.pipeline.on_candles(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    candles=candles,
                    regime=None,
                    master_bot_on=self.master_bot_on,
                )
                if result.skipped_reason:
                    logger.debug("%s skipped: %s", symbol, result.skipped_reason)
                    continue
                if result.exec_result and result.exec_result.success:
                    logger.info(
                        "%s LIVE FILL %s %.2f lots @ %s",
                        symbol,
                        result.signal.side.value if result.signal else "?",
                        result.lot_size,
                        result.exec_result.fill_price,
                    )
                elif result.exec_result and not result.exec_result.success:
                    logger.warning("%s exec failed: %s", symbol, result.exec_result.message)
            except Exception:
                logger.exception("LIVE cycle error on %s", symbol)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    runner = LiveRunner()
    try:
        await runner.start()
    except KeyboardInterrupt:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
