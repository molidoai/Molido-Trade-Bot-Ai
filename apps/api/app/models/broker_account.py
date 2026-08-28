from sqlalchemy import String, Boolean, Integer, Enum as SAEnum, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base, TimestampMixin


class AccountType(str, enum.Enum):
    DEMO = "DEMO"
    REAL = "REAL"


class BrokerPlatform(str, enum.Enum):
    MT5 = "MT5"
    MT4 = "MT4"
    OANDA = "OANDA"
    FIX = "FIX"
    OTHER = "OTHER"


class BrokerAccount(Base, TimestampMixin):
    """
    Represents a broker account.
    Designed for future multi-account support (account_id on every Position/Order/Trade).
    """
    __tablename__ = "broker_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "My Demo Account"
    platform: Mapped[BrokerPlatform] = mapped_column(
        SAEnum(BrokerPlatform, name="broker_platform"),
        default=BrokerPlatform.MT5,
        nullable=False,
    )
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, name="account_type"),
        nullable=False,
    )
    login: Mapped[str] = mapped_column(String(50), nullable=False)  # stored as string for safety
    server: Mapped[str] = mapped_column(String(100), nullable=False)
    # Password is NEVER stored in plain text. Only encrypted or reference to secret manager.
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_sync_at: Mapped[str | None] = mapped_column(String(50))  # ISO timestamp
    notes: Mapped[str | None] = mapped_column(Text)

    # Future multi-broker ready
    broker_name: Mapped[str | None] = mapped_column(String(100))
