"""Trading Hours Guard (Master Prompt §3.2)."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


@dataclass
class SessionWindow:
    name: str
    start: time  # UTC
    end: time    # UTC
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri


# Major FX sessions (approximate UTC)
DEFAULT_SESSIONS = [
    SessionWindow("Sydney", time(21, 0), time(6, 0)),
    SessionWindow("Tokyo", time(0, 0), time(9, 0)),
    SessionWindow("London", time(7, 0), time(16, 0)),
    SessionWindow("NewYork", time(12, 0), time(21, 0)),
    SessionWindow("London_NY_Overlap", time(12, 0), time(16, 0)),
]


class TradingHoursGuard:
    def __init__(
        self,
        allowed_sessions: list[str] | None = None,
        block_weekends: bool = True,
        custom_windows: list[SessionWindow] | None = None,
    ):
        self.allowed_sessions = allowed_sessions  # None = all
        self.block_weekends = block_weekends
        self.windows = custom_windows or DEFAULT_SESSIONS

    def _in_window(self, now: datetime, w: SessionWindow) -> bool:
        t = now.timetz().replace(tzinfo=None) if False else now.time()
        wd = now.weekday()
        if wd not in w.weekdays:
            return False
        if w.start <= w.end:
            return w.start <= t <= w.end
        # overnight window (e.g. Sydney)
        return t >= w.start or t <= w.end

    def allow_new_entries(self, now: datetime | None = None) -> tuple[bool, str]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if self.block_weekends and now.weekday() >= 5:
            return False, "Weekend – market closed / unstable"

        active = [w for w in self.windows if self._in_window(now, w)]
        if self.allowed_sessions is not None:
            active = [w for w in active if w.name in self.allowed_sessions]
            if not active:
                return False, f"Outside allowed sessions: {self.allowed_sessions}"

        if not active:
            return False, "Outside all configured trading sessions"

        names = ", ".join(w.name for w in active)
        return True, f"In session: {names}"
