"""
Anomaly detection (Master Prompt §23).

Detects: price spike, spread spike, stale data, abnormal move vs ATR.
On severe anomaly → recommend Circuit Breaker (caller decides).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Sequence

from molido_shared.types import Tick, Candle


@dataclass
class AnomalyEvent:
    kind: str
    severity: str          # info / warning / critical
    symbol: str
    message: str
    should_halt_entries: bool = False


class AnomalyDetector:
    def __init__(
        self,
        max_spread_points: float = 50.0,
        spike_atr_mult: float = 5.0,
        stale_seconds: float = 30.0,
    ):
        self.max_spread_points = max_spread_points
        self.spike_atr_mult = spike_atr_mult
        self.stale_seconds = stale_seconds
        self._last_mid: dict[str, float] = {}

    def check_tick(self, tick: Tick, atr: float | None = None, point: float = 0.0001) -> list[AnomalyEvent]:
        events: list[AnomalyEvent] = []
        now = datetime.now(timezone.utc)
        age = (now - tick.time).total_seconds() if tick.time.tzinfo else 0

        if age > self.stale_seconds:
            events.append(AnomalyEvent(
                kind="stale_data",
                severity="critical",
                symbol=tick.symbol,
                message=f"Tick age {age:.1f}s > {self.stale_seconds}s",
                should_halt_entries=True,
            ))

        spread_pts = tick.spread / point if point else 0
        if spread_pts > self.max_spread_points:
            events.append(AnomalyEvent(
                kind="spread_spike",
                severity="warning",
                symbol=tick.symbol,
                message=f"Spread {spread_pts:.1f} points",
                should_halt_entries=spread_pts > self.max_spread_points * 2,
            ))

        prev = self._last_mid.get(tick.symbol)
        mid = tick.mid
        if prev is not None and atr and atr > 0:
            move = abs(mid - prev)
            if move > self.spike_atr_mult * atr:
                events.append(AnomalyEvent(
                    kind="price_spike",
                    severity="critical",
                    symbol=tick.symbol,
                    message=f"Move {move:.5f} > {self.spike_atr_mult}×ATR ({atr:.5f})",
                    should_halt_entries=True,
                ))
        self._last_mid[tick.symbol] = mid
        return events

    def check_candles(self, candles: Sequence[Candle], atr: float | None = None) -> list[AnomalyEvent]:
        events: list[AnomalyEvent] = []
        if len(candles) < 2:
            return events
        a, b = candles[-2], candles[-1]
        # Gap detection
        gap = abs(b.open - a.close)
        if atr and atr > 0 and gap > 3 * atr:
            events.append(AnomalyEvent(
                kind="price_gap",
                severity="warning",
                symbol=b.symbol,
                message=f"Gap {gap:.5f} between candles",
                should_halt_entries=False,
            ))
        # Duplicate / bad OHLC
        if b.high < b.low or b.high < b.open or b.high < b.close:
            events.append(AnomalyEvent(
                kind="bad_candle",
                severity="critical",
                symbol=b.symbol,
                message="Invalid OHLC",
                should_halt_entries=True,
            ))
        return events
