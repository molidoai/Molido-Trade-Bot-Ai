"""
Reconciliation (Master Prompt §16).

Broker is the final source of truth.
If state is unknown → stop new entries → reconcile → resume.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

from molido_broker.base import BrokerAdapter
from molido_portfolio.position_manager import PositionManager
from molido_portfolio.models import ReconcileReport

logger = logging.getLogger(__name__)


class Reconciler:
    def __init__(
        self,
        broker: BrokerAdapter,
        position_manager: PositionManager,
    ):
        self.broker = broker
        self.positions = position_manager
        self._entries_paused: bool = False
        self._last_report: ReconcileReport | None = None

    @property
    def entries_paused(self) -> bool:
        return self._entries_paused or not self.positions.is_synced

    @property
    def last_report(self) -> ReconcileReport | None:
        return self._last_report

    def pause_entries(self, reason: str = "reconciliation required") -> None:
        self._entries_paused = True
        self.positions.mark_unsynced()
        logger.warning("New entries PAUSED: %s", reason)

    def resume_entries(self) -> None:
        if self.positions.is_synced:
            self._entries_paused = False
            logger.info("New entries RESUMED after successful reconcile")
        else:
            logger.warning("Cannot resume – still unsynced")

    async def reconcile(self) -> ReconcileReport:
        """
        Full reconcile cycle:
        1. Pause new entries
        2. Fetch broker positions + account
        3. Diff with local state
        4. Adopt broker state
        5. Resume if clean
        """
        self.pause_entries("reconcile started")
        discrepancies: list[str] = []
        local_only: list[str] = []
        broker_only: list[str] = []

        try:
            if not await self.broker.is_connected():
                ok = await self.broker.connect()
                if not ok:
                    report = ReconcileReport(
                        success=False,
                        message="Broker not connected",
                        discrepancies=["connection failed"],
                    )
                    self._last_report = report
                    return report

            # Snapshot local tickets before sync
            local_tickets = {p.ticket for p in self.positions.get_all()}

            # Account check
            account = await self.broker.get_account_info()
            if account.equity <= 0 and account.balance <= 0:
                discrepancies.append("Account equity/balance is zero")

            # Sync positions from broker (source of truth)
            count = await self.positions.sync_from_broker()
            broker_tickets = {p.ticket for p in self.positions.get_all()}

            local_only = sorted(local_tickets - broker_tickets)
            broker_only = sorted(broker_tickets - local_tickets)

            if local_only:
                discrepancies.append(
                    f"Local positions not on broker (dropped): {local_only}"
                )
            if broker_only:
                discrepancies.append(
                    f"Broker positions not in local (adopted): {broker_only}"
                )

            # Orders (informational)
            try:
                orders = await self.broker.get_orders()
                orders_count = len(orders)
            except Exception:
                orders_count = 0
                discrepancies.append("Could not fetch open orders")

            success = True  # adopting broker state is always the resolution
            report = ReconcileReport(
                success=success,
                positions_synced=count,
                orders_synced=orders_count,
                discrepancies=discrepancies,
                local_only_tickets=local_only,
                broker_only_tickets=broker_only,
                message=(
                    f"Reconciled OK – {count} positions, "
                    f"account equity={account.equity:.2f}"
                ),
            )
            self._last_report = report

            if success:
                self.resume_entries()

            logger.info(report.message)
            return report

        except Exception as e:
            logger.exception("Reconcile failed")
            report = ReconcileReport(
                success=False,
                message=str(e),
                discrepancies=[str(e)],
            )
            self._last_report = report
            return report

    def can_accept_new_entries(self) -> tuple[bool, str]:
        if self._entries_paused:
            return False, "Entries paused for reconciliation"
        if not self.positions.is_synced:
            return False, "Position state not synced with broker"
        return True, "OK"
