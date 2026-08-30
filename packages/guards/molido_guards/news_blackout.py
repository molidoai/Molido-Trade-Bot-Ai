"""News Blackout Window (Master Prompt §3.3).

If calendar unavailable or stale -> conservative. A live calendar (fetched
from NEWS_CALENDAR_URL) is preferred; when none is configured, or the fetch
fails, `refresh_calendar()` falls back to a static table of recurring
high-impact US data release windows so there's always something on disk to
load (README: "Empty -> static 14-day high-impact table").

Even when no calendar has ever been loaded, `in_fail_closed_window` still
blocks new entries during the hours most high-impact USD data actually
prints (08:25-08:35 America/New_York on weekdays, and the FOMC-style
13:55-14:15 window on Wednesdays) — a fully offline/misconfigured deployment
should refuse to trade blind through those windows rather than silently
allow everything.
"""

from __future__ import annotations
import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")


@dataclass
class CalendarEvent:
    title: str
    currency: str
    impact: str  # high / medium / low
    time: datetime
    affected_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "currency": self.currency,
            "impact": self.impact,
            "time": self.time.isoformat(),
            "affected_symbols": self.affected_symbols,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarEvent":
        return cls(
            title=str(data.get("title", "")),
            currency=str(data.get("currency", "")),
            impact=str(data.get("impact", "high")),
            time=datetime.fromisoformat(str(data["time"])),
            affected_symbols=list(data.get("affected_symbols") or []),
        )


def default_calendar_path() -> str:
    return os.getenv("NEWS_CALENDAR_PATH", "/app/data/news_calendar.json")


def static_high_impact_events(now: datetime | None = None, days: int = 14) -> list[CalendarEvent]:
    """Recurring-schedule approximation, not a real economic calendar.

    Most US high-impact releases (NFP, CPI, PPI, Retail Sales, Jobless
    Claims, GDP) print at 08:30 America/New_York; FOMC statements print at
    14:00. Without a live feed we don't know the exact dates, so every
    weekday's 08:30 window is marked as a *possible* release and every
    Wednesday's 14:00 window as a possible FOMC — conservative in the sense
    that it's fine to sit out a few extra cycles, not fine to trade through
    an actual NFP/FOMC print.
    """
    now = now or datetime.now(timezone.utc)
    start = now.astimezone(NY)
    events: list[CalendarEvent] = []
    for i in range(days + 1):
        day = (start + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        if day.weekday() >= 5:  # Saturday/Sunday — no releases
            continue
        data_time = day.replace(hour=8, minute=30)
        events.append(
            CalendarEvent(
                title="US high-impact data (NFP/CPI/PPI/Retail Sales/Jobless Claims, approx static table)",
                currency="USD",
                impact="high",
                time=data_time.astimezone(timezone.utc),
            )
        )
        if day.weekday() == 2:  # Wednesday — possible FOMC rate decision
            fomc_time = day.replace(hour=14, minute=0)
            events.append(
                CalendarEvent(
                    title="FOMC rate decision (approx static table)",
                    currency="USD",
                    impact="high",
                    time=fomc_time.astimezone(timezone.utc),
                )
            )
    return events


def in_fail_closed_window(now: datetime | None = None) -> tuple[bool, str]:
    """True when `now` falls in a window where a high-impact US release is
    likely enough that we should refuse new entries even with zero calendar
    data loaded."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(NY)
    if local.weekday() >= 5:
        return False, ""
    data_start = local.replace(hour=8, minute=25, second=0, microsecond=0)
    data_end = local.replace(hour=8, minute=35, second=0, microsecond=0)
    if data_start <= local <= data_end:
        return True, "News blackout fail-closed: inside daily US data release window (08:30 NY, no calendar loaded)"
    if local.weekday() == 2:
        fomc_start = local.replace(hour=13, minute=55, second=0, microsecond=0)
        fomc_end = local.replace(hour=14, minute=15, second=0, microsecond=0)
        if fomc_start <= local <= fomc_end:
            return True, "News blackout fail-closed: inside possible FOMC window (14:00 NY Wednesday, no calendar loaded)"
    return False, ""


def load_calendar_file(path: str | os.PathLike) -> list[CalendarEvent]:
    """Read a previously-written calendar JSON file ({"events": [...]})."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CalendarEvent.from_dict(e) for e in raw.get("events", [])]


def refresh_calendar(path: str | os.PathLike | None = None, url: str = "", timeout: float = 6.0) -> dict:
    """Fetch NEWS_CALENDAR_URL (JSON: {"events": [...]}) if configured,
    else fall back to the static table. Always (atomically) writes `path`
    so a later load_calendar_file()/load_from_disk() call succeeds even
    fully offline."""
    path = str(path or default_calendar_path())
    url = url if url != "" else os.getenv("NEWS_CALENDAR_URL", "")
    events: list[CalendarEvent] = []
    source = "static"
    if url:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            raw_events = raw.get("events", raw) if isinstance(raw, dict) else raw
            events = [CalendarEvent.from_dict(e) for e in raw_events]
            source = "live"
        except Exception:
            logger.exception("news calendar fetch failed; falling back to static table")
            source = "static-fallback"
    if not events:
        events = static_high_impact_events()

    payload = {
        "source": source,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "events": [e.to_dict() for e in events],
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(p)
    return payload


class NewsBlackoutGuard:
    def __init__(
        self,
        minutes_before: int = 30,
        minutes_after: int = 30,
        block_when_stale: bool = False,
        high_impact_only: bool = True,
        calendar_path: str | os.PathLike | None = None,
    ):
        self.minutes_before = minutes_before
        self.minutes_after = minutes_after
        self.block_when_stale = block_when_stale
        self.high_impact_only = high_impact_only
        self.calendar_path = calendar_path
        self._events: list[CalendarEvent] = []
        self._last_refresh: datetime | None = None
        self._stale_after = timedelta(hours=24)

    def set_events(self, events: list[CalendarEvent]) -> None:
        self._events = events
        self._last_refresh = datetime.now(timezone.utc)

    def load_from_disk(self) -> bool:
        """Load events from self.calendar_path, if set and readable."""
        if not self.calendar_path:
            return False
        try:
            events = load_calendar_file(self.calendar_path)
        except Exception:
            logger.debug("news calendar not readable at %s", self.calendar_path)
            return False
        self.set_events(events)
        return True

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
            fail_closed, why = in_fail_closed_window(now)
            if fail_closed:
                return False, why
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
