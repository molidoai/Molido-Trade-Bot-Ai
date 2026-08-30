"""Feature engineering shared between scripts/train_regime_model.py (offline
training) and ml_engine.py (live inference).

Must stay byte-identical in behavior between the two call sites, or live
predictions silently drift from what the model was actually trained on.
Both import from here rather than each defining their own copy.
"""

from __future__ import annotations
from typing import Sequence

import numpy as np

from molido_shared.types import Candle

FEATURE_NAMES = [
    "ret_5", "ret_20", "ret_50",
    "vol_20", "vol_50",
    "atr_pct",
    "ema9_slope", "ema21_slope", "ema9_over_ema21",
    "rsi_14",
    "range_pct",
]

WARMUP_BARS = 60  # minimum candles needed before the first valid feature row


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(closes, prepend=closes[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.zeros_like(closes)
    avg_loss = np.zeros_like(closes)
    avg_gain[period] = gain[1 : period + 1].mean() if len(gain) > period else 0.0
    avg_loss[period] = loss[1 : period + 1].mean() if len(loss) > period else 0.0
    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.nan), where=avg_loss != 0)
    out = 100 - 100 / (1 + rs)
    out[: period + 1] = 50.0
    return np.nan_to_num(out, nan=50.0)


def ema(values: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _atr14(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    tr = np.concatenate([[highs[0] - lows[0]], tr])
    atr14 = np.empty_like(tr)
    atr14[0] = tr[0]
    for i in range(1, len(tr)):
        atr14[i] = (atr14[i - 1] * 13 + tr[i]) / 14
    return atr14


def _feature_row_at(i: int, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, ema9: np.ndarray, ema21: np.ndarray, rsi14: np.ndarray, atr14: np.ndarray) -> list[float]:
    ret_5 = (closes[i] - closes[i - 5]) / closes[i - 5] if closes[i - 5] else 0.0
    ret_20 = (closes[i] - closes[i - 20]) / closes[i - 20] if closes[i - 20] else 0.0
    ret_50 = (closes[i] - closes[i - 50]) / closes[i - 50] if closes[i - 50] else 0.0
    window = closes[i - 20 : i + 1]
    vol_20 = float(np.std(np.diff(window) / window[:-1])) if len(window) > 1 else 0.0
    window50 = closes[i - 50 : i + 1]
    vol_50 = float(np.std(np.diff(window50) / window50[:-1])) if len(window50) > 1 else 0.0
    atr_pct = atr14[i] / closes[i] if closes[i] else 0.0
    ema9_slope = (ema9[i] - ema9[i - 5]) / closes[i] if closes[i] else 0.0
    ema21_slope = (ema21[i] - ema21[i - 5]) / closes[i] if closes[i] else 0.0
    ema9_over_ema21 = 1.0 if ema9[i] > ema21[i] else -1.0
    range_pct = (highs[i] - lows[i]) / closes[i] if closes[i] else 0.0
    return [ret_5, ret_20, ret_50, vol_20, vol_50, atr_pct, ema9_slope, ema21_slope, ema9_over_ema21, rsi14[i], range_pct]


def build_feature_matrix(candles: Sequence[Candle], forward_bars: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Batch feature builder for training. Returns (X, idx) skipping the
    warmup and (if forward_bars>0) trailing rows a caller needs for labels."""
    closes = np.array([c.close for c in candles])
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    atr14 = _atr14(highs, lows, closes)

    n = len(candles)
    rows: list[list[float]] = []
    idx: list[int] = []
    for i in range(WARMUP_BARS, n - forward_bars):
        rows.append(_feature_row_at(i, closes, highs, lows, ema9, ema21, rsi14, atr14))
        idx.append(i)
    return np.array(rows), np.array(idx)


def latest_feature_row(candles: Sequence[Candle]) -> np.ndarray | None:
    """Live-inference version: one feature row for the most recent candle.
    None if there isn't enough history yet."""
    if len(candles) < WARMUP_BARS + 1:
        return None
    closes = np.array([c.close for c in candles])
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    atr14 = _atr14(highs, lows, closes)
    i = len(candles) - 1
    return np.array(_feature_row_at(i, closes, highs, lows, ema9, ema21, rsi14, atr14))
