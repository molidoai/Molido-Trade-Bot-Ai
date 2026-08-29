"""Three numeric brains in series. No LLM. None of them pick BUY/SELL.

Brain1 Setup — H1 alignment + session/universe/spread quality. Pass (1) or veto (0).
Brain2 Edge  — P(win)/EV with spread+swap. size_mult in {1, 0.5, 0}; never enlarges.
Brain3 Survival — journal mean R, correlation, daily loss, ATR dead/wild. Cut or veto.

DecisionBrain runs 1 → 2 → 3. Final size_mult is the min of all three.
Full size only when every brain passes at 1.0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from molido_brain.features import extract_features
from molido_brain.swap import overnight_swap_r, veto_weekend_hold

try:
    from molido_guards.correlation import correlated_block
except ImportError:  # pragma: no cover
    def correlated_block(symbol: str, open_symbols: list[str] | None) -> tuple[bool, str]:
        return True, "no correlation helper"


def clamp_size(mult: float) -> float:
    """Only {0, 0.5, 1}. Never enlarges past 1."""
    if mult <= 0:
        return 0.0
    if mult <= 0.5:
        return 0.5
    return 1.0


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sigmoid(z: float) -> float:
    z = clip(z, -12.0, 12.0)
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


@dataclass
class BrainVote:
    name: str
    allow: bool
    size_mult: float
    reasons: list[str] = field(default_factory=list)
    p_win: float | None = None
    expected_r: float | None = None


@dataclass
class FeatureSnap:
    side: str
    entry: float
    stop_distance: float | None
    rsi: float | None
    atr: float | None
    close: float
    score_n: float
    rr: float
    trend: float
    rsi_fit: float
    vol: float
    regime_s: str
    regime_pen: float
    agree_n: float
    atr_z: float
    last3: float
    h1_tr: float
    overlap_f: float
    spread_stop: float
    mom_fit: float
    feats_raw: dict[str, Any]
    swap: float


def snapshot_features(
    signal: Any,
    *,
    indicators: dict | None = None,
    regime: str | None = None,
    agreeing: int = 1,
    h1_side: str | None = None,
    spread: float | None = None,
    swap_r: float | None = None,
    candles: Any = None,
    overlap: bool | None = None,
    now: Any = None,
    default_swap_r: float = 0.03,
) -> FeatureSnap:
    indicators = indicators or {}
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
        regime=regime or getattr(signal, "market_regime", None),
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

    score_n = clip((getattr(signal, "score", 0.0) or 0.0) / 100.0, 0.0, 1.0)
    rr = clip(float(getattr(signal, "risk_reward", None) or 1.0), 0.5, 4.0)

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
            rsi_fit = clip((50.0 - rsi) / 20.0, -1.5, 1.5)
        else:
            rsi_fit = clip((rsi - 50.0) / 20.0, -1.5, 1.5)

    vol = 0.0
    if atr and close:
        vol = clip((atr / close) / 0.004, 0.0, 3.0)

    regime_s = str(regime or getattr(signal, "market_regime", None) or feats_raw.get("regime") or "Unknown").lower()
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

    agree_n = clip((agreeing - 1) / 2.0, 0.0, 1.0)
    atr_z = float(feats_raw.get("atr_z") or 0.0)
    last3 = float(feats_raw.get("last3_ret") or 0.0)
    h1_tr = float(feats_raw.get("h1_trend") or 0.0)
    overlap_f = float(feats_raw.get("overlap") or 0.0)
    spread_stop = float(feats_raw.get("spread_stop") or 0.0)

    if side == "BUY":
        mom_fit = clip(last3 / 0.002, -1.5, 1.5)
    else:
        mom_fit = clip(-last3 / 0.002, -1.5, 1.5)

    symbol = getattr(signal, "symbol", None)
    if swap_r is None:
        swap = overnight_swap_r(symbol=symbol, side=side, now=now, base=default_swap_r)
    else:
        swap = overnight_swap_r(
            symbol=symbol, side=side, now=now, quoted=float(swap_r), base=default_swap_r
        )

    return FeatureSnap(
        side=side,
        entry=entry,
        stop_distance=stop_distance,
        rsi=rsi,
        atr=atr,
        close=close,
        score_n=score_n,
        rr=rr,
        trend=trend,
        rsi_fit=rsi_fit,
        vol=vol,
        regime_s=regime_s,
        regime_pen=regime_pen,
        agree_n=agree_n,
        atr_z=atr_z,
        last3=last3,
        h1_tr=h1_tr,
        overlap_f=overlap_f,
        spread_stop=spread_stop,
        mom_fit=mom_fit,
        feats_raw=feats_raw,
        swap=swap,
    )


class Brain1Setup:
    """H1 alignment + universe/session/spread quality. Veto or size_mult 0. Never 0.5."""

    def __init__(self, max_spread_stop: float = 0.25):
        self.max_spread_stop = max_spread_stop

    def vote(
        self,
        snap: FeatureSnap,
        *,
        h1_side: str | None = None,
        spread: float | None = None,
        session_ok: bool = True,
        universe_score: float | None = None,
    ) -> BrainVote:
        reasons: list[str] = ["brain1=setup"]
        if not session_ok:
            return BrainVote("setup", False, 0.0, reasons + ["setup veto: session closed"])
        if universe_score is not None and float(universe_score) <= 0:
            return BrainVote(
                "setup", False, 0.0,
                reasons + [f"setup veto: universe score {universe_score:.2f} <= 0"],
            )
        if h1_side and str(h1_side).upper() in ("BUY", "SELL"):
            if str(h1_side).upper() != snap.side:
                return BrainVote(
                    "setup", False, 0.0,
                    reasons + [f"hard veto: against H1 filter ({h1_side} vs {snap.side})"],
                )
            reasons.append(f"h1 aligned {h1_side}")
        if snap.stop_distance and spread is not None and snap.stop_distance > 0:
            if float(spread) > self.max_spread_stop * snap.stop_distance:
                return BrainVote(
                    "setup", False, 0.0,
                    reasons + [
                        f"hard veto: spread {float(spread):.5f} > {self.max_spread_stop:.0%} of stop {snap.stop_distance:.5f}"
                    ],
                )
        reasons.append(f"spread/stop={snap.spread_stop:.3f}")
        return BrainVote("setup", True, 1.0, reasons)


class Brain2Edge:
    """P(win)/EV including spread+swap. size_mult in {1, 0.5, 0}. Never enlarges."""

    def __init__(self, min_p: float = 0.58, min_ev: float = 0.10):
        self.min_p = min_p
        self.min_ev = min_ev

    def vote(self, snap: FeatureSnap, *, now: Any = None) -> BrainVote:
        z = (
            -0.70
            + 1.20 * snap.score_n
            + 0.30 * (snap.rr - 1.0)
            + 0.35 * snap.trend
            + 0.20 * snap.rsi_fit
            + 0.15 * snap.mom_fit
            + 0.25 * snap.h1_tr
            + 0.10 * snap.overlap_f
            - 0.20 * abs(snap.atr_z)
            - 0.45 * snap.vol
            + snap.regime_pen
            + 0.15 * snap.agree_n
        )
        p = sigmoid(z)
        p = 0.55 * p + 0.45 * 0.45
        ev = p * snap.rr - (1.0 - p) * 1.0 - snap.swap
        reasons = [
            "brain2=edge",
            f"P(win)={p:.2f}",
            f"EV={ev:.2f}R after swap {snap.swap:.3f}R",
            f"rsi={float(snap.rsi):.1f}" if snap.rsi is not None else "rsi=n/a",
        ]
        hold_veto, hold_why = veto_weekend_hold(snap.swap, now)
        if hold_veto:
            return BrainVote("edge", False, 0.0, reasons + [hold_why], p_win=p, expected_r=ev)
        if p < self.min_p:
            return BrainVote(
                "edge", False, 0.0,
                reasons + [f"brain veto: p {p:.2f} < {self.min_p}"],
                p_win=p, expected_r=ev,
            )
        if ev < self.min_ev:
            return BrainVote(
                "edge", False, 0.0,
                reasons + [f"brain veto: EV {ev:.2f}R < {self.min_ev}"],
                p_win=p, expected_r=ev,
            )
        size = 1.0
        if p < self.min_p + 0.04 or ev < self.min_ev + 0.05 or snap.vol > 1.2:
            size = 0.5
            reasons.append("size_mult=0.5 (marginal p/EV or elevated vol)")
        return BrainVote("edge", True, clamp_size(size), reasons, p_win=p, expected_r=ev)


class Brain3Survival:
    """Journal mean R, correlation, daily loss, ATR dead/wild. Cut size or veto only."""

    def __init__(
        self,
        pause_on_negative_journal: bool = True,
        dead_atr_ratio: float = 0.0003,
        atr_vs_stop_max: float = 1.2,
        daily_loss_limit: float = 0.02,
    ):
        self.pause_on_negative_journal = pause_on_negative_journal
        self.dead_atr_ratio = dead_atr_ratio
        self.atr_vs_stop_max = atr_vs_stop_max
        self.daily_loss_limit = daily_loss_limit

    def vote(
        self,
        snap: FeatureSnap,
        *,
        journal_stats: dict | None = None,
        open_symbols: list[str] | None = None,
        symbol: str | None = None,
        daily_pnl: float | None = None,
        equity: float | None = None,
        daily_loss_limit: float | None = None,
    ) -> BrainVote:
        reasons = ["brain3=survival"]
        size = 1.0
        limit = float(daily_loss_limit if daily_loss_limit is not None else self.daily_loss_limit)

        if snap.atr and snap.close:
            if snap.atr / snap.close < self.dead_atr_ratio:
                return BrainVote(
                    "survival", False, 0.0,
                    reasons + [f"hard veto: ATR dead ({snap.atr / snap.close:.6f} < {self.dead_atr_ratio})"],
                )
        if snap.atr and snap.stop_distance:
            if snap.atr > self.atr_vs_stop_max * snap.stop_distance:
                return BrainVote(
                    "survival", False, 0.0,
                    reasons + [
                        f"hard veto: ATR {snap.atr:.5f} > {self.atr_vs_stop_max} x stop {snap.stop_distance:.5f}"
                    ],
                )
        if "unknown" in snap.regime_s and snap.vol > 1.5:
            return BrainVote("survival", False, 0.0, reasons + ["hard veto: unknown regime + high vol"])

        if symbol:
            ok_c, why_c = correlated_block(symbol, open_symbols or [])
            if not ok_c:
                return BrainVote("survival", False, 0.0, reasons + [f"survival veto: {why_c}"])

        if equity and equity > 0 and daily_pnl is not None:
            loss_frac = max(0.0, -float(daily_pnl) / float(equity))
            if loss_frac >= limit:
                return BrainVote(
                    "survival", False, 0.0,
                    reasons + [f"survival veto: daily loss {loss_frac:.2%} >= {limit:.2%}"],
                )
            if loss_frac >= limit * 0.5:
                size = min(size, 0.5)
                reasons.append(f"daily loss {loss_frac:.2%} — size_mult=0.5")

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
                return BrainVote(
                    "survival", False, 0.0,
                    reasons + [
                        f"hard veto: last-{n_j} journal expectancy {mean_r:.3f}R < 0 (pause new entries)"
                    ],
                )
            size = min(size, 0.5)
            reasons.append("journal negative: size_mult=0.5")

        reasons.append(f"atr_z={snap.atr_z:.2f}")
        return BrainVote("survival", True, clamp_size(size), reasons)
