"""
Market Data Engine

Responsibilities (from Master Prompt section 4):
- Live ticker / OHLCV / bid-ask / spread
- Multi-timeframe
- Stale-data detection
- Duplicate detection
- Heartbeat / reconnect handling (delegated to adapter)
- Never feed invalid or stale data into Strategy
"""

from __future__ import annotations
import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Callable, Awaitable

from molido_shared.types import Candle, Tick, TimeFrame
from molido_broker.base import BrokerAdapter

logger = logging.getLogger(__name__)


class MarketDataEngine:
    def __init__(
        self,
        broker: BrokerAdapter,
        symbols: list[str],
        stale_threshold_seconds: float = 30.0,
        max_tick_history: int = 500,
    ):
        self.broker = broker
        self.symbols = symbols
        self.stale_threshold = timedelta(seconds=stale_threshold_seconds)
        self._latest_tick: dict[str, Tick] = {}
        self._tick_history: dict[str, deque[Tick]] = defaultdict(
            lambda: deque(maxlen=max_tick_history)
        )
        self._candle_cache: dict[tuple[str, TimeFrame], list[Candle]] = {}
        self._running = False
        self._stream_task: asyncio.Task | None = None
        self._subscribers: list[Callable[[Tick], Awaitable[None]]] = []
        self._last_heartbeat: datetime | None = None

    async def start(self) -> None:
        if self._running:
            return
        connected = await self.broker.connect()
        if not connected:
            raise RuntimeError("Broker failed to connect")
        self._running = True
        self._last_heartbeat = datetime.now(timezone.utc)
        self._stream_task = asyncio.create_task(self._run_stream())
        logger.info("MarketDataEngine started for symbols: %s", self.symbols)

    async def stop(self) -> None:
        self._running = False
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        await self.broker.disconnect()
        logger.info("MarketDataEngine stopped")

    def subscribe(self, callback: Callable[[Tick], Awaitable[None]]) -> None:
        """Register an async callback that receives every new valid tick."""
        self._subscribers.append(callback)

    async def get_latest_tick(self, symbol: str) -> Tick | None:
        tick = self._latest_tick.get(symbol)
        if tick is None:
            return None
        if self._is_stale(tick):
            logger.warning("Stale tick detected for %s (age > %s)", symbol, self.stale_threshold)
            return None
        return tick

    async def get_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        count: int = 100,
        use_cache: bool = True,
    ) -> list[Candle]:
        key = (symbol, timeframe)
        if use_cache and key in self._candle_cache:
            cached = self._candle_cache[key]
            if len(cached) >= count:
                return cached[-count:]

        candles = await self.broker.get_candles(symbol, timeframe, count=count)
        # Basic validation: drop candles with bad OHLC
        valid = [
            c for c in candles
            if c.high >= c.low and c.high >= c.open and c.high >= c.close
            and c.low <= c.open and c.low <= c.close
        ]
        self._candle_cache[key] = valid
        return valid[-count:] if count else valid

    def is_data_fresh(self, symbol: str | None = None) -> bool:
        if symbol:
            tick = self._latest_tick.get(symbol)
            return tick is not None and not self._is_stale(tick)
        # All symbols
        if not self._latest_tick:
            return False
        return all(not self._is_stale(t) for t in self._latest_tick.values())

    def health(self) -> dict:
        return {
            "running": self._running,
            "symbols": self.symbols,
            "latest_ticks": {
                s: {
                    "bid": t.bid,
                    "ask": t.ask,
                    "spread": t.spread,
                    "age_seconds": (datetime.now(timezone.utc) - t.time).total_seconds(),
                }
                for s, t in self._latest_tick.items()
            },
            "data_fresh": self.is_data_fresh(),
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
        }

    # ---------- internal ----------

    def _is_stale(self, tick: Tick) -> bool:
        age = datetime.now(timezone.utc) - tick.time
        return age > self.stale_threshold

    def _is_duplicate(self, tick: Tick) -> bool:
        hist = self._tick_history[tick.symbol]
        if not hist:
            return False
        last = hist[-1]
        return (
            last.bid == tick.bid
            and last.ask == tick.ask
            and abs((last.time - tick.time).total_seconds()) < 0.05
        )

    async def _run_stream(self) -> None:
        try:
            async for tick in self.broker.stream_ticks(self.symbols):
                if not self._running:
                    break
                self._last_heartbeat = datetime.now(timezone.utc)

                if self._is_duplicate(tick):
                    continue

                self._latest_tick[tick.symbol] = tick
                self._tick_history[tick.symbol].append(tick)

                for cb in self._subscribers:
                    try:
                        await cb(tick)
                    except Exception:
                        logger.exception("Subscriber callback failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Tick stream error – will attempt reconnect logic later")
            self._running = False
