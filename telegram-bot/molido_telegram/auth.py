"""Telegram access control – admin / allowed chats only."""

from __future__ import annotations


class TelegramAuth:
    def __init__(
        self,
        admin_chat_id: str | None,
        allowed_chat_ids: list[str] | None = None,
    ):
        self.admin_chat_id = str(admin_chat_id) if admin_chat_id else None
        allowed = set(allowed_chat_ids or [])
        if self.admin_chat_id:
            allowed.add(self.admin_chat_id)
        self.allowed = allowed

    def is_allowed(self, chat_id: str | int) -> bool:
        if not self.allowed:
            # No restriction configured → allow only if admin set to same (safe default: deny all if empty)
            return False
        return str(chat_id) in self.allowed

    def is_admin(self, chat_id: str | int) -> bool:
        return self.admin_chat_id is not None and str(chat_id) == self.admin_chat_id
