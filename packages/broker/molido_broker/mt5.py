"""
MetaTrader 5 Broker Adapter.

IMPORTANT:
- The official MetaTrader5 Python package requires a running MT5 terminal.
- On Ubuntu servers without GUI this usually means running MT5 under Wine
  or using a Windows VPS / remote terminal.
- This module is written so that the rest of the system only depends on
  the abstract BrokerAdapter interface.
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Any

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

logger = logging.getLogger(__name__)

# Try to import the official package – may not be available in all environments
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False


_TF_MAP = {
    TimeFrame.M1: 1,      # mt5.TIMEFRAME_M1
    TimeFrame.M5: 5,
    TimeFrame.M15: 15,
    TimeFrame.H1: 16385,  # mt5.TIMEFRAME_H1
    TimeFrame.H4: 16388,
    TimeFrame.D1: 16408,
}


class MT5BrokerAdapter(BrokerAdapter):
    """
    Production adapter for MetaTrader 5.
    Falls back to clear errors if the MetaTrader5 package or terminal is missing.
    """

    def __init__(
        self,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        path: str | None = None,
        timeout: int = 10_000,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.timeout = timeout
        self._connected = False

    async def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package is not installed")
            return False

        def _init() -> bool:
            kwargs: dict[str, Any] = {"timeout": self.timeout}
            if self.path:
                kwargs["path"] = self.path
            if not mt5.initialize(**kwargs):
                logger.error("MT5 initialize failed: %s", mt5.last_error())
                return False
            if self.login and self.password and self.server:
                authorized = mt5.login(self.login, password=self.password, server=self.server)
                if not authorized:
                    logger.error("MT5 login failed: %s", mt5.last_error())
                    mt5.shutdown()
                    return False
            return True

        self._connected = await asyncio.to_thread(_init)
        return self._connected

    async def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            await asyncio.to_thread(mt5.shutdown)
        self._connected = False

    async def is_connected(self) -> bool:
        if not MT5_AVAILABLE or not self._connected:
            return False
        info = await asyncio.to_thread(mt5.terminal_info)
        return info is not None

    async def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        info = await asyncio.to_thread(mt5.account_info)
        if info is None:
            raise RuntimeError(f"account_info failed: {mt5.last_error()}")
        return AccountInfo(
            login=info.login,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            margin_level=info.margin_level,
            profit=info.profit,
            currency=info.currency,
            leverage=info.leverage,
            trade_allowed=info.trade_allowed,
            account_type="DEMO" if info.trade_mode == 0 else "REAL",  # approximate
        )

    async def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        self._ensure_connected()
        info = await asyncio.to_thread(mt5.symbol_info, symbol)
        if info is None:
            return None
        return SymbolInfo(
            name=info.name,
            description=info.description,
            digits=info.digits,
            point=info.point,
            trade_contract_size=info.trade_contract_size,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
            stop_level=info.trade_stops_level,
            freeze_level=info.trade_freeze_level,
            spread=float(info.spread),
            currency_base=info.currency_base,
            currency_profit=info.currency_profit,
            currency_margin=info.currency_margin,
        )

    async def get_symbols(self) -> list[str]:
        self._ensure_connected()
        symbols = await asyncio.to_thread(mt5.symbols_get)
        if symbols is None:
            return []
        return [s.name for s in symbols if s.visible]

    async def get_tick(self, symbol: str) -> Tick | None:
        self._ensure_connected()
        tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            return None
        return Tick(
            symbol=symbol,
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=float(tick.volume),
            time=datetime.fromtimestamp(tick.time, tz=timezone.utc),
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        count: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        self._ensure_connected()
        tf = _TF_MAP.get(timeframe, 15)
        rates = await asyncio.to_thread(
            mt5.copy_rates_from_pos, symbol, tf, 0, count
        )
        if rates is None:
            return []
        candles: list[Candle] = []
        for r in rates:
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["tick_volume"]),
                    spread=float(r["spread"]) if "spread" in r.dtype.names else None,
                    is_closed=True,
                )
            )
        return candles

    async def stream_ticks(self, symbols: list[str]) -> AsyncIterator[Tick]:
        """
        Simple polling-based tick stream.
        For production a more efficient subscription can be added later.
        """
        self._ensure_connected()
        while await self.is_connected():
            for symbol in symbols:
                tick = await self.get_tick(symbol)
                if tick:
                    yield tick
            await asyncio.sleep(0.3)

    async def get_positions(self) -> list[BrokerPosition]:
        self._ensure_connected()
        positions = await asyncio.to_thread(mt5.positions_get)
        if positions is None:
            return []
        result: list[BrokerPosition] = []
        for p in positions:
            result.append(
                BrokerPosition(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    side=Side.BUY if p.type == 0 else Side.SELL,
                    volume=p.volume,
                    price_open=p.price_open,
                    price_current=p.price_current,
                    sl=p.sl or None,
                    tp=p.tp or None,
                    profit=p.profit,
                    swap=p.swap,
                    commission=getattr(p, "commission", 0.0),
                    time_open=datetime.fromtimestamp(p.time, tz=timezone.utc),
                    magic=p.magic,
                    comment=p.comment,
                )
            )
        return result

    async def get_orders(self) -> list[BrokerOrder]:
        self._ensure_connected()
        orders = await asyncio.to_thread(mt5.orders_get)
        if orders is None:
            return []
        # Mapping can be expanded later
        return []

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self._ensure_connected()
        # Full implementation of order_send with type, deviation, magic, etc.
        # will be completed when real terminal credentials are available.
        logger.warning("place_order called but full MT5 order path not yet activated")
        return OrderResult(
            success=False,
            client_order_id=request.client_order_id,
            message="MT5 live order execution not yet enabled in this phase",
        )

    async def cancel_order(self, ticket: str | int) -> bool:
        self._ensure_connected()
        return False

    async def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> bool:
        self._ensure_connected()
        return False

    async def close_position(
        self,
        ticket: str | int,
        volume: float | None = None,
    ) -> OrderResult:
        self._ensure_connected()
        return OrderResult(success=False, message="Not implemented yet")

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("MT5BrokerAdapter is not connected")
