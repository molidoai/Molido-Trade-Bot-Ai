from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, ForeignKey, DateTime, Enum as SAEnum, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.db.base import Base, TimestampMixin


class AuditAction(str, enum.Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    ACCOUNT_MODE_CHANGE = "ACCOUNT_MODE_CHANGE"      # DEMO <-> REAL
    MASTER_SWITCH = "MASTER_SWITCH"                  # ON / OFF
    STRATEGY_CHANGE = "STRATEGY_CHANGE"
    RISK_PARAM_CHANGE = "RISK_PARAM_CHANGE"
    LIVE_ACTIVATION = "LIVE_ACTIVATION"
    KILL_SWITCH = "KILL_SWITCH"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    MANUAL_ORDER = "MANUAL_ORDER"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    API_KEY_CHANGE = "API_KEY_CHANGE"
    UNAUTHORIZED_ATTEMPT = "UNAUTHORIZED_ATTEMPT"


class AuditLog(Base, TimestampMixin):
    """
    Immutable audit trail. Regular users cannot delete these records.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(50))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(30))  # dashboard / telegram / system
    details: Mapped[str | None] = mapped_column(Text)


class SystemEvent(Base, TimestampMixin):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info/warning/error/critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class PortfolioSnapshot(Base, TimestampMixin):
    """Periodic snapshot of account equity / exposure for analytics."""
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id"), nullable=False, index=True)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    margin_used: Mapped[float | None] = mapped_column(Float)
    free_margin: Mapped[float | None] = mapped_column(Float)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float)
    open_positions: Mapped[int] = mapped_column(Integer, default=0)
    drawdown_pct: Mapped[float | None] = mapped_column(Float)
    exposure: Mapped[dict | None] = mapped_column(JSON)  # currency / symbol exposure
