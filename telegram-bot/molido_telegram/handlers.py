"""
Command handlers (Master Prompt section 31).

Commands: /start /status /balance /positions /pnl /risk /pause /resume /stop
/flatten /off
Sensitive ops require admin + confirmation pattern where needed.

Telegram /flatten and /off call POST /api/v1/ops/flatten and
POST /api/v1/ops/master {"on": false} when MOLIDO_API_URL + MOLIDO_API_TOKEN
(admin JWT) are set. Otherwise they use BotState callbacks if the engine wired them.
"""

from __future__ import annotations
import os
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
    on_pause: Callable[[], Awaitable[None]] | None = None
    on_resume: Callable[[], Awaitable[None]] | None = None
    on_flatten: Callable[[], Awaitable[None]] | None = None
    get_status: Callable[[], Awaitable[dict[str, Any]]] | None = None


async def _ops_post(path: str, body: dict) -> tuple[bool, str]:
    """Call API ops routes. Telegram bot should set MOLIDO_API_URL and MOLIDO_API_TOKEN."""
    base = (os.getenv("MOLIDO_API_URL") or os.getenv("OPS_API_URL") or "").rstrip("/")
    token = os.getenv("MOLIDO_API_TOKEN") or ""
    if not base:
        return False, "MOLIDO_API_URL not set"
    url = f"{base}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json=body, headers=headers)
            return r.is_success, r.text[:400]
    except Exception as exc:
        return False, str(exc)


