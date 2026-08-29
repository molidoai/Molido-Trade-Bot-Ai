"""VPS-to-broker latency probe. No secrets. Logs milliseconds; warns above 80ms."""

from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any

logger = logging.getLogger(__name__)

WARN_MS = 80.0


def probe_tcp(host: str, port: int = 443, timeout: float = 2.0) -> dict[str, Any]:
    started = time.perf_counter()
    err = ""
    ok = False
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.close()
        ok = True
    except OSError as exc:
        err = str(exc)
    ms = (time.perf_counter() - started) * 1000.0
    warn = ms > WARN_MS or not ok
    rec = {
        "host": host,
        "port": int(port),
        "ms": round(ms, 2),
        "ok": ok,
        "warn": warn,
        "error": err,
        "threshold_ms": WARN_MS,
    }
    if warn:
        logger.warning("latency probe %s:%s %.1fms ok=%s %s", host, port, ms, ok, err)
    else:
        logger.info("latency probe %s:%s %.1fms", host, port, ms)
    return rec


def probe_latency(
    host: str | None = None,
    port: int | None = None,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """TCP connect timing to a broker-ish host (MT5_RPC_HOST or MT5_LATENCY_HOST)."""
    host = (
        host
        or os.getenv("MT5_LATENCY_HOST")
        or os.getenv("MT5_RPC_HOST")
        or "1.1.1.1"
    )
    port = int(port or os.getenv("MT5_LATENCY_PORT") or os.getenv("MT5_RPC_PORT") or 443)
    if host in ("host.docker.internal", "127.0.0.1", "localhost") and port == 443:
        port = int(os.getenv("MT5_RPC_PORT") or 8001)
    return probe_tcp(host, port, timeout=timeout)


def probe_tick_roundtrip(get_tick, symbol: str = "EURUSD") -> dict[str, Any]:
    """Time a connected MT5 get_tick call. Pass a callable; no engine start required."""
    started = time.perf_counter()
    err = ""
    ok = False
    try:
        tick = get_tick(symbol)
        ok = tick is not None
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        tick = None
    ms = (time.perf_counter() - started) * 1000.0
    warn = ms > WARN_MS or not ok
    rec = {
        "symbol": symbol,
        "ms": round(ms, 2),
        "ok": ok,
        "warn": warn,
        "error": err,
        "threshold_ms": WARN_MS,
        "tick": bool(tick),
    }
    if warn:
        logger.warning("tick roundtrip %s %.1fms ok=%s %s", symbol, ms, ok, err)
    else:
        logger.info("tick roundtrip %s %.1fms", symbol, ms)
    return rec
