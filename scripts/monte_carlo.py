#!/usr/bin/env python3
"""Bootstrap demo-journal R sequence. Warns on 5th-percentile ruin. Log only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/backtester"))

from molido_backtester.monte_carlo import monte_carlo, load_journal_r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="")
    ap.add_argument("--r", nargs="*", type=float, default=[])
    ap.add_argument("--paths", type=int, default=400)
    ap.add_argument("--ruin", type=float, default=0.80)
    args = ap.parse_args()
    rs = list(args.r)
    if args.journal:
        rs = load_journal_r(args.journal)
    result = monte_carlo(rs, n_paths=args.paths, ruin_threshold=args.ruin)
    print(
        f"n={result.n_trades} paths={result.n_paths} p5_min={result.p5_min_equity:.4f} "
        f"p50_final={result.p50_final:.4f} ruin_hit={result.ruin_hit}"
    )
    if result.warning:
        print(result.warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
