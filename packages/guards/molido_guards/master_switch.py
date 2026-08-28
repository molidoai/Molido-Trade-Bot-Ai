"""Persistent Master ON/OFF and account mode (Master Prompt §3.1).

Uses in-memory + optional Redis. Defaults: Master OFF, mode DEMO.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

AccountMode = Literal["DEMO", "PROP", "REAL"]


@dataclass
class OperationalState:
    master_on: bool = False
    account_mode: AccountMode = "DEMO"
    updated_at: str = ""
    updated_by: str = "system"
    source: str = "system"  # dashboard / telegram / system


class MasterSwitchStore:
    def __init__(self, redis_client: Any | None = None, key: str = "molido:ops_state"):
        self.redis = redis_client
        self.key = key
        self._state = OperationalState(
            master_on=False,
            account_mode="DEMO",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def get(self) -> OperationalState:
        if self.redis is not None:
            try:
                raw = self.redis.get(self.key)
                if raw:
                    data = json.loads(raw)
                    self._state = OperationalState(**data)
            except Exception:
                logger.exception("Redis read failed – using memory")
        return self._state

    def set_master(self, on: bool, by: str = "system", source: str = "system") -> OperationalState:
        st = self.get()
        st.master_on = on
        st.updated_at = datetime.now(timezone.utc).isoformat()
        st.updated_by = by
        st.source = source
        self._persist(st)
        return st

    def set_mode(
        self,
        mode: AccountMode,
        by: str = "system",
        source: str = "system",
        confirm_token: str | None = None,
    ) -> OperationalState:
        st = self.get()
        if mode == "REAL" and confirm_token != "CONFIRM_REAL":
            raise PermissionError("REAL mode requires confirm_token=CONFIRM_REAL")
        if mode == "PROP" and confirm_token not in (None, "CONFIRM_PROP", "CONFIRM_REAL"):
            # PROP allowed with CONFIRM_PROP or open from DEMO with explicit token
            if st.account_mode != "PROP" and confirm_token != "CONFIRM_PROP":
                raise PermissionError("PROP mode requires confirm_token=CONFIRM_PROP")
        st.account_mode = mode
        st.updated_at = datetime.now(timezone.utc).isoformat()
        st.updated_by = by
        st.source = source
        self._persist(st)
        return st

    def _persist(self, st: OperationalState) -> None:
        self._state = st
        if self.redis is not None:
            try:
                self.redis.set(self.key, json.dumps(asdict(st)))
            except Exception:
                logger.exception("Redis write failed")
