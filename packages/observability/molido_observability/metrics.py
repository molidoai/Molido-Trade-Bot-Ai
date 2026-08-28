"""
In-process metrics registry (Prometheus-compatible text format).
Works without prometheus_client if needed; integrates when available.
"""

from __future__ import annotations
from collections import defaultdict
from threading import Lock
from typing import Iterable


class Counter:
    def __init__(self, name: str, help_text: str = ""):
        self.name = name
        self.help = help_text
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += amount

    def collect(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        with self._lock:
            for labels, val in self._values.items():
                if labels:
                    lbl = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f"{self.name}{{{lbl}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class Gauge:
    def __init__(self, name: str, help_text: str = ""):
        self.name = name
        self.help = help_text
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = Lock()

    def set(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = value

    def collect(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        with self._lock:
            for labels, val in self._values.items():
                if labels:
                    lbl = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f"{self.name}{{{lbl}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class MetricsRegistry:
    def __init__(self):
        self.orders_total = Counter("molido_orders_total", "Orders submitted")
        self.orders_failed = Counter("molido_orders_failed", "Orders failed")
        self.signals_total = Counter("molido_signals_total", "Signals produced")
        self.risk_denials = Counter("molido_risk_denials_total", "Risk engine denials")
        self.equity = Gauge("molido_equity", "Account equity")
        self.drawdown_pct = Gauge("molido_drawdown_pct", "Current drawdown percent")
        self.open_positions = Gauge("molido_open_positions", "Open positions count")
        self.circuit_breaker = Gauge("molido_circuit_breaker", "1 if open else 0")
        self.broker_connected = Gauge("molido_broker_connected", "1 if connected")

    def render(self) -> str:
        parts: list[str] = []
        for metric in (
            self.orders_total, self.orders_failed, self.signals_total,
            self.risk_denials, self.equity, self.drawdown_pct,
            self.open_positions, self.circuit_breaker, self.broker_connected,
        ):
            parts.extend(metric.collect())
        return "\n".join(parts) + "\n"


# Global registry for simple import
metrics = MetricsRegistry()
