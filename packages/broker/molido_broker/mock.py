"""
Mock Broker Adapter – for development, paper trading and tests.
Generates realistic synthetic ticks and candles without any real broker.
"""

from __future__ import annotations
import asyncio
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from molido_shared.types import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    Candle,
    OrderRequest,
    OrderResult,
    Side,
    SymbolInfo,
    Tick,
    TimeFrame,
    OrderType,
)
from molido_broker.base import BrokerAdapter


# Base prices for major pairs (approximate)
_BASE_PRICES: dict[str, float] = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.3050,
    "USDJPY": 149.50,
    "USDCHF": 0.8650,
    "AUDUSD": 0.6650,
    "USDCAD": 1.3600,
    "NZDUSD": 0.6100,
    "XAUUSD": 2650.00,
    "XAGUSD": 31.50,
}


class MockBrokerAdapter(BrokerAdapter):
    """
    Fully functional in-memory broker for development and Paper mode.
    """

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        account_type: str = "DEMO",
        leverage: int = 100,
        spread_points: dict[str, float] | None = None,
    ):
        self._connected = False
        self._balance = initial_balance
        self._equity = initial_balance
        self._account_type = account_type
        self._leverage = leverage
        self._positions: dict[str, BrokerPosition] = {}
        self._orders: dict[str, BrokerOrder] = {}
        self._prices: dict[str, float] = dict(_BASE_PRICES)
        self._spread_points = spread_points or {
            "EURUSD": 1.2,
            "GBPUSD": 1.5,
            "USDJPY": 1.3,
            "XAUUSD": 25.0,
        }
        self._tick_task: asyncio.Task | None = None
        self._subscribers: list[asyncio.Queue] = []

    async def connect(self) -> bool:
        self._connected = True
        # Start background price walker
        if self._tick_task is None or self._tick_task.done():
            self._tick_task = asyncio.create_task(self._price_walker())
        return True

    async def disconnect(self) -> None:
        self._connected = False
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        self._tick_task = None

    async def is_connected(self) -> bool:
        return self._connected

    async def get_account_info(self) -> AccountInfo:
        self._recalc_equity()
        return AccountInfo(
            login="mock-1001",
            balance=round(self._balance, 2),
            equity=round(self._equity, 2),
            margin=0.0,
            free_margin=round(self._equity, 2),
            margin_level=None,
            profit=round(self._equity - self._balance, 2),
            currency="USD",
            leverage=self._leverage,
            trade_allowed=True,
            account_type=self._account_type,
        )

    async def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        if symbol not in self._prices:
            return None
        digits = 3 if "JPY" in symbol or symbol.startswith("XAU") else 5
        point = 0.001 if digits == 3 else 0.00001
        if symbol.startswith("XAU"):
            point = 0.01
            digits = 2
        return SymbolInfo(
            name=symbol,
            description=f"Mock {symbol}",
            digits=digits,
            point=point,
            volume_min=0.01,
            volume_max=50.0,
            volume_step=0.01,
            spread=self._spread_points.get(symbol, 1.5),
            currency_base=symbol[:3],
            currency_profit="USD",
        )

    async def get_symbols(self) -> list[str]:
        return list(self._prices.keys())

    async def get_tick(self, symbol: str) -> Tick | None:
        if symbol not in self._prices:
            return None
        mid = self._prices[symbol]
        half_spread = self._point_value(symbol) * self._spread_points.get(symbol, 1.5) / 2
        return Tick(
            symbol=symbol,
            bid=round(mid - half_spread, 6),
            ask=round(mid + half_spread, 6),
            last=mid,
            volume=random.uniform(0.5, 5.0),
            time=datetime.now(timezone.utc),
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        count: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        if symbol not in self._prices:
            return []

        tf_minutes = {
            TimeFrame.M1: 1,
            TimeFrame.M5: 5,
            TimeFrame.M15: 15,
            TimeFrame.H1: 60,
            TimeFrame.H4: 240,
            TimeFrame.D1: 1440,
        }.get(timeframe, 60)

        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        candles: list[Candle] = []
        price = self._prices[symbol]

        for i in range(count, 0, -1):
            open_time = now - timedelta(minutes=tf_minutes * i)
            # Simple random walk candle
            change = random.gauss(0, price * 0.0003)
            o = price
            c = price + change
            h = max(o, c) + abs(random.gauss(0, price * 0.0001))
            l = min(o, c) - abs(random.gauss(0, price * 0.0001))
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    open=round(o, 6),
                    high=round(h, 6),
                    low=round(l, 6),
                    close=round(c, 6),
                    volume=random.uniform(10, 200),
                    is_closed=True,
                )
            )
            price = c
        return candles

    async def stream_ticks(self, symbols: list[str]) -> AsyncIterator[Tick]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(queue)
        try:
            while self._connected:
                tick = await queue.get()
                if tick.symbol in symbols:
                    yield tick
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def get_positions(self) -> list[BrokerPosition]:
        self._update_position_prices()
        return list(self._positions.values())

    async def get_orders(self) -> list[BrokerOrder]:
        return list(self._orders.values())

    async def place_order(self, request: OrderRequest) -> OrderResult:
        if not self._connected:
            return OrderResult(success=False, message="Not connected", client_order_id=request.client_order_id)

        tick = await self.get_tick(request.symbol)
        if tick is None:
            return OrderResult(success=False, message=f"Unknown symbol {request.symbol}")

        fill_price = tick.ask if request.side == Side.BUY else tick.bid
        if request.order_type != OrderType.MARKET and request.price is not None:
            # Simplified: accept limit/stop at given price for mock
            fill_price = request.price

        ticket = str(uuid.uuid4())[:12]
        pos = BrokerPosition(
            ticket=ticket,
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            price_open=fill_price,
            price_current=fill_price,
            sl=request.sl,
            tp=request.tp,
            profit=0.0,
            time_open=datetime.now(timezone.utc),
            comment=request.comment or request.client_order_id,
        )
        self._positions[ticket] = pos

        return OrderResult(
            success=True,
            broker_order_id=ticket,
            client_order_id=request.client_order_id,
            fill_price=fill_price,
            filled_volume=request.volume,
            message="Filled (mock)",
        )

    async def cancel_order(self, ticket: str | int) -> bool:
        key = str(ticket)
        if key in self._orders:
            del self._orders[key]
            return True
        return False

    async def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> bool:
        key = str(ticket)
        if key not in self._positions:
            return False
        pos = self._positions[key]
        if sl is not None:
            pos.sl = sl
        if tp is not None:
            pos.tp = tp
        return True

    async def close_position(
        self,
        ticket: str | int,
        volume: float | None = None,
    ) -> OrderResult:
        key = str(ticket)
        if key not in self._positions:
            return OrderResult(success=False, message="Position not found")

        pos = self._positions[key]
        close_vol = volume or pos.volume
        tick = await self.get_tick(pos.symbol)
        if tick is None:
            return OrderResult(success=False, message="No tick")

        close_price = tick.bid if pos.side == Side.BUY else tick.ask
        # Very simplified PnL (not pip-accurate for all symbols)
        direction = 1 if pos.side == Side.BUY else -1
        pnl = direction * (close_price - pos.price_open) * close_vol * 100000  # rough for FX

        self._balance += pnl
        if close_vol >= pos.volume:
            del self._positions[key]
        else:
            pos.volume -= close_vol

        return OrderResult(
            success=True,
            broker_order_id=key,
            fill_price=close_price,
            filled_volume=close_vol,
            message=f"Closed (mock) PnL≈{pnl:.2f}",
        )

    # ---------- internal helpers ----------

    def _point_value(self, symbol: str) -> float:
        if symbol.startswith("XAU"):
            return 0.01
        if "JPY" in symbol:
            return 0.001
        return 0.00001

    def _recalc_equity(self) -> None:
        self._update_position_prices()
        unrealized = sum(p.profit for p in self._positions.values())
        self._equity = self._balance + unrealized

    def _update_position_prices(self) -> None:
        for pos in self._positions.values():
            mid = self._prices.get(pos.symbol, pos.price_open)
            pos.price_current = mid
            direction = 1 if pos.side == Side.BUY else -1
            pos.profit = direction * (mid - pos.price_open) * pos.volume * 100000

    async def _price_walker(self) -> None:
        """Background task that slowly moves prices and pushes ticks."""
        while self._connected:
            for symbol in list(self._prices.keys()):
                # Small random walk
                change_pct = random.gauss(0, 0.00008)
                self._prices[symbol] *= (1 + change_pct)

                tick = await self.get_tick(symbol)
                if tick:
                    for q in self._subscribers:
                        try:
                            q.put_nowait(tick)
                        except asyncio.QueueFull:
                            pass
            await asyncio.sleep(0.5)  # ~2 ticks/sec per symbol
