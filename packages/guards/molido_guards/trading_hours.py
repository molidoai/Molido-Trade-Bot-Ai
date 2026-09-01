"""Trading Hours Guard — NY-aware FX calendar."""

from __future__ import annotations
from datetime import datetime
from molido_guards.sessions import SessionCalendar, SessionWindow, FX_SESSIONS

# Back-compat names used by older imports
DEFAULT_SESSIONS = FX_SESSIONS


class TradingHoursGuard:
    def __init__(
        self,
        allowed_sessions: list[str] | None = None,
        block_weekends: bool = True,
        custom_windows: list[SessionWindow] | None = None,
        overlap_only: bool = True,
    ):
        self.allowed_sessions = allowed_sessions
        # overlap_only was never forwarded, so this guard always fell back to
        # SessionCalendar's own default of True and confined entries to the
        # ~4h London/NY overlap no matter what the deployment had configured.
        self.calendar = SessionCalendar(
            block_weekends=block_weekends, overlap_only=overlap_only
        )
        self.windows = custom_windows or FX_SESSIONS

    def allow_new_entries(self, now: datetime | None = None) -> tuple[bool, str]:
        ok, why = self.calendar.allow_new_entries(now)
        if not ok:
            return False, why
        if self.allowed_sessions is None:
            return True, why
        active = self.calendar.active_sessions(now)
        hit = [n for n in active if n in self.allowed_sessions]
        if not hit:
            return False, f"Outside allowed sessions: {self.allowed_sessions}"
        return True, "In session: " + ", ".join(hit)
