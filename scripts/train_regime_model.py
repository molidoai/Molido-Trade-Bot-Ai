#!/usr/bin/env python3
"""Train a lightweight ML regime classifier from collected M15 history and
validate it walk-forward (time-ordered folds, never random k-fold — a
regime label predicted from shuffled data would leak future information).

This does NOT replace packages/regime/molido_regime/engine.py. It's an
optional companion (packages/regime/molido_regime/ml_engine.py) that only
ever *reduces* risk size in packages/risk/molido_risk/engine.py, alongside
the existing rule-based "High Volatility" regime path — never a direction
or entry signal (see ml_engine.py's docstring for why).

Label: what regime is *about to happen* over the next FORWARD_BARS bars,
inferred from realized forward return + forward volatility — not the
current bar's regime (which the rule-based classifier already estimates
directly; predicting the *next* window is the only version of this that's
actually a forecasting task worth training a model for).

Feature engineering is imported from molido_regime.features — the exact
same code path ml_engine.py uses for live inference, so there is no way
for training and serving features to drift apart.

Usage (inside molido-engine container, which already has the historical
CSVs and the molido_* packages on PYTHONPATH; numpy/scikit-learn are now
in apps/trading-engine/requirements.txt so a fresh image build already has
them -- only needed manually if running against an older image):

    pip install --quiet scikit-learn==1.5.2 numpy==2.1.3
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

from molido_regime.features import build_feature_matrix, FEATURE_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("train_regime")

DATA_DIR = Path(os.getenv("COLLECT_OUT_DIR", "/app/data/historical"))
MODEL_OUT = Path(os.getenv("REGIME_MODEL_PATH", "/app/data/regime_model.pkl"))

FORWARD_BARS = 20  # ~5h on M15 — the horizon the model predicts
TREND_THRESHOLD = 0.0025  # 0.25% forward move -> directional regime
VOL_HIGH_PCTL = 0.85  # top 15% of forward volatility -> "HighVol"

LABELS = ["Bull", "Bear", "HighVol", "Sideways"]


@dataclass
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float


class _CandleLike:
    """Duck-types molido_shared.types.Candle for the fields
    molido_regime.features actually reads (close/high/low)."""

    __slots__ = ("close", "high", "low")

    def __init__(self, close: float, high: float, low: float):
        self.close = close
        self.high = high
        self.low = low


def load_csv(path: Path) -> list[Bar]:
    out: list[Bar] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(Bar(row["time"], float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    return out


def build_forward_labels_raw(bars: list[Bar], idx: np.ndarray) -> np.ndarray:
    """(forward_return, forward_volatility) for each feature row index,
    looking FORWARD_BARS ahead of that index -- training-only, not shared
    with live inference (which has no future to look at)."""
    closes = np.array([b.c for b in bars])
    out = np.empty(len(idx), dtype=object)
    for k, i in enumerate(idx):
        forward_ret = (closes[i + FORWARD_BARS] - closes[i]) / closes[i] if closes[i] else 0.0
        forward_window = closes[i : i + FORWARD_BARS + 1]
        forward_vol = float(np.std(np.diff(forward_window) / forward_window[:-1]))
        out[k] = (forward_ret, forward_vol)
    return out


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
        candles = [_CandleLike(b.c, b.h, b.l) for b in bars]
        X, idx = build_feature_matrix(candles, forward_bars=FORWARD_BARS)
        if len(X) == 0:
            continue
        y_raw = build_forward_labels_raw(bars, idx)
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
