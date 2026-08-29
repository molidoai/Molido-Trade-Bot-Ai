"""Candle quality gate. Never invent a missing price; refuse to trade on junk."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Sequence

from molido_shared.types import Candle


@dataclass
class QualityReport:
    score: float
    tradeable: bool
    findings: list[str] = field(default_factory=list)


def score_candles(candles: Sequence[Candle]) -> QualityReport:
    findings: list[str] = []
    if len(candles) < 30:
        return QualityReport(score=0.0, tradeable=False, findings=["too few bars"])

    bad = 0
    for i, c in enumerate(candles):
        if c.high < c.low:
            findings.append(f"high<low @{c.open_time}")
            bad += 1
        if c.close > c.high or c.close < c.low or c.open > c.high or c.open < c.low:
            findings.append(f"ohlc outside range @{c.open_time}")
            bad += 1
        if c.high <= 0 or c.low <= 0:
            findings.append(f"non-positive price @{c.open_time}")
            bad += 1
        if i > 0:
            prev = candles[i - 1].close
            if prev and abs(c.open - prev) / prev > 0.04:
                findings.append(f"gap>4% @{c.open_time}")
                bad += 1

    n = max(len(candles), 1)
    score = max(0.0, 1.0 - bad / n)
    tradeable = score >= 0.85 and bad < 5
    if not tradeable and not findings:
        findings.append("quality below 0.85")
    return QualityReport(score=score, tradeable=tradeable, findings=findings[:12])
