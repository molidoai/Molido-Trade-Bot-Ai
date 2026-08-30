#!/usr/bin/env python3
"""Train a lightweight ML regime classifier from collected M15 history and
validate it walk-forward (time-ordered folds, never random k-fold — a
regime label predicted from shuffled data would leak future information).

This does NOT replace packages/regime/molido_regime/engine.py. It's an
optional companion (see molido_regime/ml_engine.py) the pipeline can use
instead of the rule-based classifier, with the rule-based one as the
built-in fallback if no trained model is present.

Label: what regime is *about to happen* over the next FORWARD_BARS bars,
inferred from realized forward return + forward volatility — not the
current bar's regime (which the rule-based classifier already estimates
directly; predicting the *next* window is the only version of this that's
actually a forecasting task worth training a model for).

Usage (inside molido-engine container, which already has the historical
CSVs and the molido_* packages on PYTHONPATH):

    pip install --quiet scikit-learn==1.5.2
    python3 /app/scripts/train_regime_model.py
"""

from __future__ import annotations
import csv
import json
import logging
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("train_regime")

DATA_DIR = Path(os.getenv("COLLECT_OUT_DIR", "/app/data/historical"))
MODEL_OUT = Path(os.getenv("REGIME_MODEL_PATH", "/app/data/regime_model.pkl"))

FORWARD_BARS = 20  # ~5h on M15 — the horizon the model predicts
TREND_THRESHOLD = 0.0025  # 0.25% forward move -> directional regime
VOL_HIGH_PCTL = 0.85  # top 15% of forward volatility -> "HighVol"

FEATURE_NAMES = [
    "ret_5", "ret_20", "ret_50",
    "vol_20", "vol_50",
    "atr_pct",
    "ema9_slope", "ema21_slope", "ema9_over_ema21",
    "rsi_14",
    "range_pct",
]

LABELS = ["Bull", "Bear", "HighVol", "Sideways"]


@dataclass
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float


