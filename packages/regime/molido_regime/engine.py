"""Simple Market Regime classifier (Master Prompt §7)."""

from __future__ import annotations
from typing import Sequence
from molido_shared.types import Candle
from molido_indicators.base import IndicatorResult


REGIMES = [
    "Strong Bull", "Bull", "Sideways", "Bear", "Strong Bear",
    "High Volatility", "Low Volatility", "Unknown",
]


class MarketRegimeEngine:
    def classify(
        self,
        candles: Sequence[Candle],
        indicators: dict[str, IndicatorResult] | None = None,
    ) -> str:
        if not candles or len(candles) < 30:
            return "Unknown"

        indicators = indicators or {}
        closes = [c.close for c in candles[-50:]]
        ret = (closes[-1] - closes[0]) / closes[0] if closes[0] else 0

        atr = None
        atr_res = indicators.get("ATR") or indicators.get("atr14")
        if atr_res:
            atr = atr_res.get("atr")
        multi = indicators.get("MultiEMA") or indicators.get("ema")
        ema_fast = multi.get("ema_9") if multi else None
        ema_slow = multi.get("ema_21") if multi else None

        # Volatility
        if atr and closes[-1]:
            atr_pct = atr / closes[-1]
            if atr_pct > 0.005:
                return "High Volatility"
            if atr_pct < 0.0008:
                vol_tag = "Low Volatility"
            else:
                vol_tag = None
        else:
            vol_tag = None

        if ema_fast is not None and ema_slow is not None:
            if ema_fast > ema_slow and ret > 0.01:
                return "Strong Bull"
            if ema_fast > ema_slow:
                return "Bull"
            if ema_fast < ema_slow and ret < -0.01:
                return "Strong Bear"
            if ema_fast < ema_slow:
                return "Bear"

        if abs(ret) < 0.003:
            return vol_tag or "Sideways"
        return vol_tag or "Unknown"
