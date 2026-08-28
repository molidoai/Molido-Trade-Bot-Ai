"""
Command handlers (Master Prompt §31).

Commands: /start /status /balance /positions /pnl /risk /pause /resume /stop
Sensitive ops require admin + confirmation pattern where needed.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class BotState:
    """Shared mutable state the bot can read/control."""
    master_bot_on: bool = False
    account_mode: str = "DEMO"
    equity: float = 0.0
    balance: float = 0.0
    open_positions: int = 0
    daily_pnl: float = 0.0
    circuit_open: bool = False
    last_message: str = ""
    # Optional callbacks wired by Trading Engine later
    on_pause: Callable[[], Awaitable[None]] | None = None
    on_resume: Callable[[], Awaitable[None]] | None = None
    get_status: Callable[[], Awaitable[dict[str, Any]]] | None = None


class CommandRouter:
    def __init__(self, state: BotState, auth_is_admin: Callable[[str], bool]):
        self.state = state
        self.is_admin = auth_is_admin
        self._pending_confirm: dict[str, str] = {}  # chat_id → action

    async def handle(self, chat_id: str, text: str, user_name: str = "") -> str:
        text = (text or "").strip()
        if not text.startswith("/"):
            return "دستورات با / شروع می‌شوند. /start برای راهنما."

        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:]

        # Confirmation flow for sensitive actions
        if cmd == "/confirm" and args:
            return await self._confirm(chat_id, args[0])

        handlers = {
            "/start": self._start,
            "/help": self._start,
            "/status": self._status,
            "/balance": self._balance,
            "/pnl": self._pnl,
            "/positions": self._positions,
            "/risk": self._risk,
            "/pause": self._pause,
            "/resume": self._resume,
            "/stop": self._stop,
            "/mode": self._mode,
        }
        fn = handlers.get(cmd)
        if not fn:
            return f"دستور ناشناخته: {cmd}\n/help برای لیست دستورات."
        return await fn(chat_id, args, user_name)

    async def _start(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            "<b>Molido Trade Bot AI</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "دستورات:\n"
            "/status — وضعیت کلی\n"
            "/balance — موجودی و اکوئیتی\n"
            "/pnl — سود/زیان روزانه\n"
            "/positions — پوزیشن‌های باز\n"
            "/risk — محدودیت‌های ریسک\n"
            "/mode — حالت حساب (DEMO/PROP/REAL)\n"
            "/pause — توقف ورود جدید\n"
            "/resume — ازسرگیری (نیاز تأیید)\n"
            "/stop — خاموش کردن Master (نیاز تأیید)\n"
            "\n"
            "⚠️ هیچ تضمین سودی وجود ندارد.\n"
            f"حالت فعلی: <b>{self.state.account_mode}</b> | "
            f"ربات: <b>{'ON' if self.state.master_bot_on else 'OFF'}</b>"
        )

    async def _status(self, chat_id: str, args: list[str], user: str) -> str:
        if self.state.get_status:
            try:
                data = await self.state.get_status()
                self.state.equity = data.get("equity", self.state.equity)
                self.state.balance = data.get("balance", self.state.balance)
                self.state.open_positions = data.get("open_positions", self.state.open_positions)
                self.state.master_bot_on = data.get("master_bot_on", self.state.master_bot_on)
                self.state.account_mode = data.get("account_mode", self.state.account_mode)
                self.state.circuit_open = data.get("circuit_open", self.state.circuit_open)
            except Exception as e:
                return f"خطا در دریافت وضعیت: {e}"

        circuit = "🔴 باز" if self.state.circuit_open else "🟢 بسته"
        master = "🟢 ON" if self.state.master_bot_on else "🔴 OFF"
        return (
            f"<b>وضعیت سیستم</b>\n"
            f"حالت حساب: <b>{self.state.account_mode}</b>\n"
            f"Master Bot: {master}\n"
            f"Circuit Breaker: {circuit}\n"
            f"اکوئیتی: <code>{self.state.equity:,.2f}</code>\n"
            f"موجودی: <code>{self.state.balance:,.2f}</code>\n"
            f"پوزیشن باز: <code>{self.state.open_positions}</code>\n"
            f"PnL روزانه: <code>{self.state.daily_pnl:,.2f}</code>"
        )

    async def _balance(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            f"<b>موجودی</b>\n"
            f"Balance: <code>{self.state.balance:,.2f}</code>\n"
            f"Equity: <code>{self.state.equity:,.2f}</code>\n"
            f"Mode: {self.state.account_mode}"
        )

    async def _pnl(self, chat_id: str, args: list[str], user: str) -> str:
        sign = "+" if self.state.daily_pnl >= 0 else ""
        return f"<b>PnL روزانه</b>\n<code>{sign}{self.state.daily_pnl:,.2f}</code>"

    async def _positions(self, chat_id: str, args: list[str], user: str) -> str:
        if self.state.open_positions == 0:
            return "پوزیشن بازی وجود ندارد."
        return f"تعداد پوزیشن باز: <b>{self.state.open_positions}</b>\n(جزئیات کامل در Dashboard)"

    async def _risk(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            "<b>ریسک</b>\n"
            "• Stop-Loss اجباری\n"
            "• سقف ضرر روزانه / دراودان فعال\n"
            "• در حالت PROP قوانین شرکت پراپ اعمال می‌شود\n"
            f"Circuit: {'OPEN' if self.state.circuit_open else 'OK'}"
        )

    async def _mode(self, chat_id: str, args: list[str], user: str) -> str:
        return f"حالت حساب فعلی: <b>{self.state.account_mode}</b>\nتغییر حالت فقط از Dashboard با Audit."

    async def _pause(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط ادمین می‌تواند pause کند."
        self.state.master_bot_on = False
        if self.state.on_pause:
            await self.state.on_pause()
        return "⏸ ورود جدید متوقف شد (Master OFF). پوزیشن‌های باز همچنان مدیریت می‌شوند."

    async def _resume(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط ادمین."
        self._pending_confirm[chat_id] = "resume"
        return "برای ازسرگیری تایپ کنید:\n<code>/confirm resume</code>"

    async def _stop(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط ادمین."
        self._pending_confirm[chat_id] = "stop"
        return "⚠️ خاموشی کامل Master. تأیید:\n<code>/confirm stop</code>"

    async def _confirm(self, chat_id: str, action: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط ادمین."
        expected = self._pending_confirm.get(chat_id)
        if expected != action:
            return "تأیید نامعتبر یا منقضی شده."
        del self._pending_confirm[chat_id]
        if action == "resume":
            self.state.master_bot_on = True
            if self.state.on_resume:
                await self.state.on_resume()
            return "▶️ Master Bot روشن شد."
        if action == "stop":
            self.state.master_bot_on = False
            if self.state.on_pause:
                await self.state.on_pause()
            return "⏹ Master Bot خاموش شد."
        return "اقدام ناشناخته."
