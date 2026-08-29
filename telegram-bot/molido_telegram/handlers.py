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
            return "Commands start with /. /start for help."

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
            return f"unknown command: {cmd}\n/help for commands."
        return await fn(chat_id, args, user_name)

    async def _start(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            "<b>Molido Trade Bot AI</b>\n"
            "----------------\n"
            "Commands:\n"
            "/status - status\n"
            "/balance - balance and equity\n"
            "/pnl - daily pnl\n"
            "/positions - open positions\n"
            "/risk - risk limits\n"
            "/mode - account mode (DEMO/PROP/REAL)\n"
            "/pause - stop new entries\n"
            "/resume - resume (needs confirm)\n"
            "/stop - Master off (needs confirm)\n"
            "/off - Master OFF immediate (admin)\n"
            "/flatten - close all positions (admin)\n"
            "\n"
            "API: POST /api/v1/ops/flatten and POST /api/v1/ops/master {on:false}\n"
            "Telegram uses MOLIDO_API_URL + MOLIDO_API_TOKEN.\n"
            "\n"
            "No profit guarantee.\n"
            f"Mode: <b>{self.state.account_mode}</b> | "
            f"bot: <b>{'ON' if self.state.master_bot_on else 'OFF'}</b>"
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
                return f"status error: {e}"

        circuit = "OPEN" if self.state.circuit_open else "OK"
        master = "ON" if self.state.master_bot_on else "OFF"
        return (
            f"<b>status</b>\n"
            f"mode: <b>{self.state.account_mode}</b>\n"
            f"Master Bot: {master}\n"
            f"Circuit: {circuit}\n"
            f"equity: <code>{self.state.equity:,.2f}</code>\n"
            f"balance: <code>{self.state.balance:,.2f}</code>\n"
            f"open: <code>{self.state.open_positions}</code>\n"
            f"daily pnl: <code>{self.state.daily_pnl:,.2f}</code>"
        )

    async def _balance(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            f"<b>balance</b>\n"
            f"Balance: <code>{self.state.balance:,.2f}</code>\n"
            f"Equity: <code>{self.state.equity:,.2f}</code>\n"
            f"Mode: {self.state.account_mode}"
        )

    async def _pnl(self, chat_id: str, args: list[str], user: str) -> str:
        sign = "+" if self.state.daily_pnl >= 0 else ""
        return f"<b>daily pnl</b>\n<code>{sign}{self.state.daily_pnl:,.2f}</code>"

    async def _positions(self, chat_id: str, args: list[str], user: str) -> str:
        if self.state.open_positions == 0:
            return "no open positions."
        return f"open positions: <b>{self.state.open_positions}</b>\n(details in Dashboard)"

    async def _risk(self, chat_id: str, args: list[str], user: str) -> str:
        return (
            "<b>risk</b>\n"
            "- Stop-Loss required\n"
            "- daily loss / drawdown limits on\n"
            "- PROP mode applies prop-firm rules\n"
            f"Circuit: {'OPEN' if self.state.circuit_open else 'OK'}"
        )

    async def _mode(self, chat_id: str, args: list[str], user: str) -> str:
        return f"account mode: <b>{self.state.account_mode}</b>\nchange mode from Dashboard with audit."

    async def _pause(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "admin only."
        self.state.master_bot_on = False
        if self.state.on_pause:
            await self.state.on_pause()
        await _ops_post("/ops/master", {"on": False, "actor": "telegram"})
        return "new entries paused (Master OFF). open positions still managed."

    async def _off(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "admin only."
        self.state.master_bot_on = False
        if self.state.on_pause:
            await self.state.on_pause()
        ok, detail = await _ops_post("/ops/master", {"on": False, "actor": "telegram /off"})
        extra = " API OK" if ok else f" API: {detail}"
        return "Master OFF." + extra

    async def _flatten(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "admin only."
        if self.state.on_flatten:
            await self.state.on_flatten()
        ok, detail = await _ops_post("/ops/flatten", {"actor": "telegram /flatten", "reason": "telegram"})
        extra = " API OK" if ok else f" API: {detail}"
        return "Flatten requested (close all opens)." + extra

    async def _resume(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "admin only."
        self._pending_confirm[chat_id] = "resume"
        return "to resume type:\n<code>/confirm resume</code>"

    async def _stop(self, chat_id: str, args: list[str], user: str) -> str:
        if not self.is_admin(chat_id):
            return "admin only."
        self._pending_confirm[chat_id] = "stop"
        return "Master off. confirm:\n<code>/confirm stop</code>"

    async def _confirm(self, chat_id: str, action: str) -> str:
        if not self.is_admin(chat_id):
            return "admin only."
        expected = self._pending_confirm.get(chat_id)
        if expected != action:
            return "confirm invalid or expired."
        del self._pending_confirm[chat_id]
        if action == "resume":
            self.state.master_bot_on = True
            if self.state.on_resume:
                await self.state.on_resume()
            await _ops_post("/ops/master", {"on": True, "actor": "telegram"})
            return "Master Bot ON."
        if action == "stop":
            self.state.master_bot_on = False
            if self.state.on_pause:
                await self.state.on_pause()
            await _ops_post("/ops/master", {"on": False, "actor": "telegram"})
            return "Master Bot OFF."
        return "unknown action."
