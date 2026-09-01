"""Ops Telegram notify. Token + chat id come from runtime-settings.json.

Never log or return the token. No-op if token is empty. Chat ids come only
from telegram_admin_chat_id / telegram_allowed_chat_ids — never hardcoded,
per docs/DEPLOY_MTRADE.md ("No secrets, IPs, or chat ids in git").
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request

from app.services import runtime_settings as rs

logger = logging.getLogger(__name__)


def _chat_ids(data: dict) -> list[str]:
    chats = str(data.get("telegram_admin_chat_id") or "")
    extra = str(data.get("telegram_allowed_chat_ids") or "")
    ids = [p.strip() for p in (chats + "," + extra).replace(";", ",").split(",") if p.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def notify(text: str) -> bool:
    data = rs.load()
    token = str(data.get("telegram_bot_token") or "").strip()
    if not token or token == "••••":
        return False
    ids = _chat_ids(data)
    if not ids:
        return False
    sent = False
    for chat_id in ids:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            body = urllib.parse.urlencode(
                # parse_mode=HTML so the <b> tags in the Persian reports render as
                # bold instead of showing up as literal markup.
                {"chat_id": chat_id, "text": text[:3500], "parse_mode": "HTML"}
            ).encode()
            req = urllib.request.Request(url, data=body, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
            sent = True
        except Exception:
            logger.exception("ops telegram notify failed for a chat id")
    return sent
