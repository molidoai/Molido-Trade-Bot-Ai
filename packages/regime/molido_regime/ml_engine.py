"""ML volatility-warning signal (optional companion to MarketRegimeEngine).

scripts/train_regime_model.py validated this model walk-forward: it has a
real, honest edge at spotting *forward high-volatility* windows (recall up
to ~0.67, precision up to ~0.84 in later folds), but essentially none at
predicting direction (Bull/Bear recall ~0-1% in every fold). So this class
deliberately only exposes a high-volatility probability -- it is not, and
must not become, a direction/entry signal. RiskEngine only ever uses it to
*reduce* size via the same high_vol_risk_mult path the rule-based
"High Volatility" regime already uses -- never to allow or enlarge a trade.

Fails soft: if no trained model file is present, every call returns None,
and callers must treat that exactly like "no ML signal available" (fall
back to the rule-based regime only). A missing model must never become a
denial or a silent full-size trade -- it should look identical to before
this file existed.
"""

from __future__ import annotations
import logging
import os
import pickle
from pathlib import Path
from typing import Sequence

from molido_shared.types import Candle
from molido_regime.features import latest_feature_row

logger = logging.getLogger(__name__)


class MLVolatilityDetector:
    def __init__(self, model_path: str | os.PathLike | None = None):
        self.model_path = Path(model_path or os.getenv("REGIME_MODEL_PATH", "/app/data/regime_model.pkl"))
        self._model = None
        self._labels: list[str] | None = None
        self._high_vol_idx: int | None = None
        self._load_attempted = False

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_attempted:
            return False
        self._load_attempted = True
        if not self.model_path.exists():
            logger.info("no regime ML model at %s; volatility signal disabled", self.model_path)
            return False
        try:
            with self.model_path.open("rb") as fh:
                payload = pickle.load(fh)
            self._model = payload["model"]
            self._labels = list(payload["labels"])
            self._high_vol_idx = list(self._model.classes_).index("HighVol")
            logger.info(
                "loaded regime ML model from %s (trained_on_rows=%s, mean_wf_accuracy=%.3f)",
                self.model_path,
                payload.get("trained_on_rows"),
                payload.get("walk_forward_summary", {}).get("mean_accuracy", float("nan")),
            )
            return True
        except Exception:
            logger.exception("failed to load regime ML model from %s", self.model_path)
            self._model = None
            return False

    def high_vol_probability(self, candles: Sequence[Candle]) -> float | None:
        """P(the model's HighVol label) for the upcoming window, or None if
        no model is loaded or there isn't enough candle history yet."""
        if not self._ensure_loaded():
            return None
        row = latest_feature_row(candles)
        if row is None:
            return None
        try:
            proba = self._model.predict_proba(row.reshape(1, -1))[0]
            return float(proba[self._high_vol_idx])
        except Exception:
            logger.exception("regime ML inference failed")
            return None


_default_detector: MLVolatilityDetector | None = None


def get_default_detector() -> MLVolatilityDetector:
    global _default_detector
    if _default_detector is None:
        _default_detector = MLVolatilityDetector()
    return _default_detector
