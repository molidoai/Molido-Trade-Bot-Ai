"""Decision brain — three numeric brains in series. Still no LLM.

Brain1 Setup → Brain2 Edge → Brain3 Survival.
Each may only veto or cut size (size_mult in {1.0, 0.5, 0}). Never enlarges.
Never picks direction via LLM. This is not a profit guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from molido_brain.brains import (
    Brain1Setup,
    Brain2Edge,
    Brain3Survival,
    BrainVote,
    clamp_size,
    snapshot_features,
)
from molido_strategies.base import SignalSide


@dataclass
class BrainDecision:
    allow: bool
    p_win: float
    expected_r: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
    size_mult: float = 1.0
    votes: list[BrainVote] = field(default_factory=list)


class DecisionBrain:
    """Runs Setup, Edge, Survival in series. Final size is min of the three."""

    def __init__(
        self,
        min_p: float = 0.58,
        min_ev: float = 0.10,
        default_swap_r: float = 0.03,
        pause_on_negative_journal: bool = True,
        max_spread_stop: float = 0.25,
        dead_atr_ratio: float = 0.0003,
        atr_vs_stop_max: float = 1.2,
        daily_loss_limit: float = 0.02,
    ):
        self.min_p = min_p
        self.min_ev = min_ev
        self.default_swap_r = default_swap_r
        self.pause_on_negative_journal = pause_on_negative_journal
        self.max_spread_stop = max_spread_stop
        self.dead_atr_ratio = dead_atr_ratio
        self.atr_vs_stop_max = atr_vs_stop_max
        self.daily_loss_limit = daily_loss_limit
        self.setup = Brain1Setup(max_spread_stop=max_spread_stop)
        self.edge = Brain2Edge(min_p=min_p, min_ev=min_ev)
        self.survival = Brain3Survival(
            pause_on_negative_journal=pause_on_negative_journal,
            dead_atr_ratio=dead_atr_ratio,
            atr_vs_stop_max=atr_vs_stop_max,
            daily_loss_limit=daily_loss_limit,
        )

    def decide(
        self,
        signal: Any,
        indicators: dict | None = None,
        regime: str | None = None,
        agreeing: int = 1,
        **kwargs: Any,
    ) -> BrainDecision:
        """Compatible with pipeline(signal, indicators, regime, agreeing).

        Optional kwargs: h1_side, spread, journal_stats, swap_r, candles,
        overlap, now, session_ok, universe_score, open_symbols, symbol,
        daily_pnl, equity, daily_loss_limit.
        """
        if signal.side == SignalSide.EXIT:
            return BrainDecision(
                allow=True,
                p_win=1.0,
                expected_r=0.0,
                reasons=["exit path"],
                size_mult=1.0,
            )

        snap = snapshot_features(
            signal,
            indicators=indicators,
            regime=regime,
            agreeing=agreeing,
            h1_side=kwargs.get("h1_side"),
            spread=kwargs.get("spread"),
            swap_r=kwargs.get("swap_r"),
            candles=kwargs.get("candles"),
            overlap=kwargs.get("overlap"),
            now=kwargs.get("now"),
            default_swap_r=self.default_swap_r,
        )

        session_ok = kwargs.get("session_ok")
        if session_ok is None:
            session_ok = True
        v1 = self.setup.vote(
            snap,
            h1_side=kwargs.get("h1_side"),
            spread=kwargs.get("spread"),
            session_ok=bool(session_ok),
            universe_score=kwargs.get("universe_score"),
        )
        votes = [v1]
        if not v1.allow or v1.size_mult <= 0:
            return self._pack(False, 0.0, 0.0, 0.0, votes, snap)

        v2 = self.edge.vote(snap, now=kwargs.get("now"))
        votes.append(v2)
        if not v2.allow or v2.size_mult <= 0:
            return self._pack(
                False,
                float(v2.p_win or 0.0),
                float(v2.expected_r or 0.0),
                0.0,
                votes,
                snap,
            )

        v3 = self.survival.vote(
            snap,
            journal_stats=kwargs.get("journal_stats"),
            open_symbols=kwargs.get("open_symbols"),
            symbol=kwargs.get("symbol") or getattr(signal, "symbol", None),
            daily_pnl=kwargs.get("daily_pnl"),
            equity=kwargs.get("equity"),
            daily_loss_limit=kwargs.get("daily_loss_limit", self.daily_loss_limit),
        )
        votes.append(v3)
        if not v3.allow or v3.size_mult <= 0:
            return self._pack(
                False,
                float(v2.p_win or 0.0),
                float(v2.expected_r or 0.0),
                0.0,
                votes,
                snap,
            )

        size = clamp_size(min(v1.size_mult, v2.size_mult, v3.size_mult))
        if size > 1.0:
            size = 1.0
        allow = size > 0
        return self._pack(
            allow,
            float(v2.p_win or 0.0),
            float(v2.expected_r or 0.0),
            size,
            votes,
            snap,
        )

    def _pack(
        self,
        allow: bool,
        p: float,
        ev: float,
        size_mult: float,
        votes: list[BrainVote],
        snap: Any,
    ) -> BrainDecision:
        reasons: list[str] = []
        for v in votes:
            reasons.extend(v.reasons)
        numeric = {
            k: float(val)
            for k, val in snap.feats_raw.items()
            if isinstance(val, (int, float))
        }
        numeric.update(
            {
                "score_n": snap.score_n,
                "rr": snap.rr,
                "trend": snap.trend,
                "rsi_fit": snap.rsi_fit,
                "vol": snap.vol,
                "agree": snap.agree_n,
                "swap_r": snap.swap,
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
            votes=votes,
        )

    def rank_universe(self, rows: list) -> list:
        """Rank cheap-scored symbols. Does not pick BUY/SELL via LLM."""
        return sorted(rows, key=lambda r: float(getattr(r, "score", 0.0)), reverse=True)
