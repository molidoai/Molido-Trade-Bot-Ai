from sqlalchemy import String, Boolean, Integer, Float, Enum as SAEnum, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base, TimestampMixin


class AccountType(str, enum.Enum):
    DEMO = "DEMO"
    PROP = "PROP"   # Proprietary Trading Firm (FTMO, FundedNext, etc.)
    REAL = "REAL"


class BrokerPlatform(str, enum.Enum):
    MT5 = "MT5"
    MT4 = "MT4"
    OANDA = "OANDA"
    FIX = "FIX"
    OTHER = "OTHER"


class PropPhase(str, enum.Enum):
    """Typical prop firm challenge stages."""
    CHALLENGE = "CHALLENGE"       # Phase 1 evaluation
    VERIFICATION = "VERIFICATION" # Phase 2
    FUNDED = "FUNDED"             # Live funded account
    SCALED = "SCALED"             # After scaling plan


class BrokerAccount(Base, TimestampMixin):
    """
    Represents a broker account.
    Supports DEMO, PROP (prop firm) and REAL.
    Designed for future multi-account support (account_id on every Position/Order/Trade).
    """
    __tablename__ = "broker_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "FTMO Challenge 100k"
    platform: Mapped[BrokerPlatform] = mapped_column(
        SAEnum(BrokerPlatform, name="broker_platform"),
        default=BrokerPlatform.MT5,
        nullable=False,
    )
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, name="account_type"),
        nullable=False,
    )
    login: Mapped[str] = mapped_column(String(50), nullable=False)
    server: Mapped[str] = mapped_column(String(100), nullable=False)
    # Password is NEVER stored in plain text.
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_sync_at: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    broker_name: Mapped[str | None] = mapped_column(String(100))

    # ---------- Prop Firm specific fields ----------
    prop_firm_name: Mapped[str | None] = mapped_column(String(100))  # e.g. "FTMO", "FundedNext"
    prop_phase: Mapped[PropPhase | None] = mapped_column(
        SAEnum(PropPhase, name="prop_phase"),
        nullable=True,
    )
    prop_account_size: Mapped[float | None] = mapped_column(Float)  # e.g. 100000
    # Hard rules from the prop firm (enforced by Risk Engine later)
    prop_max_daily_loss_pct: Mapped[float | None] = mapped_column(Float)   # e.g. 5.0
    prop_max_total_drawdown_pct: Mapped[float | None] = mapped_column(Float)  # e.g. 10.0
    prop_profit_target_pct: Mapped[float | None] = mapped_column(Float)   # e.g. 10.0
    prop_min_trading_days: Mapped[int | None] = mapped_column(Integer)
    prop_consistency_rule_pct: Mapped[float | None] = mapped_column(Float)  # optional
