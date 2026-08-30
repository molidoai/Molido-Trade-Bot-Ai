"""Minimal Telegram Bot API client (HTTP long-polling)."""

from __future__ import annotations
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, token: str, timeout: float = 30.0):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout
        self._offset = 0

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base}/sendMessage", json=payload)
            r.raise_for_status()
            return r.json()

    async def get_updates(self, timeout: int = 25) -> list[dict]:
        params = {"offset": self._offset, "timeout": timeout}
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            r = await client.get(f"{self.base}/getUpdates", params=params)
            r.raise_for_status()
            data = r.json()
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates
