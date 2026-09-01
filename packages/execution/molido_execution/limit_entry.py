"""Limit-entry helpers. New entries are LIMIT at bid (buy) / ask (sell)."""

from __future__ import annotations
from typing import Any


def entry_limit_price(side: str, tick: Any) -> float | None:
    """Buy limit at bid, sell limit at ask. None if no book."""
    if tick is None:
        return None
    s = str(side).upper()
    if s == "BUY":
        bid = getattr(tick, "bid", None)
        return float(bid) if bid is not None else None
    if s == "SELL":
        ask = getattr(tick, "ask", None)
        return float(ask) if ask is not None else None
    return None


def is_exit_side(side: str, reduce_only: bool = False) -> bool:
    return reduce_only or str(side).upper() in ("EXIT", "CLOSE", "FLATTEN")


def shift_stops_to_price(
    entry: float,
    stop_loss: float,
    take_profit: float | None,
    order_price: float,
    max_drift_r: float = 0.5,
) -> tuple[float, float | None, float, str | None]:
    """Re-anchor SL/TP from the signal's entry to the actual order price.

    Strategies compute entry/SL/TP against the last closed candle, but the
    order is placed at the live bid/ask. Sending the original absolute
    levels with a moved price silently distorts the intended risk/reward --
    and once price passes the take-profit, the broker rejects the order
    outright ("Invalid stops", MT5 retcode 10016).

    Shifting both levels by the same drift preserves the stop distance
    exactly, which matters because position size was computed from it.

    Returns (sl, tp, drift, reject_reason). reject_reason is non-None when
    price has moved more than max_drift_r * stop_distance from the signal,
    i.e. the setup is stale and chasing it would enter a different trade
    than the one that was validated.
    """
    stop_distance = abs(float(entry) - float(stop_loss))
    drift = float(order_price) - float(entry)
    if stop_distance > 0:
        max_drift = max_drift_r * stop_distance
        if abs(drift) > max_drift:
            return (
                float(stop_loss),
                take_profit,
                drift,
                f"price drifted {abs(drift):.5f} from signal entry "
                f"(> {max_drift:.5f} = {max_drift_r}R)",
            )
    sl = round(float(stop_loss) + drift, 6)
    tp = round(float(take_profit) + drift, 6) if take_profit else None
    return sl, tp, drift, None
