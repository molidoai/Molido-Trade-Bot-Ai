"""Alert helpers for trade events, risk, system failures."""

from __future__ import annotations
from molido_telegram.client import TelegramClient


class AlertService:
    def __init__(self, client: TelegramClient, admin_chat_id: str | None):
        self.client = client
        self.admin_chat_id = admin_chat_id

    async def _send(self, text: str) -> None:
        if not self.admin_chat_id:
            return
        try:
            await self.client.send_message(self.admin_chat_id, text)
        except Exception:
            pass  # never break trading loop on alert failure

    async def trade_opened(self, symbol: str, side: str, volume: float, price: float, strategy: str) -> None:
        await self._send(
            f"🟢 <b>ورود</b>\n{symbol} {side} {volume} @ {price}\nStrategy: {strategy}"
        )

    async def trade_closed(self, symbol: str, side: str, pnl: float, reason: str) -> None:
        emoji = "🟢" if pnl >= 0 else "🔴"
        await self._send(
            f"{emoji} <b>خروج</b>\n{symbol} {side}\nPnL: <code>{pnl:,.2f}</code>\nReason: {reason}"
        )

    async def daily_loss_limit(self, pct: float) -> None:
        await self._send(f"🚨 <b>سقف ضرر روزانه</b> رسید: {pct:.2%}\nورود جدید مسدود شد.")

    async def drawdown_warning(self, pct: float) -> None:
        await self._send(f"⚠️ دراودان: {pct:.2%}")

    async def circuit_breaker(self, reason: str) -> None:
        await self._send(f"🚨 <b>Circuit Breaker</b>\n{reason}")

    async def api_error(self, source: str, message: str) -> None:
        await self._send(f"❌ خطا [{source}]: {message}")

    async def reconciliation_failure(self, message: str) -> None:
        await self._send(f"⚠️ Reconciliation ناموفق:\n{message}")
