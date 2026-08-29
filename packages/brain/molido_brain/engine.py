"""Decision brain.

Turns scored signals + indicators + regime into a calibrated P(win) and EV.
Uncertainty only tightens the gate. It never makes the bot more aggressive.
This is not a profit guarantee.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any

from molido_signals.engine import FinalSignal
from molido_strategies.base import SignalSide


@dataclass
class BrainDecision:
    allow: bool
    p_win: float
    expected_r: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sigmoid(z: float) -> float:
    z = _clip(z, -12.0, 12.0)
    return 1.0 / (1.0 + math.exp(-z))


def _val(ind: Any, *keys: str) -> float | None:
    if ind is None:
        return None
    getter = getattr(ind, "get", None)
    if callable(getter):
        for key in keys:
            v = getter(key)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    if isinstance(ind, dict):
        for key in keys:
            v = ind.get(key)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    return None


class DecisionBrain:
    """Logistic gate in front of RiskEngine.

    Weights are conservative priors, not a fitted edge. Until a journal of
    resolved trades exists, P(win) is a *discounted* score, not a forecast.
    """

    def __init__(self, min_p: float = 0.55, min_ev: float = 0.05):
        self.min_p = min_p
        self.min_ev = min_ev

    def decide(
        self,
        signal: FinalSignal,
        indicators: dict | None = None,
        regime: str | None = None,
        agreeing: int = 1,
    ) -> BrainDecision:
        if signal.side == SignalSide.EXIT:
            return BrainDecision(allow=True, p_win=1.0, expected_r=0.0, reasons=["exit path"])

        indicators = indicators or {}
        rsi = _val(indicators.get("RSI") or indicators.get("rsi"), "rsi", "value")
        ema_fast = _val(indicators.get("MultiEMA") or indicators.get("ema"), "ema_9", "ema9")
        ema_slow = _val(indicators.get("MultiEMA") or indicators.get("ema"), "ema_21", "ema21")
        atr = _val(indicators.get("ATR") or indicators.get("atr14"), "atr")
        close = signal.entry

        score_n = _clip((signal.score or 0.0) / 100.0, 0.0, 1.0)
        rr = _clip(float(signal.risk_reward or 1.0), 0.5, 4.0)
        side = signal.side.value if hasattr(signal.side, "value") else str(signal.side)

        trend = 0.0
        if ema_fast is not None and ema_slow is not None:
            aligned = (ema_fast > ema_slow and side == "BUY") or (ema_fast < ema_slow and side == "SELL")
            trend = 1.0 if aligned else -1.0

        rsi_fit = 0.0
        if rsi is not None:
            if side == "BUY":
                rsi_fit = _clip((50.0 - rsi) / 20.0, -1.5, 1.5)
            else:
                rsi_fit = _clip((rsi - 50.0) / 20.0, -1.5, 1.5)

        vol = 0.0
        if atr and close:
            vol = _clip((atr / close) / 0.004, 0.0, 3.0)

        regime_s = (regime or signal.market_regime or "Unknown").lower()
        regime_pen = 0.0
        if "unknown" in regime_s:
            regime_pen = -0.8
        elif "high volatility" in regime_s:
            regime_pen = -0.6
        elif side == "BUY" and "bear" in regime_s:
            regime_pen = -1.1
        elif side == "SELL" and "bull" in regime_s:
            regime_pen = -1.1
        elif side == "BUY" and "bull" in regime_s:
            regime_pen = 0.35
        elif side == "SELL" and "bear" in regime_s:
            regime_pen = 0.35

        agree_n = _clip((agreeing - 1) / 2.0, 0.0, 1.0)

        # Intercept is deliberately below 0 so a mediocre score does not pass.
        z = (
            -0.55
            + 1.40 * score_n
            + 0.35 * (rr - 1.0)
            + 0.40 * trend
            + 0.25 * rsi_fit
            - 0.45 * vol
            + regime_pen
            + 0.20 * agree_n
        )
        p = _sigmoid(z)
        # Prior shrinkage: no live journal yet, so pull toward 0.45 (no edge).
        p = 0.55 * p + 0.45 * 0.45
        ev = p * rr - (1.0 - p) * 1.0

        reasons: list[str] = [
            f"P(win)={p:.2f}",
            f"EV={ev:.2f}R",
            f"regime={regime or signal.market_regime or 'Unknown'}",
        ]
        allow = True
        if p < self.min_p:
            allow = False
            reasons.append(f"brain veto: p {p:.2f} < {self.min_p}")
        if ev < self.min_ev:
            allow = False
            reasons.append(f"brain veto: EV {ev:.2f}R < {self.min_ev}")
        if "unknown" in regime_s and vol > 1.5:
            allow = False
            reasons.append("brain veto: unknown regime + high vol")

        return BrainDecision(
            allow=allow,
            p_win=round(p, 4),
            expected_r=round(ev, 4),
            reasons=reasons,
            features={
                "score_n": score_n,
                "rr": rr,
                "trend": trend,
                "rsi_fit": rsi_fit,
                "vol": vol,
                "agree": agree_n,
            },
        )
