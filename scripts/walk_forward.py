#!/usr/bin/env python3
"""Walk-forward smoke/CLI on a sample CSV with spread+commission costs."""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for pkg in (
    "packages/shared",
    "packages/indicators",
    "packages/strategies",
    "packages/backtester",
    "packages/signals",
    "packages/risk",
):
    sys.path.insert(0, str(ROOT / pkg))

from molido_shared.types import Candle, TimeFrame
from molido_backtester import walk_forward, CostModel


def load_csv(path: Path, symbol: str, tf: TimeFrame) -> list[Candle]:
    rows: list[Candle] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for rec in reader:
            ts = rec.get("time") or rec.get("timestamp") or rec.get("open_time")
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            rows.append(
                Candle(
                    symbol=symbol,
                    timeframe=tf,
                    open_time=dt,
                    open=float(rec["open"]),
                    high=float(rec["high"]),
                    low=float(rec["low"]),
                    close=float(rec["close"]),
                    volume=float(rec.get("volume") or 1),
                    spread=float(rec["spread"]) if rec.get("spread") else None,
                    is_closed=True,
                )
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward with spread+commission (not clean mid)")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--train", type=int, default=24)
    ap.add_argument("--test", type=int, default=8)
    ap.add_argument("--warmup", type=int, default=16)
    args = ap.parse_args()
    candles = load_csv(Path(args.csv), args.symbol, TimeFrame.M15)
    result = walk_forward(
        candles,
        args.symbol,
        TimeFrame.M15,
        train_bars=args.train,
        test_bars=args.test,
        warmup=args.warmup,
        cost_model=CostModel(spread_points=1.2, commission_per_lot=7.0),
    )
    m = result.metrics
    print(
        f"folds={len(result.folds)} oos_trades={m.total_trades} "
        f"net={m.net_profit:.2f} commission={m.total_commission:.2f} notes={result.notes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
