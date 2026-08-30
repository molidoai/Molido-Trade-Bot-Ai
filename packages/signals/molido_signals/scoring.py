"""
Signal Scoring components (Master Prompt §9).

Weights (configurable, sum ≈ 100):
  Trend 20 | Momentum 15 | Volume 15 | Structure 15
  MTF 15   | Volatility 10 | Strategy 10
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from molido_indicators.base import IndicatorResult
from molido_strategies.base import StrategySignal, SignalSide


@dataclass
class ScoreBreakdown:
    trend: float = 0.0
    momentum: float = 0.0
    volume: float = 0.0
    structure: float = 0.0
    mtf: float = 0.0
    volatility: float = 0.0
    strategy: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.trend + self.momentum + self.volume + self.structure
            + self.mtf + self.volatility + self.strategy
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "trend": round(self.trend, 2),
            "momentum": round(self.momentum, 2),
            "volume": round(self.volume, 2),
            "structure": round(self.structure, 2),
            "mtf": round(self.mtf, 2),
            "volatility": round(self.volatility, 2),
            "strategy": round(self.strategy, 2),
            "total": round(self.total, 2),
        }


@dataclass
class ScoringWeights:
    trend: float = 20.0
    momentum: float = 15.0
    volume: float = 15.0
    structure: float = 15.0
    mtf: float = 15.0
    volatility: float = 10.0
    strategy: float = 10.0

    def normalized(self) -> "ScoringWeights":
        s = self.trend + self.momentum + self.volume + self.structure + self.mtf + self.volatility + self.strategy
        if s <= 0:
            return self
        return ScoringWeights(
            trend=self.trend / s * 100,
            momentum=self.momentum / s * 100,
            volume=self.volume / s * 100,
            structure=self.structure / s * 100,
            mtf=self.mtf / s * 100,
            volatility=self.volatility / s * 100,
            strategy=self.strategy / s * 100,
        )


def score_trend(indicators: dict[str, IndicatorResult], side: SignalSide) -> float:
    """0–1 factor based on EMA alignment / Supertrend."""
    multi = indicators.get("MultiEMA") or indicators.get("ema")
    st = indicators.get("Supertrend") or indicators.get("supertrend")
    score = 0.5  # neutral

    if multi:
        e9 = multi.get("ema_9")
        e21 = multi.get("ema_21")
        e50 = multi.get("ema_50")
        if e9 is not None and e21 is not None:
            if side == SignalSide.BUY and e9 > e21:
                score += 0.25
            elif side == SignalSide.SELL and e9 < e21:
                score += 0.25
        if e21 is not None and e50 is not None:
            if side == SignalSide.BUY and e21 > e50:
                score += 0.15
            elif side == SignalSide.SELL and e21 < e50:
                score += 0.15

    if st:
        direction = st.get("direction")
        if direction is not None:
            if side == SignalSide.BUY and direction > 0:
                score += 0.2
            elif side == SignalSide.SELL and direction < 0:
                score += 0.2

    return max(0.0, min(1.0, score))


def score_momentum(indicators: dict[str, IndicatorResult], side: SignalSide) -> float:
    rsi = (indicators.get("RSI") or indicators.get("rsi14") or IndicatorResult()).get("rsi")
    macd = indicators.get("MACD") or indicators.get("macd")
    score = 0.5

    if rsi is not None:
        if side == SignalSide.BUY:
            if 40 <= rsi <= 65:
                score += 0.3
            elif rsi < 30:
                score += 0.15  # oversold bounce possible
            elif rsi > 75:
                score -= 0.2
        elif side == SignalSide.SELL:
            if 35 <= rsi <= 60:
                score += 0.3
            elif rsi > 70:
                score += 0.15
            elif rsi < 25:
                score -= 0.2

    if macd:
        hist = macd.get("histogram")
        if hist is not None:
            if side == SignalSide.BUY and hist > 0:
                score += 0.2
            elif side == SignalSide.SELL and hist < 0:
                score += 0.2

    return max(0.0, min(1.0, score))


def score_volatility(indicators: dict[str, IndicatorResult]) -> float:
    """Prefer moderate volatility – extreme vol reduces score."""
    atr = (indicators.get("ATR") or indicators.get("atr14") or IndicatorResult()).get("atr")
    bb = indicators.get("BollingerBands") or indicators.get("bb")
    score = 0.7  # default ok

    if bb:
        width = bb.get("width")
        if width is not None:
            if width < 0.001:      # very tight – low opportunity
                score = 0.4
            elif width > 0.02:      # extremely wide
                score = 0.35
            else:
                score = 0.85
    return score


def score_structure(indicators: dict[str, IndicatorResult], side: SignalSide) -> float:
    swings = indicators.get("SwingPoints") or indicators.get("swings")
    don = indicators.get("DonchianChannel") or indicators.get("donchian")
    score = 0.5

    if don:
        # Being near channel edge supports breakout direction
        score += 0.2

    if swings:
        if side == SignalSide.BUY and swings.get("is_swing_low"):
            score += 0.25
        if side == SignalSide.SELL and swings.get("is_swing_high"):
            score += 0.25

    return max(0.0, min(1.0, score))


def score_strategy_quality(raw: StrategySignal) -> float:
    """Map strategy's own confidence (0–100) to 0–1."""
    return max(0.0, min(1.0, raw.confidence / 100.0))


def compute_breakdown(
    raw: StrategySignal,
    indicators: dict[str, IndicatorResult],
    weights: ScoringWeights | None = None,
    mtf_factor: float = 0.5,   # 0–1 from multi-timeframe engine (placeholder)
    volume_factor: float = 0.5, # 0–1 when volume data available
) -> ScoreBreakdown:
    w = (weights or ScoringWeights()).normalized()
    side = raw.side

    if side not in (SignalSide.BUY, SignalSide.SELL):
        return ScoreBreakdown()  # no score for HOLD / NO_TRADE / EXIT in this model

    t = score_trend(indicators, side)
    m = score_momentum(indicators, side)
    v = volume_factor
    s = score_structure(indicators, side)
    mtf = mtf_factor
    vol = score_volatility(indicators)
    st = score_strategy_quality(raw)

    return ScoreBreakdown(
        trend=t * w.trend,
        momentum=m * w.momentum,
        volume=v * w.volume,
        structure=s * w.structure,
        mtf=mtf * w.mtf,
        volatility=vol * w.volatility,
        strategy=st * w.strategy,
    )
