"""Learning from realised outcomes.

The three brains are hand-tuned formulas: they score a setup the same way on
day one and day five hundred, and nothing in the system ever fed a trade's
result back into the next decision. This module closes that loop.

It reads closed trades out of the journal and estimates, per bucket
(strategy / symbol / session), what actually happened -- mean R and sample
size -- then turns that into a size multiplier.

Three rules keep it honest:

1. **It can only shrink.** The multiplier is capped at 1.0, matching the rule
   the brains already follow: a brain may veto or cut size, never enlarge and
   never pick direction. Good history buys the *full* configured size, not
   more, so a lucky streak can never inflate risk.

2. **It shrinks toward neutral when data is thin.** With four trades in a
   bucket you know almost nothing; the estimate is pulled toward "no opinion"
   in proportion to how little evidence there is (a standard shrinkage
   estimator). Below MIN_SAMPLES it abstains entirely rather than acting on
   noise. This is the difference between learning and overfitting to a bad
   afternoon.

3. **It never fabricates a number.** No history means None, and None must
   behave exactly like "no signal" upstream -- never like 0.0, which would be
   a claim that the bucket loses money.

What it is not: it does not predict direction, rank setups, or replace the
brains. It answers one narrow question -- "when this bot has traded this
combination before, how did it go?" -- and lets that shade position size.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

# Below this, any apparent edge is indistinguishable from noise, so abstain.
MIN_SAMPLES = 8

# Shrinkage strength: the number of "prior" observations of zero R that the
# estimate is blended against. Larger = more conservative, slower to react.
# At n == PRIOR_STRENGTH the observed mean is halved.
PRIOR_STRENGTH = 12.0

# How far this layer may cut size on its own. It is one input among several,
# not a kill switch -- brain 3 already owns outright vetoes.
MIN_MULT = 0.5

CLOSE_EVENTS = ("close", "exit", "flatten")


@dataclass(frozen=True)
class BucketStats:
    n: int
    mean_r: float
    shrunk_r: float
    wins: int

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0


def _r_of(rec: dict) -> float | None:
    for key in ("r_multiple", "r", "realized_r"):
        val = rec.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def read_closed(path: str, limit: int = 2000) -> list[dict]:
    """Closed trades from a journal file, oldest first. Never raises."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except (FileNotFoundError, OSError):
        return []
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") not in CLOSE_EVENTS:
            continue
        if _r_of(rec) is None:
            continue
        out.append(rec)
    return out


def shrink(values: Sequence[float]) -> float:
    """Mean pulled toward zero in proportion to how little evidence there is.

    With n observations the estimate is n/(n+PRIOR_STRENGTH) of the observed
    mean. Three lucky trades barely move it; sixty move it most of the way.
    """
    n = len(values)
    if n == 0:
        return 0.0
    observed = sum(values) / n
    return observed * (n / (n + PRIOR_STRENGTH))


def _stats(values: Sequence[float]) -> BucketStats:
    return BucketStats(
        n=len(values),
        mean_r=sum(values) / len(values) if values else 0.0,
        shrunk_r=shrink(values),
        wins=sum(1 for v in values if v > 0),
    )


class Experience:
    """Realised performance, sliced by the things a decision can key on."""

    def __init__(self, records: Iterable[dict] | None = None):
        self._by_key: dict[tuple[str, str], list[float]] = {}
        self._all: list[float] = []
        for rec in records or ():
            self.add(rec)

    @classmethod
    def from_journal(cls, path: str, limit: int = 2000) -> "Experience":
        return cls(read_closed(path, limit))

    def add(self, rec: dict) -> None:
        r = _r_of(rec)
        if r is None:
            return
        self._all.append(r)
        for dim, value in (
            ("symbol", rec.get("symbol")),
            ("strategy", rec.get("strategy")),
            ("session", rec.get("session")),
            ("side", rec.get("side")),
            # How the trade ended. Splits "the stop did its job" from "we
            # closed it ourselves", which is the difference between a strategy
            # that is wrong and one that is merely being interrupted.
            ("exit", rec.get("exit_reason")),
        ):
            if value:
                self._by_key.setdefault((dim, str(value)), []).append(r)

    def stats(self, dim: str, value: Any) -> BucketStats | None:
        vals = self._by_key.get((dim, str(value)))
        if not vals or len(vals) < MIN_SAMPLES:
            return None
        return _stats(vals)

    def overall(self) -> BucketStats | None:
        if len(self._all) < MIN_SAMPLES:
            return None
        return _stats(self._all)

    def size_mult(
        self,
        *,
        symbol: str | None = None,
        strategy: str | None = None,
        session: str | None = None,
    ) -> tuple[float | None, str]:
        """Size multiplier from history, plus a human-readable reason.

        Returns (None, reason) when there is not enough evidence, which callers
        must treat as "no opinion" -- identical to this layer being absent.
        """
        buckets: list[tuple[str, BucketStats]] = []
        for dim, value in (("symbol", symbol), ("strategy", strategy), ("session", session)):
            if not value:
                continue
            st = self.stats(dim, value)
            if st is not None:
                buckets.append((f"{dim}={value}", st))

        if not buckets:
            overall = self.overall()
            if overall is None:
                return None, f"not enough closed trades yet (need {MIN_SAMPLES})"
            buckets = [("overall", overall)]

        # The worst bucket governs: if this symbol has been fine but this
        # strategy has been losing, that is a reason for caution either way.
        label, worst = min(buckets, key=lambda kv: kv[1].shrunk_r)

        if worst.shrunk_r >= 0:
            return 1.0, (
                f"{label}: {worst.n} trades, mean {worst.mean_r:+.2f}R "
                f"(adjusted {worst.shrunk_r:+.2f}R) -- full size"
            )

        # Map a negative expectancy onto [MIN_MULT, 1.0). -0.5R adjusted is
        # treated as the point where size is halved; the curve is smooth so
        # there is no cliff at an arbitrary threshold.
        severity = min(1.0, abs(worst.shrunk_r) / 0.5)
        mult = 1.0 - (1.0 - MIN_MULT) * severity
        # Round to something a human can reconcile with the logs.
        mult = round(max(MIN_MULT, min(1.0, mult)), 2)
        return mult, (
            f"{label}: {worst.n} trades, mean {worst.mean_r:+.2f}R "
            f"(adjusted {worst.shrunk_r:+.2f}R) -- size x{mult}"
        )

    def summary(self, top: int = 6) -> list[str]:
        """Human-readable table for the dashboard and Telegram."""
        rows = [
            (key, _stats(vals))
            for key, vals in self._by_key.items()
            if len(vals) >= MIN_SAMPLES
        ]
        rows.sort(key=lambda kv: kv[1].shrunk_r)
        out = []
        for (dim, value), st in rows[:top]:
            out.append(
                f"{dim}={value}: n={st.n} mean={st.mean_r:+.2f}R "
                f"adj={st.shrunk_r:+.2f}R win={st.win_rate:.0%}"
            )
        if not out:
            total = len(self._all)
            out.append(f"هنوز داده کافی نیست — {total} معامله‌ی بسته‌شده، حداقل {MIN_SAMPLES} لازم است")
        return out
