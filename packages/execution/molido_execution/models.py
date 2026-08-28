"""Execution domain models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class ExecStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


@dataclass
class ExecRequest:
    """Intent to execute after Risk Engine approval."""
    symbol: str
    side: str                          # BUY / SELL / EXIT
    volume: float
    order_type: str = "MARKET"         # MARKET / LIMIT / STOP
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy: str | None = None
    signal_score: float | None = None
    risk_amount: float | None = None
    comment: str = ""
    magic: int = 0
    reduce_only: bool = False          # for exits
    position_ticket: str | int | None = None  # for close/modify


@dataclass
class ExecResult:
    success: bool
    status: ExecStatus
    client_order_id: str
    broker_order_id: str | None = None
    fill_price: float | None = None
    filled_volume: float = 0.0
    requested_volume: float = 0.0
    slippage: float | None = None
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            ExecStatus.FILLED,
            ExecStatus.CANCELLED,
            ExecStatus.REJECTED,
            ExecStatus.EXPIRED,
            ExecStatus.FAILED,
        )
