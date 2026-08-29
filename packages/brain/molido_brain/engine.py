"""Decision brain — a real gate, still no LLM.

Turns scored signals + closed-candle features into P(win) and EV.
May only veto or reduce size (size_mult in {1.0, 0.5, 0}). Never enlarges.
Never picks direction via LLM. This is not a profit guarantee.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from molido_brain.features import extract_features
from molido_signals.engine import FinalSignal
from molido_strategies.base import SignalSide


@dataclass
class BrainDecision:
    allow: bool
    p_win: float
    expected_r: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
    size_mult: float = 1.0


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


def _clamp_size(mult: float) -> float:
    if mult <= 0:
        return 0.0
    if mult <= 0.5:
        return 0.5
    return 1.0


class DecisionBrain:
    """Logistic + hard-rule gate in front of RiskEngine.

    Weights are conservative priors, not a fitted edge. Uncertainty only
    tightens the gate. size_mult is never greater than 1.
    """

    def __init__(
        self,
        min_p: float = 0.58,
        min_ev: float = 0.10,
        default_swap_r: float = 0.03,
        pause_on_negative_journal: bool = True,
        max_spread_stop: float = 0.25,
        dead_atr_ratio: float = 0.0003,
        atr_vs_stop_max: float = 1.2,
    ):
        self.min_p = min_p
        self.min_ev = min_ev
        self.default_swap_r = default_swap_r
        self.pause_on_negative_journal = pause_on_negative_journal
        self.max_spread_stop = max_spread_stop
        self.dead_atr_ratio = dead_atr_ratio
        self.atr_vs_stop_max = atr_vs_stop_max

    def decide(
        self,
        signal: FinalSignal,
        indicators: dict | None = None,
        regime: str | None = None,
        agreeing: int = 1,
        **kwargs: Any,
    ) -> BrainDecision:
        """Compatible with pipeline(signal, indicators, regime, agreeing).

        Optional kwargs (all ignored if absent): h1_side, spread, journal_stats,
        swap_r, candles, overlap, now.
        """
        if signal.side == SignalSide.EXIT:
            return BrainDecision(
                allow=True,
                p_win=1.0,
                expected_r=0.0,
                reasons=["exit path"],
                size_mult=1.0,
            )

        indicators = indicators or {}
        h1_side = kwargs.get("h1_side")
        spread = kwargs.get("spread")
        journal_stats = kwargs.get("journal_stats")
        swap_r = kwargs.get("swap_r")
        candles = kwargs.get("candles")
        overlap = kwargs.get("overlap")
        now = kwargs.get("now")

        side = signal.side.value if hasattr(signal.side, "value") else str(signal.side)
        entry = float(signal.entry or 0.0)
        sl = signal.stop_loss
        stop_distance = abs(entry - float(sl)) if sl is not None and entry else None

        feats_raw = extract_features(
            candles,
            side=side,
            stop_distance=stop_distance,
            spread=float(spread) if spread is not None else None,
            h1_side=str(h1_side) if h1_side else None,
            regime=regime or signal.market_regime,
            now=now,
            overlap=overlap,
            indicators=indicators,
        )

        rsi = _val(indicators.get("RSI") or indicators.get("rsi"), "rsi", "value")
        if rsi is None:
            rsi = float(feats_raw.get("rsi") or 50.0)
        ema_fast = _val(indicators.get("MultiEMA") or indicators.get("ema"), "ema_9", "ema9")
        ema_slow = _val(indicators.get("MultiEMA") or indicators.get("ema"), "ema_21", "ema21")
        atr = _val(indicators.get("ATR") or indicators.get("atr14"), "atr")
        if atr is None:
            atr = float(feats_raw.get("atr") or 0.0) or None
        close = entry or float(feats_raw.get("close") or 0.0)

        score_n = _clip((signal.score or 0.0) / 100.0, 0.0, 1.0)
        rr = _clip(float(signal.risk_reward or 1.0), 0.5, 4.0)

        trend = 0.0
        if ema_fast is not None and ema_slow is not None:
            aligned = (ema_fast > ema_slow and side == "BUY") or (
                ema_fast < ema_slow and side == "SELL"
            )
            trend = 1.0 if aligned else -1.0
        elif float(feats_raw.get("ema9_slope") or 0) != 0:
            s9 = float(feats_raw["ema9_slope"])
            aligned = (s9 > 0 and side == "BUY") or (s9 < 0 and side == "SELL")
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

        regime_s = str(regime or signal.market_regime or feats_raw.get("regime") or "Unknown").lower()
        regime_pen = 0.0
        if "unknown" in regime_s:
            regime_pen = -0.8
        elif "high volatility" in regime_s or "extreme" in regime_s:
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
        atr_z = float(feats_raw.get("atr_z") or 0.0)
        last3 = float(feats_raw.get("last3_ret") or 0.0)
        h1_tr = float(feats_raw.get("h1_trend") or 0.0)
        overlap_f = float(feats_raw.get("overlap") or 0.0)
        spread_stop = float(feats_raw.get("spread_stop") or 0.0)

        mom_fit = 0.0
        if side == "BUY":
            mom_fit = _clip(last3 / 0.002, -1.5, 1.5)
        else:
            mom_fit = _clip(-last3 / 0.002, -1.5, 1.5)

        z = (
            -0.70
            + 1.20 * score_n
            + 0.30 * (rr - 1.0)
            + 0.35 * trend
            + 0.20 * rsi_fit
            + 0.15 * mom_fit
            + 0.25 * h1_tr
            + 0.10 * overlap_f
            - 0.20 * abs(atr_z)
            - 0.45 * vol
            + regime_pen
            + 0.15 * agree_n
        )
        p = _sigmoid(z)
        # Prior shrinkage: pull toward 0.45 (no assumed edge).
        p = 0.55 * p + 0.45 * 0.45

        swap = self.default_swap_r if swap_r is None else float(swap_r)
        ev = p * rr - (1.0 - p) * 1.0 - swap

        reasons: list[str] = [
            f"P(win)={p:.2f}",
            f"EV={ev:.2f}R after swap {swap:.3f}R",
            f"regime={regime or signal.market_regime or 'Unknown'}",
            f"h1={h1_side or 'n/a'}",
            f"overlap={bool(overlap_f)}",
            f"atr_z={atr_z:.2f}",
            f"rsi={float(rsi):.1f}" if rsi is not None else "rsi=n/a",
            f"spread/stop={spread_stop:.3f}",
        ]

        allow = True
        size_mult = 1.0
        vetoes: list[str] = []

        if h1_side and str(h1_side).upper() in ("BUY", "SELL"):
            if str(h1_side).upper() != side:
                allow = False
                vetoes.append(f"hard veto: against H1 filter ({h1_side} vs {side})")

        if stop_distance and spread is not None and stop_distance > 0:
            if float(spread) > self.max_spread_stop * stop_distance:
                allow = False
                vetoes.append(
                    f"hard veto: spread {float(spread):.5f} > {self.max_spread_stop:.0%} of stop {stop_distance:.5f}"
                )

        if atr and close:
            if atr / close < self.dead_atr_ratio:
                allow = False
                vetoes.append(
                    f"hard veto: ATR dead ({atr / close:.6f} < {self.dead_atr_ratio})"
                )
        if atr and stop_distance:
            if atr > self.atr_vs_stop_max * stop_distance:
                allow = False
                vetoes.append(
                    f"hard veto: ATR {atr:.5f} > {self.atr_vs_stop_max} x stop {stop_distance:.5f}"
                )

        if "unknown" in regime_s and vol > 1.5:
            allow = False
            vetoes.append("hard veto: unknown regime + high vol")

        mean_r = None
        n_j = 0
        if isinstance(journal_stats, dict):
            try:
                mean_r = float(journal_stats.get("mean_r"))
                n_j = int(journal_stats.get("n") or 0)
            except (TypeError, ValueError):
                mean_r = None
        if mean_r is not None and n_j >= 20 and mean_r < 0:
            reasons.append(f"journal last-{n_j} mean R={mean_r:.3f}")
            if self.pause_on_negative_journal:
                allow = False
                size_mult = 0.0
                vetoes.append(
                    f"hard veto: last-{n_j} journal expectancy {mean_r:.3f}R < 0 (pause new entries)"
                )
            else:
                size_mult = min(size_mult, 0.5)
                reasons.append("journal negative: size_mult=0.5")

        if p < self.min_p:
            allow = False
            vetoes.append(f"brain veto: p {p:.2f} < {self.min_p}")
        if ev < self.min_ev:
            allow = False
            vetoes.append(f"brain veto: EV {ev:.2f}R < {self.min_ev}")

        reasons.extend(vetoes)

        if not allow:
            size_mult = 0.0
        elif size_mult >= 1.0 and (p < self.min_p + 0.04 or ev < self.min_ev + 0.05 or vol > 1.2):
            size_mult = 0.5
            reasons.append("size_mult=0.5 (marginal p/EV or elevated vol)")

        size_mult = _clamp_size(size_mult)
        if size_mult > 1.0:
            size_mult = 1.0
        if size_mult == 0.0:
            allow = False

        numeric = {
            k: float(v)
            for k, v in feats_raw.items()
            if isinstance(v, (int, float))
        }
        numeric.update(
            {
                "score_n": score_n,
                "rr": rr,
                "trend": trend,
                "rsi_fit": rsi_fit,
                "vol": vol,
                "agree": agree_n,
                "swap_r": swap,
                "size_mult": size_mult,
            }
        )

        return BrainDecision(
            allow=allow,
            p_win=round(p, 4),
            expected_r=round(ev, 4),
            reasons=reasons,
            features=numeric,
            size_mult=size_mult,
        )

    def rank_universe(self, rows: list) -> list:
        """Rank cheap-scored symbols. Does not pick BUY/SELL via LLM."""
        return sorted(rows, key=lambda r: float(getattr(r, "score", 0.0)), reverse=True)
