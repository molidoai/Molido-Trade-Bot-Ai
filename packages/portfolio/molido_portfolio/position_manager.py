"""
Position Manager (Master Prompt §16).

Broker is the source of truth.
After restart → must reconcile before accepting new entries.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

from molido_broker.base import BrokerAdapter
from molido_shared.types import BrokerPosition
from molido_portfolio.models import ManagedPosition

logger = logging.getLogger(__name__)


class PositionManager:
    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self._positions: dict[str, ManagedPosition] = {}
        self._synced: bool = False
        self._last_sync: datetime | None = None

    @property
    def is_synced(self) -> bool:
        return self._synced

    @property
    def last_sync(self) -> datetime | None:
        return self._last_sync

    async def sync_from_broker(self) -> int:
        """Pull open positions from broker and replace local state."""
        broker_positions = await self.broker.get_positions()
        new_map: dict[str, ManagedPosition] = {}
        for bp in broker_positions:
            ticket = str(bp.ticket)
            new_map[ticket] = self._from_broker(bp)
        self._positions = new_map
        self._synced = True
        self._last_sync = datetime.now(timezone.utc)
        logger.info("PositionManager synced %d positions", len(new_map))
        return len(new_map)

    def get_all(self) -> list[ManagedPosition]:
        return list(self._positions.values())

    def get(self, ticket: str) -> ManagedPosition | None:
        return self._positions.get(str(ticket))

    def by_symbol(self, symbol: str) -> list[ManagedPosition]:
        return [p for p in self._positions.values() if p.symbol == symbol]

    def count(self) -> int:
        return len(self._positions)

    def total_unrealized(self) -> float:
        return sum(p.unrealized_pnl for p in self._positions.values())

    def total_risk(self) -> float:
        return sum(p.risk_if_sl_hit for p in self._positions.values())

    def symbol_risk_map(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for p in self._positions.values():
            out[p.symbol] = out.get(p.symbol, 0.0) + p.risk_if_sl_hit
        return out

    def mark_unsynced(self) -> None:
        """Call when connection lost or unknown order state detected."""
        self._synced = False
        logger.warning("PositionManager marked UNSYNCED – new entries must pause")

    @staticmethod
    def _from_broker(bp: BrokerPosition) -> ManagedPosition:
        return ManagedPosition(
            ticket=str(bp.ticket),
            symbol=bp.symbol,
            side=bp.side.value if hasattr(bp.side, "value") else str(bp.side),
            volume=bp.volume,
            entry_price=bp.price_open,
            current_price=bp.price_current,
            stop_loss=bp.sl,
            take_profit=bp.tp,
            unrealized_pnl=bp.profit,
            swap=bp.swap,
            commission=bp.commission,
            opened_at=bp.time_open,
        )
