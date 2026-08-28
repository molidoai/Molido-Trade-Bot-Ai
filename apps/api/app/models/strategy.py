from sqlalchemy import String, Boolean, Integer, Float, Text, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base, TimestampMixin


class StrategyStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    DEMO = "DEMO"
    MICRO_LIVE = "MICRO_LIVE"
    LIVE = "LIVE"
    DISABLED = "DISABLED"


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)  # trend, breakout, ...
    status: Mapped[StrategyStatus] = mapped_column(
        SAEnum(StrategyStatus, name="strategy_status"),
        default=StrategyStatus.DRAFT,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_versions.id"))
    allowed_regimes: Mapped[dict | None] = mapped_column(JSON)  # list of allowed market regimes
    risk_profile: Mapped[str] = mapped_column(String(30), default="normal")  # conservative/normal/aggressive


class StrategyVersion(Base, TimestampMixin):
    """
    Versioned strategy parameters (section 27.1.20).
    Every change creates a new version. Rollback is possible.
    """
    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "1.2.0"
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    entry_rules: Mapped[str | None] = mapped_column(Text)
    exit_rules: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_stable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
