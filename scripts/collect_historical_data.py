#!/usr/bin/env python3
"""Pull historical M15 candles from the connected MT5 (demo) account for the
default symbol universe and save them as CSV, one file per symbol, for
regime-model training / backtesting. Read-only — never places orders.

Run inside the trading-engine container (it's the only place with network
access to the MT5 RPC bridge):

    docker exec molido-engine python3 /app/scripts/collect_historical_data.py

Credentials come from the same runtime-settings.json the live runner uses —
never printed or logged.
"""

from __future__ import annotations
import asyncio
import csv
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("collector")

from molido_broker import create_broker, BrokerType
from molido_shared.types import TimeFrame
from molido_brain.universe import DEFAULT_UNIVERSE

BARS_PER_SYMBOL = int(os.getenv("COLLECT_BARS", "50000"))
OUT_DIR = Path(os.getenv("COLLECT_OUT_DIR", "/app/data/historical"))


def _load_runtime() -> dict:
    path = os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _pick(rt: dict, *keys: str, env: str | None = None) -> str:
    for key in keys:
        val = rt.get(key)
        if val:
            text = str(val).strip()
            if text and text != "••••":
                return text
    if env:
        return (os.getenv(env) or "").strip()
    return ""


async def main() -> None:
    rt = _load_runtime()
    login_raw = _pick(rt, "mt5_login", "mt5_real_login", env="MT5_REAL_LOGIN")
    password = _pick(rt, "mt5_password", "mt5_real_password", env="MT5_REAL_PASSWORD")
    server = _pick(rt, "mt5_server", "mt5_real_server", env="MT5_REAL_SERVER")
    path = _pick(rt, "mt5_path", "mt5_real_path", env="MT5_REAL_PATH") or None
    if not (login_raw and password and server):
        logger.error("MT5 credentials not configured in runtime-settings.json")
        sys.exit(1)

    broker = create_broker(BrokerType.MT5, login=int(login_raw), password=password, server=server, path=path)
    ok = await broker.connect()
    if not ok:
        logger.error("MT5 connect failed")
        sys.exit(1)
    logger.info("connected, pulling %s bars (M15) for %d symbols", BARS_PER_SYMBOL, len(DEFAULT_UNIVERSE))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, int] = {}
    for symbol in DEFAULT_UNIVERSE:
        try:
            candles = await broker.get_candles(symbol, TimeFrame.M15, count=BARS_PER_SYMBOL)
        except Exception:
            logger.exception("fetch failed for %s", symbol)
            summary[symbol] = 0
            continue
        if not candles:
            logger.warning("%s: 0 bars returned", symbol)
            summary[symbol] = 0
            continue
        out_path = OUT_DIR / f"{symbol}_M15.csv"
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["time", "open", "high", "low", "close", "volume", "spread"])
            for c in candles:
                w.writerow([
                    c.open_time.isoformat(),
                    c.open, c.high, c.low, c.close, c.volume,
                    c.spread if c.spread is not None else "",
                ])
        summary[symbol] = len(candles)
        logger.info("%s: %d bars -> %s (%s .. %s)", symbol, len(candles), out_path, candles[0].open_time.date(), candles[-1].open_time.date())

    await broker.disconnect()
    logger.info("done: %s", summary)


if __name__ == "__main__":
    asyncio.run(main())