class CommandRouter:
    def __init__(self, state: BotState, auth_is_admin: Callable[[str], bool]):
        self.state = state
        self.is_admin = auth_is_admin
        self._pending_confirm: dict[str, str] = {}  # chat_id -> action

    async def handle(self, chat_id: str, text: str, user_name: str = "") -> str:
        text = (text or "").strip()
        if not text.startswith("/"):
            return "دستورها با / شروع می‌شوند. برای راهنما /start را بزنید."

        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:]

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
            "/off": self._off,
            "/flatten": self._flatten,
            "/mode": self._mode,
        }
        fn = handlers.get(cmd)
        if not fn:
            return f"دستور ناشناخته: {cmd}\nبرای فهرست دستورها /help را بزنید."
        return await fn(chat_id, args, user_name)

    async def _start(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            "<b>ربات معاملاتی Molido</b>\n"
            "----------------\n"
            "دستورها:\n"
            "/status - وضعیت کلی\n"
            "/balance - موجودی و اکوئیتی\n"
            "/pnl - سود و زیان امروز\n"
            "/positions - پوزیشن‌های باز\n"
            "/risk - محدودیت‌های ریسک\n"
            "/mode - حالت حساب (DEMO/PROP/REAL)\n"
            "/pause - توقف ورودهای جدید\n"
            "/resume - ازسرگیری (نیاز به تأیید)\n"
            "/stop - خاموش کردن مستر (نیاز به تأیید)\n"
            "/off - خاموشی فوری مستر (فقط مدیر)\n"
            "/flatten - بستن همه پوزیشن‌ها (فقط مدیر)\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "⚠️ هیچ تضمین سودی وجود ندارد.\n"
            f"حالت حساب: <b>{self.state.account_mode}</b> | "
            f"مستر: <b>{'روشن' if self.state.master_bot_on else 'خاموش'}</b>"
        )

    # The typed commands answer from the same live snapshot the buttons use.
    #
    # They used to read BotState, which is populated only if the engine wires
    # `get_status` -- and it never does, because the bot runs in its own
    # container with no link to the engine. So /status reported equity 0.00 and
    # /positions said "no open positions" while the account held two. The
    # buttons were fixed to read the engine's snapshot off the shared volume
    # and the typed commands were left behind, which is worse than either
    # being broken alone: the same question got two different answers depending
    # on how it was asked, and the wrong one looked authoritative.
    #
    # menu.render() also stamps the snapshot's age, so a stale file says so
    # instead of quietly presenting old numbers as current.
    @staticmethod
    def _live(view: str) -> str | None:
        """The rendered live view, or None when there is no snapshot to show.

        The None case matters: menu.render() answers with its own "no snapshot
        yet" text rather than failing, so returning that unconditionally made
        the BotState fallback below unreachable dead code -- and a caller that
        *had* populated BotState (the engine wiring get_status, or a test) got
        "no data" instead of the state it supplied. Check for an actual
        snapshot first and let the caller decide.
        """
        try:
            from molido_telegram import live_data as ld
            from molido_telegram import menu
            if not ld.all_portfolios():
                return None
            text, _kb = menu.render(view)
            return text
        except Exception:
            return None

    async def _status(self, chat_id: str, args: list[str], user: str) -> str:
        live = self._live("status")
        if live:
            return live
        circuit = "قطع شده ⛔" if self.state.circuit_open else "سالم ✅"
        master = "روشن" if self.state.master_bot_on else "خاموش"
        return (
            f"<b>وضعیت</b>\n"
            f"حالت حساب: <b>{self.state.account_mode}</b>\n"
            f"مستر: {master}\n"
            f"مدار حفاظتی: {circuit}\n"
            f"اکوئیتی: <code>{self.state.equity:,.2f}</code>\n"
            f"موجودی: <code>{self.state.balance:,.2f}</code>\n"
            f"پوزیشن باز: <code>{self.state.open_positions}</code>\n"
            "⚠️ عکس زنده در دسترس نیست؛ اعداد بالا ممکن است کهنه باشند."
        )

    async def _balance(self, chat_id: str, args: list[str], user: str) -> str:
        live = self._live("balance")
        if live:
            return live
        return (
            f"<b>موجودی</b>\n"
            f"موجودی: <code>{self.state.balance:,.2f}</code>\n"
            f"اکوئیتی: <code>{self.state.equity:,.2f}</code>\n"
            f"حالت حساب: {self.state.account_mode}\n"
            "⚠️ عکس زنده در دسترس نیست."
        )

    async def _pnl(self, chat_id: str, args: list[str], user: str) -> str:
        live = self._live("balance")
        if live:
            return live
        sign = "+" if self.state.daily_pnl >= 0 else ""
        return f"<b>سود/زیان امروز</b>\n<code>{sign}{self.state.daily_pnl:,.2f}</code>"

    async def _positions(self, chat_id: str, args: list[str], user: str) -> str:
        live = self._live("positions")
        if live:
            return live
        if self.state.open_positions == 0:
            return "هیچ پوزیشن بازی وجود ندارد."
        return f"پوزیشن‌های باز: <b>{self.state.open_positions}</b>\n⚠️ عکس زنده در دسترس نیست."

    async def _risk(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            "<b>ریسک</b>\n"
            "- حد ضرر (Stop-Loss) اجباری است\n"
            "- سقف ضرر روزانه و دراودان فعال است\n"
            "- در حالت PROP قوانین پراپ‌فرم اعمال می‌شود\n"
            f"مدار حفاظتی: {'قطع شده ⛔' if self.state.circuit_open else 'سالم ✅'}"
        )

    async def _mode(self, chat_id: str, args: list[str], user: str) -> str:
        return f"حالت حساب: <b>{self.state.account_mode}</b>\nتغییر حالت فقط از داشبورد و با تأیید دومرحله‌ای انجام می‌شود."

    async def _pause(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط مدیر مجاز است."
        self.state.master_bot_on = False
        if self.state.on_pause:
            await self.state.on_pause()
        await _ops_post("/ops/master", {"on": False, "actor": "telegram"})
        return "ورودهای جدید متوقف شد (مستر خاموش). پوزیشن‌های باز همچنان مدیریت می‌شوند."

    async def _off(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط مدیر مجاز است."
        self.state.master_bot_on = False
        if self.state.on_pause:
            await self.state.on_pause()
        ok, detail = await _ops_post("/ops/master", {"on": False, "actor": "telegram /off"})
        extra = " ✅" if ok else f" (خطای API: {detail})"
        return "مستر خاموش شد." + extra

    async def _flatten(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط مدیر مجاز است."
        if self.state.on_flatten:
            await self.state.on_flatten()
        ok, detail = await _ops_post("/ops/flatten", {"actor": "telegram /flatten", "reason": "telegram"})
        extra = " ✅" if ok else f" (خطای API: {detail})"
        return "درخواست بستن همه پوزیشن‌ها ارسال شد." + extra

    async def _resume(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط مدیر مجاز است."
        self._pending_confirm[chat_id] = "resume"
        return "برای ازسرگیری این را بفرست:\n<code>/confirm resume</code>"

    async def _stop(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط مدیر مجاز است."
        self._pending_confirm[chat_id] = "stop"
        return "خاموش کردن مستر. برای تأیید بفرست:\n<code>/confirm stop</code>"

    async def _confirm(self, chat_id: str, action: str) -> str:
        if not self.is_admin(chat_id):
            return "⛔ فقط مدیر مجاز است."
        expected = self._pending_confirm.get(chat_id)
        if expected != action:
            return "تأیید نامعتبر یا منقضی شده است."
        del self._pending_confirm[chat_id]
        if action == "resume":
            self.state.master_bot_on = True
            if self.state.on_resume:
                await self.state.on_resume()
            await _ops_post("/ops/master", {"on": True, "actor": "telegram"})
            return "مستر روشن شد ✅"
        if action == "stop":
            self.state.master_bot_on = False
            if self.state.on_pause:
                await self.state.on_pause()
            await _ops_post("/ops/master", {"on": False, "actor": "telegram"})
            return "مستر خاموش شد."
        return "عملیات ناشناخته."
