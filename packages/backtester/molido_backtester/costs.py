"""Spread / slippage / commission / overnight-financing cost model.

Swap was missing entirely, and it is not a rounding error for anything held
overnight. The one validated edge -- TrendFollowing on XAUUSD H1 -- holds
positions for tens of hours, so it crosses one or two rollovers per trade, and
the broker charges for each. Measured on the live terminals: MetaQuotes-Demo
charges 12.6 points a night to hold XAUUSD long, RoboForex-ECN charges 60.
Against a modelled spread of 25 points paid once, a two-night hold at 60 points
a night is four times the cost the model was counting.

Every profit factor produced before this was therefore optimistic, and most
optimistic exactly for the strategies that hold longest.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CostModel:
    spread_points: float = 1.2          # average spread in points
    slippage_points: float = 0.5        # extra slippage on market orders
    commission_per_lot: float = 7.0     # round-turn $ per lot (typical ECN)
    point_size: float = 0.0001          # for standard FX; override per symbol
    # Overnight financing, in points per night per lot, signed as the terminal
    # reports it: negative is charged to you, positive is paid to you. Read
    # from symbol_info().swap_long / swap_short with swap_mode POINTS.
    swap_long_points: float = 0.0
    swap_short_points: float = 0.0
    # Wednesday carries the weekend, so brokers trip the charge. MT5 exposes
    # this as swap_rollover3days; 2 = Wednesday (Mon=0).
    swap_3day_weekday: int = 2
    contract_size: float = 100_000.0

    def entry_cost_price(self, side: str, mid: float) -> float:
        """Effective fill price including half-spread + slippage."""
        half = (self.spread_points + self.slippage_points) * self.point_size / 2
        if side.upper() == "BUY":
            return mid + half
        return mid - half

    def exit_cost_price(self, side: str, mid: float) -> float:
        """Close: pay the other side of spread."""
        half = (self.spread_points + self.slippage_points) * self.point_size / 2
        # Closing a BUY means selling → bid
        if side.upper() == "BUY":
            return mid - half
        return mid + half

    def commission(self, volume: float) -> float:
        return abs(volume) * self.commission_per_lot

    def nights_held(self, entry: datetime, exit: datetime) -> int:
        """Rollovers crossed, counting the triple-charge day three times.

        Counts date boundaries rather than dividing elapsed hours: a position
        opened at 23:00 and closed at 01:00 is charged one night even though it
        lived two hours, which is how the broker actually bills it.
        """
        if entry is None or exit is None:
            return 0
        days = (exit.date() - entry.date()).days
        if days <= 0:
            return 0
        nights = 0
        for i in range(days):
            d = entry.date() + __import__("datetime").timedelta(days=i)
            nights += 3 if d.weekday() == self.swap_3day_weekday else 1
        return nights

    def swap_cost(self, side: str, volume: float, entry: datetime, exit: datetime) -> float:
        """Financing for the whole hold, as a positive cost in account currency.

        A negative return is possible and correct: a short on a symbol with a
        positive short swap is paid to stay open, and pretending otherwise
        would understate exactly the strategies this broker suits.
        """
        nights = self.nights_held(entry, exit)
        if not nights:
            return 0.0
        pts = self.swap_long_points if side.upper() == "BUY" else self.swap_short_points
        # points -> price -> account currency
        return -(pts * self.point_size * self.contract_size * abs(volume) * nights)

    def for_symbol(self, symbol: str) -> "CostModel":
        point = 0.01 if ("JPY" in symbol or symbol.startswith("XAU")) else 0.0001
        spread = 25.0 if symbol.startswith("XAU") else self.spread_points
        return CostModel(
            spread_points=spread,
            slippage_points=self.slippage_points,
            commission_per_lot=self.commission_per_lot,
            point_size=point,
            swap_long_points=self.swap_long_points,
            swap_short_points=self.swap_short_points,
            swap_3day_weekday=self.swap_3day_weekday,
            # Metals are quoted per 100 units, not the FX 100,000.
            contract_size=100.0 if symbol.startswith("XAU") else self.contract_size,
        )
