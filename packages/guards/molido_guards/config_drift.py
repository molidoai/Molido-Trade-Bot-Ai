"""Config Drift Detector (Master Prompt §27.1.27)."""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class DriftResult:
    drifted: bool
    differences: list[str]
    current_hash: str
    baseline_hash: str


class ConfigDriftDetector:
    def __init__(self):
        self._baseline: dict[str, Any] | None = None
        self._baseline_hash: str = ""

    @staticmethod
    def _hash(cfg: dict[str, Any]) -> str:
        blob = json.dumps(cfg, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def set_baseline(self, cfg: dict[str, Any]) -> str:
        self._baseline = dict(cfg)
        self._baseline_hash = self._hash(cfg)
        return self._baseline_hash

    def check(self, cfg: dict[str, Any]) -> DriftResult:
        current_hash = self._hash(cfg)
        if self._baseline is None:
            return DriftResult(False, ["No baseline set"], current_hash, "")
        diffs = []
        for k, v in self._baseline.items():
            if k not in cfg:
                diffs.append(f"Missing key: {k}")
            elif cfg[k] != v:
                diffs.append(f"Changed: {k}")
        for k in cfg:
            if k not in self._baseline:
                diffs.append(f"New key: {k}")
        return DriftResult(bool(diffs), diffs, current_hash, self._baseline_hash)
