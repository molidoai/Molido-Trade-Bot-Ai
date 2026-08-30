"""Telegram trade alerts. Token and chat ids come from dashboard settings.

Never log or return the token. Chat ids come only from
telegram_admin_chat_id / telegram_allowed_chat_ids (runtime settings or env)
— never hardcoded, per docs/DEPLOY_MTRADE.md ("No secrets, IPs, or chat ids
in git").
"""

from __future__ import annotations
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def _load_runtime() -> dict:
    path = os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _chat_ids(rt: dict) -> list[str]:
    chats = str(rt.get("telegram_admin_chat_id") or os.getenv("TELEGRAM_ADMIN_CHAT_ID") or "")
    extra = str(rt.get("telegram_allowed_chat_ids") or os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or "")
    ids = [p.strip() for p in (chats + "," + extra).replace(";", ",").split(",") if p.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def notify(text: str) -> None:
    rt = _load_runtime()
    token = str(rt.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token or token == "••••":
        return
    for chat_id in _chat_ids(rt):
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3500]}).encode()
            req = urllib.request.Request(url, data=body, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
        except Exception:
            logger.exception("telegram notify failed for a chat id")
