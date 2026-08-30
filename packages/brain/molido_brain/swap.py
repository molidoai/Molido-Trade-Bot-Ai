"""Overnight swap cost for EV. Not a profit claim; only a cost haircut.

Thursday NY session: weekend hold is expensive when swap is heavily negative.
Wednesday 17:00 NY is the usual triple-swap rollover; Thursday still gates
holding into Friday.
"""

from __future__ import annotations
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

DEFAULT_OVERNIGHT_SWAP_R = 0.03
HEAVY_NEGATIVE_SWAP_R = 0.08  # cost in R; larger = worse for the account


def _ny(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(NY)


def overnight_swap_r(
    symbol: str | None = None,
    side: str | None = None,
    now: datetime | None = None,
    base: float = DEFAULT_OVERNIGHT_SWAP_R,
    quoted: float | None = None,
) -> float:
    """Estimated swap cost in R to subtract from EV.

    `quoted` is a broker-provided (already negative-as-cost) value when known.
    Multi-day / weekend hold multiplies the overnight estimate.
    """
    if quoted is not None:
        cost = abs(float(quoted)) if float(quoted) < 0 else float(quoted)
    else:
        cost = abs(float(base))
    ny = _ny(now)
    wd = ny.weekday()
    t = ny.time()
    # Triple-swap Wednesday after NY 17:00
    if wd == 2 and t >= time(16, 0):
        return cost * 3.0
    # Thursday: weekend (Fri+Sat+Sun) if the trade is held
    if wd == 3 and t >= time(12, 0):
        return cost * 3.0
    if wd == 4:
        return cost * 3.0
    return cost


def veto_weekend_hold(swap_r: float, now: datetime | None = None) -> tuple[bool, str]:
    """If swap is heavily negative on Thursday NY, do not hold into Friday."""
    ny = _ny(now)
    if ny.weekday() == 3 and ny.time() >= time(8, 0) and float(swap_r) >= HEAVY_NEGATIVE_SWAP_R:
        return True, (
            f"swap veto: overnight/weekend cost {swap_r:.3f}R >= {HEAVY_NEGATIVE_SWAP_R} "
            "on Thursday NY (do not hold into Friday)"
        )
    if ny.weekday() == 4 and float(swap_r) >= HEAVY_NEGATIVE_SWAP_R:
        return True, f"swap veto: Friday hold cost {swap_r:.3f}R"
    return False, ""
