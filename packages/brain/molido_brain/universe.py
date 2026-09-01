"""Cheap universe picker. Brain chooses symbol/TF; does not loop every pair x TF.

Default majors + a few crosses. No M1. M15 primary, H1 trend filter,
M5 only in London/NY overlap when spread is OK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from molido_shared.types import TimeFrame

DEFAULT_UNIVERSE: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "XAUUSD",
)

MAX_NEW_PER_CYCLE = 2
MAX_OPEN = 3
MAX_H1_FETCH = 6

_TF = {
    "M5": TimeFrame.M5,
    "5M": TimeFrame.M5,
    "5m": TimeFrame.M5,
    "M15": TimeFrame.M15,
    "15M": TimeFrame.M15,
    "15m": TimeFrame.M15,
    "H1": TimeFrame.H1,
    "1H": TimeFrame.H1,
    "1h": TimeFrame.H1,
    "H4": TimeFrame.H4,
    "D1": TimeFrame.D1,
}


def _norm(symbol: str) -> str:
    return (symbol or "").replace("/", "").replace(".", "").strip().upper()


def is_auto_symbols(raw: str | None) -> bool:
    text = (raw or "").strip().lower()
    return text in ("", "auto", "*", "all", "universe")


def is_auto_timeframe(raw: str | None) -> bool:
    text = (raw or "").strip().lower()
    return text in ("", "auto", "brain")


def resolve_universe(raw: str | None) -> list[str]:
    if is_auto_symbols(raw):
        return list(DEFAULT_UNIVERSE)
    parts = []
    seen: set[str] = set()
    for chunk in (raw or "").replace(";", ",").split(","):
        s = _norm(chunk)
        if s and s not in seen:
            seen.add(s)
            parts.append(s)
    return parts or list(DEFAULT_UNIVERSE)


def resolve_trade_timeframe(
    raw: str | None,
    *,
    overlap: bool,
    spread_ok: bool,
) -> TimeFrame:
    key = (raw or "").strip()
    if key.upper() in ("M1", "1M"):
        return TimeFrame.M15
    if not is_auto_timeframe(raw):
        tf = _TF.get(key) or _TF.get(key.upper())
        if tf is not None:
            return tf
    if overlap and spread_ok:
        return TimeFrame.M5
    return TimeFrame.M15


@dataclass
class CheapCandidate:
    symbol: str
    score: float
    spread: float | None = None
    mid: float | None = None
    h1_side: str | None = None
    atr_ratio: float | None = None
    spread_ok: bool = False
    reasons: list[str] = field(default_factory=list)


def cheap_score(
    *,
    session_ok: bool,
    overlap: bool,
    spread: float | None,
    mid: float | None,
    h1_side: str | None = None,
    atr_ratio: float | None = None,
) -> tuple[float, list[str], bool]:
    reasons: list[str] = []
    if not session_ok:
        return -1.0, ["session closed"], False
    score = 1.0
    if overlap:
        score += 0.4
        reasons.append("overlap")
    spread_ok = False
    if spread is None or mid is None or mid <= 0:
        score -= 0.5
        reasons.append("no tick")
    else:
        rel = spread / mid
        cap = 0.0006 if mid > 50 else 0.00035
        tight = 0.00025 if mid > 50 else 0.00012
        if rel > cap:
            reasons.append(f"wide spread {rel:.5f}")
            return -1.0, reasons, False
        spread_ok = True
        if rel < tight:
            score += 0.35
            reasons.append("tight spread")
        else:
            score += 0.1
        # Break ties by how tight the spread actually is. The buckets above put
        # most majors on an identical score (observed live: EURUSD, GBPUSD and
        # USDJPY all at exactly 1.65), and since sorting is stable that left the
        # ranking decided by position in DEFAULT_UNIVERSE -- XAUUSD, being last,
        # could never be selected however good its spread was. Capped well under
        # the 0.25 gap between the buckets so it only orders symbols already
        # judged equal; it can never promote a wide spread over a tight one.
        score += 0.05 * (1.0 - min(rel / cap, 1.0))
    if h1_side in ("BUY", "SELL"):
        score += 0.3
        reasons.append(f"h1={h1_side}")
    elif h1_side:
        score -= 0.1
        reasons.append("h1 flat")
    if atr_ratio is not None:
        if atr_ratio < 0.0003:
            reasons.append("dead ATR")
            return -1.0, reasons, spread_ok
        if atr_ratio > 0.02:
            score -= 0.25
            reasons.append("hot ATR")
        else:
            score += 0.15
    return score, reasons, spread_ok


class UniversePicker:
    def __init__(
        self,
        max_new: int = MAX_NEW_PER_CYCLE,
        max_open: int = MAX_OPEN,
        max_h1_fetch: int = MAX_H1_FETCH,
    ):
        self.max_new = max_new
        self.max_open = max_open
        self.max_h1_fetch = max_h1_fetch

    def rank(self, rows: Sequence[CheapCandidate]) -> list[CheapCandidate]:
        return sorted(rows, key=lambda r: r.score, reverse=True)

    def select(
        self,
        ranked: Sequence[CheapCandidate],
        open_symbols: Sequence[str] | None = None,
    ) -> list[CheapCandidate]:
        open_n = {_norm(s) for s in (open_symbols or [])}
        room = max(0, self.max_open - len(open_n))
        take = min(self.max_new, room)
        picked: list[CheapCandidate] = []
        if take <= 0:
            return picked
        for row in ranked:
            if _norm(row.symbol) in open_n:
                continue
            if row.score <= 0:
                continue
            if len(picked) >= take:
                break
            picked.append(row)
        return picked

    def h1_budget(self, spread_ranked: Sequence[str]) -> list[str]:
        return list(spread_ranked)[: self.max_h1_fetch]
