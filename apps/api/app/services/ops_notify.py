"""Ops Telegram notify. Token + chat id come from runtime-settings.json.

Never log or return the token. No-op if token or chat id is empty.
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request

from app.services import runtime_settings as rs

logger = logging.getLogger(__name__)


def notify(text: str) -> bool:
    data = rs.load()
    token = str(data.get("telegram_bot_token") or "").strip()
    if not token or token == "••••":
        return False
    chats = str(data.get("telegram_admin_chat_id") or "")
    extra = str(data.get("telegram_allowed_chat_ids") or "")
    ids = [p.strip() for p in (chats + "," + extra).replace(";", ",").split(",") if p.strip()]
    if not ids:
        return False
    sent = False
    for chat_id in ids:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3500]}).encode()
            req = urllib.request.Request(url, data=body, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
            sent = True
        except Exception:
            logger.exception("ops telegram notify failed for a chat id")
    return sent
