"""
Shared domain types used across Trading Engine, Broker, Risk, etc.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeFrame(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    name: str                    # e.g. "EURUSD"
    description: str = ""
    digits: int = 5
    point: float = 0.00001
    trade_contract_size: float = 100000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    stop_level: int = 0          # in points
    freeze_level: int = 0
    spread: float = 0.0          # current spread in points (informational)
    trade_mode: str = "full"     # full / longonly / shortonly / closeonly
    currency_base: str = ""
    currency_profit: str = ""
    currency_margin: str = ""


@dataclass(slots=True)
class Tick:
    symbol: str
    bid: float
    ask: float
    last: float | None = None
    volume: float | None = None
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_points(self) -> float:
        # Approximate; real calculation needs SymbolInfo.point
        return self.spread


@dataclass(slots=True)
class Candle:
    symbol: str
    timeframe: TimeFrame
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float | None = None
    is_closed: bool = True


@dataclass(slots=True)
class AccountInfo:
    login: int | str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float | None = None
    profit: float = 0.0
    currency: str = "USD"
    leverage: int = 100
    trade_allowed: bool = True
    account_type: str = "DEMO"   # DEMO / REAL


@dataclass(slots=True)
class BrokerPosition:
    ticket: int | str
    symbol: str
    side: Side
    volume: float
    price_open: float
    price_current: float
    sl: float | None = None
    tp: float | None = None
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    time_open: datetime | None = None
    magic: int = 0
    comment: str = ""


@dataclass(slots=True)
class BrokerOrder:
    ticket: int | str
    symbol: str
    side: Side
    order_type: OrderType
    volume: float
    price_open: float | None = None
    sl: float | None = None
    tp: float | None = None
    status: str = "PENDING"
    time_setup: datetime | None = None


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: Side
    order_type: OrderType
    volume: float
    price: float | None = None
    sl: float | None = None
    tp: float | None = None
    client_order_id: str = ""
    comment: str = ""
    magic: int = 0


@dataclass(slots=True)
class OrderResult:
    success: bool
    broker_order_id: str | None = None
    client_order_id: str = ""
    fill_price: float | None = None
    filled_volume: float = 0.0
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
