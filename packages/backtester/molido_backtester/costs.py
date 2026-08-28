"""Slippage / commission / spread cost model (Master Prompt §27.1.23)."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CostModel:
    spread_points: float = 1.2          # average spread in points
    slippage_points: float = 0.5        # extra slippage on market orders
    commission_per_lot: float = 7.0     # round-turn $ per lot (typical ECN)
    point_size: float = 0.0001          # for standard FX; override per symbol

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

    def for_symbol(self, symbol: str) -> "CostModel":
        point = 0.01 if ("JPY" in symbol or symbol.startswith("XAU")) else 0.0001
        spread = 25.0 if symbol.startswith("XAU") else self.spread_points
        return CostModel(
            spread_points=spread,
            slippage_points=self.slippage_points,
            commission_per_lot=self.commission_per_lot,
            point_size=point,
        )
