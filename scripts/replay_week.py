#!/usr/bin/env python3
"""Replay closed M15 bars with spread costs. Prints fills; no profit claim."""

from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone

from molido_shared.types import Candle, TimeFrame
from molido_backtester.replay import replay_m15


def synthetic_week() -> list[Candle]:
    t0 = datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc)
    price = 1.1000
    out = []
    for i in range(5 * 24 * 4):
        o = price
        c = price + (0.00012 if i % 7 else -0.00008)
        h = max(o, c) + 0.00015
        l = min(o, c) - 0.00015
        out.append(
            Candle(
                symbol="EURUSD",
                timeframe=TimeFrame.M15,
                open_time=t0 + timedelta(minutes=15 * i),
                open=round(o, 5),
                high=round(h, 5),
                low=round(l, 5),
                close=round(c, 5),
                volume=100.0,
                is_closed=True,
            )
        )
        price = c
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Replay M15 with spread costs")
    p.add_argument("--spread-points", type=float, default=1.2)
    args = p.parse_args()
    candles = synthetic_week()
    res = replay_m15(candles, spread_points=args.spread_points)
    print(f"bars={res.bars} trades={res.trades} cost_paid={res.cost_paid:.4f} net={res.net_pnl:.4f}")
    if res.winrate is None:
        print("winrate=n/a (no trades)")
    else:
        print(f"winrate={res.winrate:.3f} (observed on this path only; not a forecast)")


if __name__ == "__main__":
    main()
