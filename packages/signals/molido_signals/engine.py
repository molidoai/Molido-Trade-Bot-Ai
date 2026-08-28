"""
Signal Engine (Master Prompt §9).

- Normalizes strategy outputs into a final scored signal
- Applies configurable acceptance threshold
- Never bypasses Risk Engine (score is advisory only for risk layer)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from molido_indicators.base import IndicatorResult
from molido_strategies.base import StrategySignal, SignalSide
from molido_signals.scoring import (
    ScoreBreakdown,
    ScoringWeights,
    compute_breakdown,
)


@dataclass
class FinalSignal:
    """
    Fully scored, threshold-filtered signal ready for Risk Engine.
    """
    symbol: str
    side: SignalSide
    timeframe: str
    strategy: str
    timestamp: datetime
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence: float = 0.0
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    market_regime: str | None = None
    risk_reward: float | None = None
    accepted: bool = False          # True only if score >= threshold
    reject_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def is_actionable(self) -> bool:
        return self.accepted and self.side in (SignalSide.BUY, SignalSide.SELL, SignalSide.EXIT)


class SignalEngine:
    def __init__(
        self,
        accept_threshold: float = 60.0,
        weights: ScoringWeights | None = None,
        require_sl: bool = True,
        min_rr: float = 1.0,
    ):
        """
        accept_threshold: minimum composite score (0–100) to accept a signal.
        require_sl: reject BUY/SELL without stop-loss.
        min_rr: minimum risk/reward ratio.
        """
        self.accept_threshold = accept_threshold
        self.weights = weights or ScoringWeights()
        self.require_sl = require_sl
        self.min_rr = min_rr

    def process(
        self,
        raw_signals: Sequence[StrategySignal],
        indicators: dict[str, IndicatorResult] | None = None,
        mtf_factor: float = 0.5,
        volume_factor: float = 0.5,
        pick_best: bool = True,
    ) -> list[FinalSignal]:
        """
        Score all raw strategy signals and optionally keep only the best accepted one.
        """
        indicators = indicators or {}
        finals: list[FinalSignal] = []

        for raw in raw_signals:
            final = self._score_one(raw, indicators, mtf_factor, volume_factor)
            finals.append(final)

        if pick_best:
            accepted = [f for f in finals if f.accepted]
            if not accepted:
                # Return the highest-scored rejected signal for transparency (NO_TRADE path)
                if finals:
                    best = max(finals, key=lambda x: x.score)
                    return [best]
                return []
            best = max(accepted, key=lambda x: x.score)
            return [best]

        return finals

    def _score_one(
        self,
        raw: StrategySignal,
        indicators: dict[str, IndicatorResult],
        mtf_factor: float,
        volume_factor: float,
    ) -> FinalSignal:
        # EXIT / HOLD / NO_TRADE pass through with limited scoring
        if raw.side == SignalSide.NO_TRADE:
            return FinalSignal(
                symbol=raw.symbol,
                side=raw.side,
                timeframe=raw.timeframe.value if hasattr(raw.timeframe, "value") else str(raw.timeframe),
                strategy=raw.strategy_name,
                timestamp=raw.timestamp,
                reasons=raw.reasons,
                market_regime=raw.market_regime,
                accepted=False,
                reject_reason=raw.reasons[0] if raw.reasons else "NO_TRADE",
                score=0.0,
            )

        if raw.side == SignalSide.HOLD:
            return FinalSignal(
                symbol=raw.symbol,
                side=raw.side,
                timeframe=raw.timeframe.value if hasattr(raw.timeframe, "value") else str(raw.timeframe),
                strategy=raw.strategy_name,
                timestamp=raw.timestamp,
                reasons=raw.reasons,
                market_regime=raw.market_regime,
                accepted=False,
                reject_reason="HOLD",
                score=0.0,
            )

        if raw.side == SignalSide.EXIT:
            # Exits are always accepted if strategy requested them (risk layer still decides)
            return FinalSignal(
                symbol=raw.symbol,
                side=raw.side,
                timeframe=raw.timeframe.value if hasattr(raw.timeframe, "value") else str(raw.timeframe),
                strategy=raw.strategy_name,
                timestamp=raw.timestamp,
                entry=raw.entry,
                confidence=raw.confidence,
                score=raw.confidence,
                reasons=raw.reasons,
                market_regime=raw.regime if hasattr(raw, "regime") else raw.market_regime,
                accepted=True,
            )

        # BUY / SELL – full scoring
        breakdown = compute_breakdown(
            raw, indicators, self.weights, mtf_factor, volume_factor
        )
        total = breakdown.total

        reasons = list(raw.reasons)
        reasons.append(f"Composite score {total:.1f}/100")

        reject: str | None = None
        accepted = True

        if total < self.accept_threshold:
            accepted = False
            reject = f"Score {total:.1f} < threshold {self.accept_threshold}"

        if self.require_sl and raw.stop_loss is None:
            accepted = False
            reject = "Missing mandatory Stop-Loss"

        if raw.risk_reward is not None and raw.risk_reward < self.min_rr:
            accepted = False
            reject = f"R:R {raw.risk_reward} < minimum {self.min_rr}"

        return FinalSignal(
            symbol=raw.symbol,
            side=raw.side,
            timeframe=raw.timeframe.value if hasattr(raw.timeframe, "value") else str(raw.timeframe),
            strategy=raw.strategy_name,
            timestamp=raw.timestamp or datetime.now(timezone.utc),
            entry=raw.entry,
            stop_loss=raw.stop_loss,
            take_profit=raw.take_profit,
            confidence=raw.confidence,
            score=round(total, 2),
            score_breakdown=breakdown.as_dict(),
            reasons=reasons,
            market_regime=raw.market_regime,
            risk_reward=raw.risk_reward,
            accepted=accepted,
            reject_reason=reject,
            meta={"raw_confidence": raw.confidence},
        )

    def update_threshold(self, new_threshold: float) -> None:
        """Adaptive threshold can call this – changes must be versioned/audited externally."""
        self.accept_threshold = max(0.0, min(100.0, new_threshold))
