"""News Blackout Window (Master Prompt §3.3).

If calendar unavailable or stale → conservative (block optional via flag).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta


@dataclass
class CalendarEvent:
    title: str
    currency: str
    impact: str  # high / medium / low
    time: datetime
    affected_symbols: list[str] = field(default_factory=list)


class NewsBlackoutGuard:
    def __init__(
        self,
        minutes_before: int = 30,
        minutes_after: int = 30,
        block_when_stale: bool = False,
        high_impact_only: bool = True,
    ):
        self.minutes_before = minutes_before
        self.minutes_after = minutes_after
        self.block_when_stale = block_when_stale
        self.high_impact_only = high_impact_only
        self._events: list[CalendarEvent] = []
        self._last_refresh: datetime | None = None
        self._stale_after = timedelta(hours=24)

    def set_events(self, events: list[CalendarEvent]) -> None:
        self._events = events
        self._last_refresh = datetime.now(timezone.utc)

    def is_stale(self) -> bool:
        if self._last_refresh is None:
            return True
        return datetime.now(timezone.utc) - self._last_refresh > self._stale_after

    def allow_new_entries(
        self,
        symbol: str | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        now = now or datetime.now(timezone.utc)

        if self.is_stale():
            if self.block_when_stale:
                return False, "Economic calendar stale – conservative block"
            return True, "Calendar stale – allowing (non-strict mode)"

        for ev in self._events:
            if self.high_impact_only and ev.impact.lower() != "high":
                continue
            start = ev.time - timedelta(minutes=self.minutes_before)
            end = ev.time + timedelta(minutes=self.minutes_after)
            if not (start <= now <= end):
                continue
            if symbol and ev.affected_symbols:
                # EURUSD affected by EUR or USD news
                if not any(c in symbol.upper() for c in [ev.currency.upper(), *ev.affected_symbols]):
                    if ev.currency.upper() not in symbol.upper():
                        continue
            elif symbol and ev.currency.upper() not in symbol.upper():
                continue
            return False, f"News blackout: {ev.title} ({ev.currency})"

        return True, "No high-impact news window"
