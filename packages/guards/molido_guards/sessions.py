"""FX session calendar.

Hours are in America/New_York so Sunday open and Friday close follow US DST.
A fixed UTC offset would shift a whole session for a few weeks each spring.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time
    overnight: bool = False


# Instrument-local (NY) windows used by FX majors.
FX_SESSIONS = [
    SessionWindow("Tokyo", time(19, 0), time(4, 0), overnight=True),
    SessionWindow("London", time(3, 0), time(12, 0)),
    SessionWindow("NewYork", time(8, 0), time(17, 0)),
    SessionWindow("London_NY_Overlap", time(8, 0), time(12, 0)),
]


def _in_window(now_ny: datetime, w: SessionWindow) -> bool:
    t = now_ny.time()
    if w.overnight:
        return t >= w.start or t <= w.end
    return w.start <= t <= w.end


class SessionCalendar:
    """Was this FX market open at this instant, and which liquidity sessions?"""

    def __init__(self, block_weekends: bool = True):
        self.block_weekends = block_weekends

    def now_ny(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(NY)

    def is_fx_week_open(self, now: datetime | None = None) -> tuple[bool, str]:
        ny = self.now_ny(now)
        wd = ny.weekday()  # Mon=0
        t = ny.time()
        # Sunday 17:00 NY open → Friday 17:00 NY close
        if wd == 5:
            return False, "Saturday — FX closed"
        if wd == 6 and t < time(17, 0):
            return False, "Sunday before NY 17:00 — FX closed"
        if wd == 4 and t >= time(17, 0):
            return False, "Friday after NY 17:00 — FX closed"
        if self.block_weekends and wd >= 5:
            return False, "Weekend"
        return True, "FX week open"

    def active_sessions(self, now: datetime | None = None) -> list[str]:
        open_, _ = self.is_fx_week_open(now)
        if not open_:
            return []
        ny = self.now_ny(now)
        return [w.name for w in FX_SESSIONS if _in_window(ny, w)]

    def allow_new_entries(self, now: datetime | None = None) -> tuple[bool, str]:
        ok, why = self.is_fx_week_open(now)
        if not ok:
            return False, why
        active = self.active_sessions(now)
        if not active:
            return False, "Outside Sydney/Tokyo/London/NY sessions"
        return True, "In session: " + ", ".join(active)
