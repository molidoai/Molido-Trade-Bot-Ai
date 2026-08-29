"""Walk closed M15 bars with spread costs. No fake winrate.

This is a replay helper, not a performance claim. Costs are applied;
winrate is whatever the path produced on the given candles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Any, Callable

from molido_backtester.costs import CostModel
from molido_shared.types import Candle


@dataclass
class ReplayFill:
    bar_index: int
    side: str
    entry: float
    exit: float
    pnl_net: float
    reason: str


@dataclass
class ReplayResult:
    fills: list[ReplayFill] = field(default_factory=list)
    gross_pnl: float = 0.0
    cost_paid: float = 0.0
    net_pnl: float = 0.0
    bars: int = 0
    trades: int = 0
    winrate: float | None = None


def replay_m15(
    candles: Sequence[Candle],
    *,
    signal_fn: Callable[[Sequence[Candle], int], str | None] | None = None,
    spread_points: float = 1.2,
    point_size: float = 0.0001,
    hold_bars: int = 4,
    sl_points: float = 50.0,
    tp_points: float = 80.0,
) -> ReplayResult:
    """Walk closed bars oldest to newest. signal_fn(window, i) -> BUY/SELL/None.

    Default signal is a naive close>prev close BUY else SELL so the cost
    path is exercised. Do not treat the result as an edge.
    """
    cost = CostModel(spread_points=spread_points, slippage_points=0.0, point_size=point_size, commission_per_lot=0.0)
    res = ReplayResult(bars=len(candles))
    if len(candles) < hold_bars + 2:
        return res

    i = 1
    while i < len(candles) - hold_bars:
        window = candles[: i + 1]
        bar = candles[i]
        if signal_fn is not None:
            side = signal_fn(window, i)
        else:
            side = "BUY" if bar.close >= candles[i - 1].close else "SELL"
        if side not in ("BUY", "SELL"):
            i += 1
            continue
        entry = cost.entry_cost_price(side, bar.close)
        sl_dist = sl_points * point_size
        tp_dist = tp_points * point_size
        sl = entry - sl_dist if side == "BUY" else entry + sl_dist
        tp = entry + tp_dist if side == "BUY" else entry - tp_dist
        exit_px = None
        reason = "time"
        for j in range(i + 1, min(i + 1 + hold_bars, len(candles))):
            b = candles[j]
            if side == "BUY":
                if b.low <= sl:
                    exit_px, reason = sl, "SL"
                    break
                if b.high >= tp:
                    exit_px, reason = tp, "TP"
                    break
            else:
                if b.high >= sl:
                    exit_px, reason = sl, "SL"
                    break
                if b.low <= tp:
                    exit_px, reason = tp, "TP"
                    break
        if exit_px is None:
            exit_px = candles[min(i + hold_bars, len(candles) - 1)].close
        fill = cost.exit_cost_price(side, exit_px)
        direction = 1.0 if side == "BUY" else -1.0
        move = (fill - entry) * direction
        pip_value = 10.0 if point_size == 0.0001 else 1.0
        pips = move / point_size
        pnl = pips * pip_value * 0.01  # 0.01 lot
        spread_cost = spread_points * pip_value * 0.01
        res.gross_pnl += pips * pip_value * 0.01 + spread_cost
        res.cost_paid += spread_cost
        res.net_pnl += pnl
        res.fills.append(
            ReplayFill(bar_index=i, side=side, entry=entry, exit=fill, pnl_net=pnl, reason=reason)
        )
        i += hold_bars + 1

    res.trades = len(res.fills)
    if res.trades:
        wins = sum(1 for f in res.fills if f.pnl_net > 0)
        res.winrate = wins / res.trades
    else:
        res.winrate = None
    return res
