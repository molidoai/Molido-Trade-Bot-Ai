"""
Telegram bot main loop.

Control/Notification only – never bypasses Risk Engine.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID in env.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os

from molido_telegram.client import TelegramClient
from molido_telegram.auth import TelegramAuth
from molido_telegram.handlers import CommandRouter, BotState
from molido_telegram.alerts import AlertService
from molido_telegram import menu

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(
        self,
        token: str,
        admin_chat_id: str,
        allowed_chat_ids: list[str] | None = None,
        state: BotState | None = None,
    ):
        self.client = TelegramClient(token)
        self.auth = TelegramAuth(admin_chat_id, allowed_chat_ids)
        self.state = state or BotState()
        self.router = CommandRouter(self.state, self.auth.is_admin)
        self.alerts = AlertService(self.client, admin_chat_id)
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("Telegram bot started")
        try:
            await self.client.set_commands([
                {"command": "start", "description": "menu"},
                {"command": "status", "description": "status"},
                {"command": "balance", "description": "balance"},
                {"command": "positions", "description": "open positions"},
                {"command": "risk", "description": "risk limits"},
            ])
            body, _ = menu.render("menu")
            await self.client.send_message(
                self.auth.admin_chat_id,  # type: ignore
                body,
                reply_markup=menu.REPLY_KB,
            )
        except Exception as e:
            logger.warning("Could not send startup message: %s", e)

        while self._running:
            try:
                updates = await self.client.get_updates(timeout=25)
                for upd in updates:
                    await self._process_update(upd)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Polling error")
                await asyncio.sleep(3)

    async def stop(self) -> None:
        self._running = False

    async def _process_update(self, update: dict) -> None:
        cb = update.get("callback_query")
        if cb:
            await self._process_callback(cb)
            return

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = (msg.get("text") or "").strip()
        user = (msg.get("from") or {}).get("username") or ""

        if not self.auth.is_allowed(chat_id):
            logger.warning("Unauthorized telegram chat: %s", chat_id)
            return

        # A tapped keyboard button arrives as ordinary text, so route on the
        # label first. Everything is reachable by tapping or by typing.
        view = menu.view_for_text(text)
        if view == "control":
            if not self.auth.is_admin(chat_id):
                await self.client.send_message(chat_id, "فقط مدیر", reply_markup=menu.REPLY_KB)
                return
            await self.client.send_message(chat_id, menu.CONTROL_TEXT, reply_markup=menu.CONTROL_KB)
            return
        if view:
            body, _ = menu.render(view)
            await self.client.send_message(chat_id, body, reply_markup=menu.REPLY_KB)
            return

        if text.startswith("/"):
            reply = await self.router.handle(chat_id, text, user)
            if reply:
                await self.client.send_message(chat_id, reply, reply_markup=menu.REPLY_KB)
                return
        body, _ = menu.render("menu")
        await self.client.send_message(chat_id, body, reply_markup=menu.REPLY_KB)

    async def _process_callback(self, cb: dict) -> None:
        chat_id = str(((cb.get("message") or {}).get("chat") or {}).get("id", ""))
        message_id = (cb.get("message") or {}).get("message_id")
        data = str(cb.get("data") or "")
        user = (cb.get("from") or {}).get("username") or ""
        cb_id = str(cb.get("id") or "")

        if not self.auth.is_allowed(chat_id):
            await self.client.answer_callback(cb_id, "دسترسی ندارید")
            return

        kind, _, arg = data.partition(":")

        if kind == "v" and arg == "control":
            if not self.auth.is_admin(chat_id):
                await self.client.answer_callback(cb_id, "فقط مدیر")
                return
            body, keyboard = menu.CONTROL_TEXT, menu.CONTROL_KB
        elif kind == "v":
            body, keyboard = menu.render(arg)
        elif kind == "c":
            # Ask before doing: a button must not be a shortcut past the
            # confirmation the typed commands require.
            if not self.auth.is_admin(chat_id):
                await self.client.answer_callback(cb_id, "فقط مدیر")
                return
            body, keyboard = menu.confirm_text(arg), menu.confirm_kb(arg)
        elif kind == "k":
            if not self.auth.is_admin(chat_id):
                await self.client.answer_callback(cb_id, "فقط مدیر")
                return
            body = await self.router.handle(chat_id, "/" + arg, user)
            keyboard = menu.BACK_KB
        else:
            body, keyboard = menu.render("menu")

        await self.client.answer_callback(cb_id)
        if message_id:
            await self.client.edit_message(chat_id, message_id, body, reply_markup=keyboard)
        else:
            await self.client.send_message(chat_id, body, reply_markup=keyboard)


def _runtime_settings() -> dict:
    """Dashboard-managed settings, shared with the engine over the data volume."""
    path = os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("runtime settings unreadable: %s", path)
        return {}


def _setting(rt: dict, key: str, env: str) -> str:
    """Runtime settings win over env. The token and chat ids are entered in the
    dashboard and persisted to runtime-settings.json; reading only the
    environment meant the bot could not be configured from the UI at all.
    "••••" is the masked placeholder the settings API returns -- never a value.
    """
    val = str(rt.get(key) or "").strip()
    if val and val != "••••":
        return val
    return (os.getenv(env) or "").strip()


async def main():
    logging.basicConfig(level=logging.INFO)
    # Re-read on every attempt so entering the token in the dashboard starts
    # the bot without a container restart.
    while True:
        rt = _runtime_settings()
        token = _setting(rt, "telegram_bot_token", "TELEGRAM_BOT_TOKEN")
        admin = _setting(rt, "telegram_admin_chat_id", "TELEGRAM_ADMIN_CHAT_ID")
        allowed = [
            x.strip()
            for x in _setting(rt, "telegram_allowed_chat_ids", "TELEGRAM_ALLOWED_CHAT_IDS").replace(";", ",").split(",")
            if x.strip()
        ]
        if token and admin:
            break
        logger.info("telegram token/admin chat id not configured yet; waiting")
        await asyncio.sleep(30)

    bot = TelegramBot(token, admin, allowed or [admin])
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
