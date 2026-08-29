"""Point-in-time features from CLOSED candles only. No look-ahead."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median, pstdev
from typing import Any, Sequence
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _closes(candles: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for c in candles:
        v = getattr(c, "close", None)
        if v is None and isinstance(c, dict):
            v = c.get("close")
        if v is not None:
            out.append(float(v))
    return out


def _ohlc(c: Any) -> tuple[float, float, float, float]:
    if isinstance(c, dict):
        return float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
    return float(c.open), float(c.high), float(c.low), float(c.close)


def _time(c: Any) -> datetime | None:
    t = getattr(c, "open_time", None)
    if t is None and isinstance(c, dict):
        t = c.get("open_time")
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_g = gains / period
    avg_l = losses / period
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        g = d if d > 0 else 0.0
        l = -d if d < 0 else 0.0
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def atr_series(candles: Sequence[Any], period: int = 14) -> list[float | None]:
    if len(candles) < 2:
        return [None] * len(candles)
    trs: list[float] = []
    for i, c in enumerate(candles):
        o, h, l, cl = _ohlc(c)
        if i == 0:
            trs.append(h - l)
            continue
        _, _, _, prev_c = _ohlc(candles[i - 1])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    out: list[float | None] = [None] * len(trs)
    if len(trs) < period:
        return out
    seed = sum(trs[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(trs)):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def h1_side_from_bars(candles: Sequence[Any] | None) -> str | None:
    """EMA9 vs EMA21 on closed H1 bars. BUY if fast > slow."""
    if not candles or len(candles) < 30:
        return None
    closes = _closes(candles)
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    a, b = e9[-1], e21[-1]
    if a is None or b is None:
        return None
    if a > b:
        return "BUY"
    if a < b:
        return "SELL"
    return "FLAT"


def slope(series: Sequence[float | None], lookback: int = 3) -> float:
    if len(series) < lookback + 1:
        return 0.0
    a = series[-1]
    b = series[-1 - lookback]
    if a is None or b is None or b == 0:
        return 0.0
    return (float(a) - float(b)) / abs(float(b))


def extract_features(
    candles: Sequence[Any] | None,
    *,
    side: str = "BUY",
    stop_distance: float | None = None,
    spread: float | None = None,
    h1_side: str | None = None,
    regime: str | None = None,
    now: datetime | None = None,
    overlap: bool | None = None,
    indicators: dict | None = None,
) -> dict[str, float | str]:
    """All features from closed candles (and optional indicator snapshot)."""
    candles = list(candles or [])
    closes = _closes(candles)
    last_close = closes[-1] if closes else 0.0

    atrs = atr_series(candles, 14) if candles else []
    atr_now = next((x for x in reversed(atrs) if x is not None), None)
    recent = [x for x in atrs[-50:] if x is not None]
    atr_med = median(recent) if recent else None
    atr_std = pstdev(recent) if len(recent) >= 8 else 0.0
    if atr_now is not None and atr_med and atr_std > 0:
        atr_z = (atr_now - atr_med) / atr_std
    elif atr_now is not None and atr_med:
        atr_z = (atr_now - atr_med) / (atr_med + 1e-12)
    else:
        atr_z = 0.0

    rsi_v = rsi(closes, 14) if closes else None
    e9 = ema(closes, 9) if closes else []
    e21 = ema(closes, 21) if closes else []
    ema9_slope = slope(e9, 3) if e9 else 0.0
    ema21_slope = slope(e21, 3) if e21 else 0.0

    last3_ret = 0.0
    if len(closes) >= 4 and closes[-4] != 0:
        last3_ret = (closes[-1] - closes[-4]) / abs(closes[-4])

    spread_stop = 0.0
    if spread is not None and stop_distance and stop_distance > 0:
        spread_stop = float(spread) / float(stop_distance)

    ts = now
    if ts is None and candles:
        ts = _time(candles[-1])
    if ts is None:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ny = ts.astimezone(NY)
    ny_hour = float(ny.hour) + ny.minute / 60.0
    if overlap is None:
        overlap = 8.0 <= ny_hour <= 12.0 and ny.weekday() < 5
    overlap_f = 1.0 if overlap else 0.0

    side_u = (side or "BUY").upper()
    h1 = (h1_side or "").upper() or None
    if h1 in ("BUY", "SELL"):
        h1_trend = 1.0 if h1 == side_u else -1.0
    else:
        h1_trend = 0.0

    if indicators:
        def _iv(*path: str) -> float | None:
            cur: Any = indicators
            for k in path:
                if cur is None:
                    return None
                getter = getattr(cur, "get", None)
                if callable(getter):
                    cur = getter(k)
                elif isinstance(cur, dict):
                    cur = cur.get(k)
                else:
                    return None
            try:
                return float(cur) if cur is not None else None
            except (TypeError, ValueError):
                return None

        if rsi_v is None:
            rsi_v = _iv("RSI", "rsi") or _iv("rsi", "rsi") or _iv("RSI", "value")
        if atr_now is None:
            atr_now = _iv("ATR", "atr") or _iv("atr14", "atr")
        if last_close <= 0:
            last_close = _iv("close") or 0.0  # type: ignore[assignment]

    feats: dict[str, float | str] = {
        "atr_z": round(_clip(float(atr_z), -8.0, 8.0), 4),
        "atr": float(atr_now or 0.0),
        "atr_median50": float(atr_med or 0.0),
        "rsi": float(rsi_v if rsi_v is not None else 50.0),
        "ema9_slope": round(float(ema9_slope), 6),
        "ema21_slope": round(float(ema21_slope), 6),
        "last3_ret": round(float(last3_ret), 6),
        "spread_stop": round(float(spread_stop), 4),
        "ny_hour": round(ny_hour, 3),
        "overlap": overlap_f,
        "h1_trend": h1_trend,
        "close": float(last_close or 0.0),
        "regime": str(regime or "Unknown"),
    }
    return feats
