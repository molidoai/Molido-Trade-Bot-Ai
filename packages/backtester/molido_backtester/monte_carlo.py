"""Bootstrap / shuffle Monte Carlo on a demo-journal R sequence.

If the 5th percentile equity path breaches a ruin threshold, print a warning.
Does not auto-resize live size; log only. A human must change risk.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class MonteCarloResult:
    n_paths: int
    n_trades: int
    ruin_threshold: float
    p5_min_equity: float
    p50_final: float
    p5_final: float
    ruin_hit: bool
    warning: str = ""
    notes: list[str] = field(default_factory=list)


def _equity_path(rs: Sequence[float], start: float = 1.0) -> list[float]:
    eq = start
    path = [eq]
    for r in rs:
        eq = eq + float(r) * 0.0025
        path.append(eq)
    return path


def monte_carlo(
    r_sequence: Sequence[float],
    *,
    n_paths: int = 400,
    ruin_threshold: float = 0.80,
    start_equity: float = 1.0,
    seed: int = 7,
    bootstrap: bool = True,
) -> MonteCarloResult:
    rs = [float(x) for x in r_sequence]
    n = len(rs)
    rng = random.Random(seed)
    if n == 0:
        return MonteCarloResult(
            n_paths=0, n_trades=0, ruin_threshold=ruin_threshold,
            p5_min_equity=start_equity, p50_final=start_equity, p5_final=start_equity,
            ruin_hit=False, warning="", notes=["empty R sequence"],
        )
    mins: list[float] = []
    finals: list[float] = []
    for _ in range(n_paths):
        if bootstrap:
            sample = [rng.choice(rs) for _ in range(n)]
        else:
            sample = list(rs)
            rng.shuffle(sample)
        path = _equity_path(sample, start=start_equity)
        mins.append(min(path))
        finals.append(path[-1])
    mins_sorted = sorted(mins)
    finals_sorted = sorted(finals)
    idx5 = max(0, int(math.floor(0.05 * (n_paths - 1))))
    p5_min = mins_sorted[idx5]
    p5_final = finals_sorted[idx5]
    p50_final = finals_sorted[len(finals_sorted) // 2]
    floor = start_equity * float(ruin_threshold)
    ruin_hit = p5_min < floor
    warning = ""
    if ruin_hit:
        warning = (
            f"MONTE CARLO WARNING: 5th percentile min equity {p5_min:.4f} "
            f"breaches ruin floor {floor:.4f} ({ruin_threshold:.0%} of start). "
            "Log only — do not auto-resize live risk without a human."
        )
    return MonteCarloResult(
        n_paths=n_paths, n_trades=n, ruin_threshold=ruin_threshold,
        p5_min_equity=round(p5_min, 6), p50_final=round(p50_final, 6),
        p5_final=round(p5_final, 6), ruin_hit=ruin_hit, warning=warning,
        notes=["additive 0.25% of equity per 1R; no live resize"],
    )


def load_journal_r(path: str, n: int = 200) -> list[float]:
    import json
    out: list[float] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event") not in ("close", "exit", "flatten"):
                    continue
                r = rec.get("r_multiple", rec.get("r"))
                if r is None:
                    continue
                try:
                    out.append(float(r))
                except (TypeError, ValueError):
                    continue
    except FileNotFoundError:
        return []
    return out[-n:]
