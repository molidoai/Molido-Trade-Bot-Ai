"""FX session calendar.

Hours are in America/New_York so Sunday open and Friday close follow US DST.
New entries only during London/NY overlap. Weekend, Monday gap, Friday close
and rollover are blocked. Thursday after NY 16:00 blocks new entries so we
do not hold into Friday weekend swap.
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

    def __init__(self, block_weekends: bool = True, overlap_only: bool = True):
        # Kept for backwards compatibility with existing callers (e.g.
        # TradingHoursGuard) -- Sat/pre-17:00-Sun are always closed
        # regardless of this flag's value; there is no "allow weekends"
        # mode, so this no longer changes behavior either way.
        self.block_weekends = block_weekends
        self.overlap_only = overlap_only

    def now_ny(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(NY)

    def is_fx_week_open(self, now: datetime | None = None) -> tuple[bool, str]:
        """FX week runs Sunday 17:00 NY -> Friday 17:00 NY. The three checks
        below are the complete, correctly-scoped closed window; there is
        deliberately no additional `wd >= 5` catch-all -- a previous version
        had one and it accidentally closed all of Sunday including *after*
        17:00, silently skipping the Sydney/Tokyo open every single week."""
        ny = self.now_ny(now)
        wd = ny.weekday()  # Mon=0
        t = ny.time()
        if wd == 4 and t >= time(17, 0):
            return False, "Friday after NY 17:00 - FX closed"
        if wd == 5:
            return False, "Saturday - FX closed"
        if wd == 6 and t < time(17, 0):
            return False, "Sunday before NY 17:00 - FX closed"
        return True, "FX week open"

    def active_sessions(self, now: datetime | None = None) -> list[str]:
        open_, _ = self.is_fx_week_open(now)
        if not open_:
            return []
        ny = self.now_ny(now)
        return [w.name for w in FX_SESSIONS if _in_window(ny, w)]

    def should_flatten(self, now: datetime | None = None) -> tuple[bool, str]:
        """Close opens Friday 16:00 America/New_York."""
        ny = self.now_ny(now)
        if ny.weekday() == 4 and ny.time() >= time(16, 0):
            return True, "Friday after NY 16:00 - flatten open positions"
        return False, ""

    def allow_new_entries(self, now: datetime | None = None) -> tuple[bool, str]:
        ok, why = self.is_fx_week_open(now)
        if not ok:
            return False, why
        ny = self.now_ny(now)
        wd = ny.weekday()
        t = ny.time()
        if wd == 0 and t < time(8, 30):
            return False, "Monday first 30 min NY - gap filter"
        if wd == 3 and t >= time(16, 0):
            return False, "Thursday after NY 16:00 - no new entries into Friday weekend swap"
        if wd == 4 and t >= time(16, 0):
            return False, "Friday after NY 16:00 - no new entries"
        if time(16, 45) <= t <= time(17, 15):
            return False, "NY rollover window"
        active = self.active_sessions(now)
        if not active:
            return False, "Outside Sydney/Tokyo/London/NY sessions"
        if self.overlap_only and "London_NY_Overlap" not in active:
            return False, "New entries only in London/NY overlap"
        return True, "In session: " + ", ".join(active)
