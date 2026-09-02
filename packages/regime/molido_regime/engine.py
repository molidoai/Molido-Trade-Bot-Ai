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
    # Efficiency ratio below this counts as chop. 0.20 means price walked at
    # least five times the distance it actually covered. Deliberately not
    # tuned against returns: it is a description of the market, and fitting it
    # to a P&L curve is how a regime filter becomes another overfit parameter.
    chop_threshold: float = 0.20

    def __init__(self, chop_threshold: float | None = None):
        if chop_threshold is not None:
            self.chop_threshold = chop_threshold

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

        # Is the market actually going anywhere? The efficiency ratio -- net
        # displacement divided by the total path walked to get there -- is
        # near 1 for a clean trend and near 0 for chop, and it says nothing
        # about direction, so it is genuine information rather than a restated
        # EMA cross.
        #
        # This matters because the two lines below used to decide everything:
        # `if ema_fast > ema_slow: return "Bull"` catches every bar that
        # reaches it, since the EMAs are always ordered one way or the other.
        # Measured over 980 classified bars of EURUSD H1, the engine returned
        # Bull or Bear on 100% of them; Sideways and Low Volatility were
        # reached exactly zero times. There was no state in which the bot
        # declined to trade, and RSIMeanReversion -- which is allowed only in
        # Sideways and Low Volatility -- could never trade at all.
        path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        net = abs(closes[-1] - closes[0])
        efficiency = (net / path) if path else 0.0

        if efficiency < self.chop_threshold:
            # Going nowhere: a cross here is noise, whatever the EMAs say.
            return vol_tag or "Sideways"

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
