from datetime import datetime
from sqlalchemy import (
    String, Boolean, Integer, Float, Text, ForeignKey,
    DateTime, Enum as SAEnum, JSON, Numeric
)
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.db.base import Base, TimestampMixin


class SignalSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class PositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIAL = "PARTIAL"


class Signal(Base, TimestampMixin):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("broker_accounts.id"), index=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[SignalSide] = mapped_column(SAEnum(SignalSide, name="signal_side"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10))
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    entry_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 6))
    reasons: Mapped[dict | None] = mapped_column(JSON)
    market_regime: Mapped[str | None] = mapped_column(String(30))
    is_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    no_trade_reason: Mapped[str | None] = mapped_column(Text)  # for NO_TRADE intelligence


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id"), nullable=False, index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"))
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(SAEnum(OrderType, name="order_type"), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 6))
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"),
        default=OrderStatus.PENDING,
        nullable=False,
    )
    filled_volume: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    avg_fill_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    slippage: Mapped[float | None] = mapped_column(Float)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict | None] = mapped_column(JSON)


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id"), nullable=False, index=True)
    broker_position_id: Mapped[str | None] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    current_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 6))
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(14, 4))
    swap: Mapped[float | None] = mapped_column(Numeric(12, 4))
    commission: Mapped[float | None] = mapped_column(Numeric(12, 4))
    status: Mapped[PositionStatus] = mapped_column(
        SAEnum(PositionStatus, name="position_status"),
        default=PositionStatus.OPEN,
        nullable=False,
    )
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Trade(Base, TimestampMixin):
    """Closed trade record (for journal & analytics)."""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id"), nullable=False, index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"))
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    exit_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 6))
    realized_pnl: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    commission: Mapped[float | None] = mapped_column(Numeric(12, 4))
    swap: Mapped[float | None] = mapped_column(Numeric(12, 4))
    slippage: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    market_regime: Mapped[str | None] = mapped_column(String(30))
    signal_score: Mapped[float | None] = mapped_column(Float)
    entry_reason: Mapped[str | None] = mapped_column(Text)
    exit_reason: Mapped[str | None] = mapped_column(Text)
    mfe: Mapped[float | None] = mapped_column(Float)  # Maximum Favorable Excursion
    mae: Mapped[float | None] = mapped_column(Float)  # Maximum Adverse Excursion
    journal_notes: Mapped[str | None] = mapped_column(Text)
