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
            await self.client.send_message(
                self.auth.admin_chat_id,  # type: ignore
                "🤖 Molido Telegram Bot آنلاین شد.\n/start برای راهنما.",
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
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = msg.get("text") or ""
        user = (msg.get("from") or {}).get("username") or ""

        if not self.auth.is_allowed(chat_id):
            logger.warning("Unauthorized telegram chat: %s", chat_id)
            return

        reply = await self.router.handle(chat_id, text, user)
        await self.client.send_message(chat_id, reply)


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
