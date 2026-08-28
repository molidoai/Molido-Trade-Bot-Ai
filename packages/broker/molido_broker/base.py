"""
Abstract Broker Adapter interface.
All concrete brokers (MT5, OANDA, FIX, Mock) must implement this.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator

from molido_shared.types import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    Candle,
    OrderRequest,
    OrderResult,
    SymbolInfo,
    Tick,
    TimeFrame,
)


class BrokerAdapter(ABC):
    """
    Unified interface for any broker / platform.
    Trading Engine only talks to this interface – never to MT5 directly.
    """

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        ...

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        ...

    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        ...

    @abstractmethod
    async def get_symbols(self) -> list[str]:
        """List of tradeable symbols."""
        ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> Tick | None:
        ...

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        count: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        ...

    @abstractmethod
    async def stream_ticks(self, symbols: list[str]) -> AsyncIterator[Tick]:
        """Async generator yielding live ticks."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        ...

    @abstractmethod
    async def get_orders(self) -> list[BrokerOrder]:
        ...

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        ...

    @abstractmethod
    async def cancel_order(self, ticket: str | int) -> bool:
        ...

    @abstractmethod
    async def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> bool:
        ...

    @abstractmethod
    async def close_position(
        self,
        ticket: str | int,
        volume: float | None = None,
    ) -> OrderResult:
        ...

    async def health_check(self) -> dict:
        """Basic health for monitoring."""
        connected = await self.is_connected()
        return {
            "connected": connected,
            "adapter": self.__class__.__name__,
        }