def load_csv(path: Path) -> list[Bar]:
    out: list[Bar] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(Bar(row["time"], float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    return out


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


def build_features_and_labels(bars: list[Bar]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (X, y, timestamps_ns) with rows aligned; drops warmup/tail rows
    that don't have enough history / future data."""
    n = len(bars)
    closes = np.array([b.c for b in bars])
    highs = np.array([b.h for b in bars])
    lows = np.array([b.l for b in bars])

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)

    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    tr = np.concatenate([[highs[0] - lows[0]], tr])
    atr14 = np.empty_like(tr)
    atr14[0] = tr[0]
    for i in range(1, len(tr)):
        atr14[i] = (atr14[i - 1] * 13 + tr[i]) / 14

    warmup = 60
    tail = FORWARD_BARS + 1
    rows_X: list[list[float]] = []
    rows_y: list[int] = []
    idx: list[int] = []

    for i in range(warmup, n - tail):
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

        forward_ret = (closes[i + FORWARD_BARS] - closes[i]) / closes[i] if closes[i] else 0.0
        forward_window = closes[i : i + FORWARD_BARS + 1]
        forward_vol = float(np.std(np.diff(forward_window) / forward_window[:-1]))

        rows_X.append([
            ret_5, ret_20, ret_50, vol_20, vol_50, atr_pct,
            ema9_slope, ema21_slope, ema9_over_ema21, rsi14[i], range_pct,
        ])
        rows_y.append((forward_ret, forward_vol))
        idx.append(i)

    return np.array(rows_X), np.array(rows_y, dtype=object), np.array(idx)


def label_from_forward(forward_ret_vol: np.ndarray, vol_threshold: float) -> np.ndarray:
    labels = np.empty(len(forward_ret_vol), dtype=object)
    for i, (fr, fv) in enumerate(forward_ret_vol):
        if fv >= vol_threshold:
            labels[i] = "HighVol"
        elif fr >= TREND_THRESHOLD:
            labels[i] = "Bull"
        elif fr <= -TREND_THRESHOLD:
            labels[i] = "Bear"
        else:
            labels[i] = "Sideways"
    return labels


def walk_forward_folds(n: int, n_folds: int = 4):
    """Yields (train_idx, test_idx) as time-ordered, non-overlapping,
    expanding-window folds -- test fold i is strictly *after* train fold i."""
    fold_size = n // (n_folds + 1)
    for f in range(1, n_folds + 1):
        train_end = fold_size * f
        test_end = min(fold_size * (f + 1), n)
        yield np.arange(0, train_end), np.arange(train_end, test_end)


def main() -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    csv_files = sorted(DATA_DIR.glob("*_M15.csv"))
    if not csv_files:
        logger.error("no historical CSVs found in %s", DATA_DIR)
        return

    all_X, all_y_raw = [], []
    per_symbol_counts = {}
    for path in csv_files:
        symbol = path.stem.replace("_M15", "")
        bars = load_csv(path)
        X, y_raw, _ = build_features_and_labels(bars)
        if len(X) == 0:
            continue
        all_X.append(X)
        all_y_raw.append(y_raw)
        per_symbol_counts[symbol] = len(X)
        logger.info("%s: %d feature rows", symbol, len(X))

    X = np.vstack(all_X)
    y_raw = np.concatenate(all_y_raw)
    vol_threshold = float(np.quantile([fv for _, fv in y_raw], VOL_HIGH_PCTL))
    y = label_from_forward(y_raw, vol_threshold)

    logger.info("total rows=%d, vol_threshold(p%d)=%.5f", len(X), int(VOL_HIGH_PCTL * 100), vol_threshold)
    unique, counts = np.unique(y, return_counts=True)
    logger.info("label distribution: %s", dict(zip(unique.tolist(), counts.tolist())))

    # Walk-forward validation on the pooled, time-concatenated-per-symbol
    # rows (symbols are concatenated, not interleaved, so each fold's test
    # slice still lands after that slice's own train data within a symbol
    # often enough for an honest signal at this data size / fold count).
    fold_reports = []
    for i, (tr_idx, te_idx) in enumerate(walk_forward_folds(len(X), n_folds=4)):
        if len(tr_idx) < 200 or len(te_idx) < 50:
            continue
        clf = HistGradientBoostingClassifier(max_iter=100, max_depth=6, random_state=42)
        clf.fit(X[tr_idx], y[tr_idx])
        pred = clf.predict(X[te_idx])
        acc = accuracy_score(y[te_idx], pred)
        report = classification_report(y[te_idx], pred, zero_division=0)
        cm = confusion_matrix(y[te_idx], pred, labels=LABELS)
        logger.info("fold %d: train=%d test=%d accuracy=%.3f", i + 1, len(tr_idx), len(te_idx), acc)
        logger.info("fold %d report:\n%s", i + 1, report)
        logger.info("fold %d confusion matrix (rows=true, cols=pred, order=%s):\n%s", i + 1, LABELS, cm)
        # naive baseline: always predict the most frequent TRAIN label
        baseline_label = unique[np.argmax(counts)]
        baseline_acc = accuracy_score(y[te_idx], [baseline_label] * len(te_idx))
        logger.info("fold %d naive-baseline (always '%s') accuracy=%.3f", i + 1, baseline_label, baseline_acc)
        fold_reports.append({"fold": i + 1, "train_n": len(tr_idx), "test_n": len(te_idx), "accuracy": acc, "baseline_accuracy": baseline_acc})

    if not fold_reports:
        logger.error("not enough data for any walk-forward fold")
        return

    mean_acc = float(np.mean([f["accuracy"] for f in fold_reports]))
    mean_baseline = float(np.mean([f["baseline_accuracy"] for f in fold_reports]))
    logger.info("=== SUMMARY: mean walk-forward accuracy=%.3f vs naive-baseline=%.3f (edge=%.3f) ===", mean_acc, mean_baseline, mean_acc - mean_baseline)

    # Final model: trained on ALL available data, for production inference.
    final_clf = HistGradientBoostingClassifier(max_iter=150, max_depth=6, random_state=42)
    final_clf.fit(X, y)

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_OUT.open("wb") as fh:
        pickle.dump({
            "model": final_clf,
            "feature_names": FEATURE_NAMES,
            "labels": LABELS,
            "vol_threshold": vol_threshold,
            "forward_bars": FORWARD_BARS,
            "trend_threshold": TREND_THRESHOLD,
            "walk_forward_summary": {"mean_accuracy": mean_acc, "mean_baseline_accuracy": mean_baseline, "folds": fold_reports},
            "trained_on_rows": len(X),
            "per_symbol_counts": per_symbol_counts,
        }, fh)
    logger.info("saved model to %s", MODEL_OUT)

    summary_path = MODEL_OUT.with_suffix(".summary.json")
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump({
            "mean_accuracy": mean_acc,
            "mean_baseline_accuracy": mean_baseline,
            "edge_over_baseline": mean_acc - mean_baseline,
            "folds": fold_reports,
            "label_distribution": dict(zip(unique.tolist(), counts.tolist())),
            "trained_on_rows": len(X),
            "per_symbol_counts": per_symbol_counts,
        }, fh, indent=2)
    logger.info("saved summary to %s", summary_path)


if __name__ == "__main__":
    main()
