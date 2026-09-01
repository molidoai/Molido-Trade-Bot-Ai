#!/usr/bin/env python3
"""Backtest the REAL decision chain: strategies -> signals -> 3 brains -> risk.

The existing molido_backtester stops at strategies, so it over-counts trades
badly: in production the brains veto most signals. This runs the same
components the live engine runs, so the trade count and expectancy it
reports are comparable to what actually happens.

Compares configurations so "should we add an indicator / another brain?"
can be answered from measurement instead of intuition.

Run inside molido-engine (has the packages and the historical CSVs):
    docker exec molido-engine python3 /app/scripts/backtest_full_chain.py
"""
from __future__ import annotations
import csv, os, sys, json
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, "/packages/shared")

from molido_shared.types import Candle, TimeFrame
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_strategies.base import SignalSide
from molido_signals import SignalEngine
from molido_brain import DecisionBrain

DATA_DIR = os.getenv("COLLECT_OUT_DIR", "/app/data/historical")
WARMUP = 120
MAX_HOLD_BARS = 96          # give a trade 24h on M15 before calling it unresolved
SPREAD = 0.00012            # ~1.2 pip round-trip assumption on majors


def load(path: str, symbol: str) -> list[Candle]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(Candle(
                symbol=symbol, timeframe=TimeFrame.M15,
                open_time=datetime.fromisoformat(r["time"].replace("Z", "+00:00")),
                open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]),
                volume=float(r.get("volume") or 1), is_closed=True,
            ))
    return out


def build(strategies: list[str]):
    ind = IndicatorEngine()
    for name, kw in (("MultiEMA", {}), ("RSI", {"period": 14}), ("ATR", {"period": 14}),
                     ("MACD", {}), ("BollingerBands", {"period": 20}),
                     ("DonchianChannel", {"period": 20}),
                     ("Supertrend", {"period": 10, "multiplier": 3.0})):
        ind.add_from_registry(name, **kw)
    st = StrategyEngine(); st.configure_live(strategies)
    return ind, SignalEngine(accept_threshold=55.0), st


def simulate(candles, entry_i, side, entry, sl, tp) -> float | None:
    """R multiple once SL or TP is touched. Conservative: if a bar spans both,
    assume the stop filled first."""
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    for c in candles[entry_i + 1: entry_i + 1 + MAX_HOLD_BARS]:
        if side == "BUY":
            if c.low <= sl:  return -1.0
            if c.high >= tp: return (tp - entry) / risk
        else:
            if c.high >= sl: return -1.0
            if c.low <= tp:  return (entry - tp) / risk
    return None


def run(symbol: str, candles: list[Candle], strategies: list[str], use_brain: bool, step: int):
    ind, sig, st = build(strategies)
    brain = DecisionBrain() if use_brain else None
    rs, vetoed, signals = [], 0, 0
    i = WARMUP
    while i < len(candles) - MAX_HOLD_BARS - 1:
        window = candles[: i + 1]
        il = ind.compute_latest(window)
        raw = st.evaluate_all(symbol=symbol, timeframe=TimeFrame.M15, candles=window,
                              indicators=il, regime="Bull", account_mode="DEMO",
                              open_position_side=None)
        finals = sig.process(raw, indicators=il, pick_best=True)
        i += step
        if not finals:
            continue
        f = finals[0]
        if not f.accepted or f.side not in (SignalSide.BUY, SignalSide.SELL):
            continue
        if not f.stop_loss or not f.take_profit:
            continue
        signals += 1
        if brain is not None:
            v = brain.decide(f, indicators=il, regime="Bull", agreeing=1,
                             h1_side=None, spread=SPREAD, candles=window,
                             timeframe=TimeFrame.M15, symbol=symbol, open_symbols=[])
            if not v.allow or (v.size_mult or 0) <= 0:
                vetoed += 1
                continue
        side = f.side.value
        # Enter at the live price with spread paid, stops shifted to match --
        # the same re-anchoring the live pipeline does.
        entry = f.entry + (SPREAD if side == "BUY" else -SPREAD)
        drift = entry - f.entry
        r = simulate(candles, i - step, side, entry, f.stop_loss + drift, f.take_profit + drift)
        if r is not None:
            rs.append(r)
    return rs, signals, vetoed


def report(label, rs, signals, vetoed):
    if not rs:
        print(f"{label:34s} signals={signals:5d} vetoed={vetoed:5d} trades=0")
        return
    wins = [r for r in rs if r > 0]
    gross_w = sum(wins); gross_l = -sum(r for r in rs if r <= 0)
    pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = min(dd, eq - peak)
    print(f"{label:34s} signals={signals:5d} vetoed={vetoed:5d} trades={len(rs):4d} "
          f"win={len(wins)/len(rs)*100:5.1f}% meanR={sum(rs)/len(rs):+.3f} "
          f"totalR={sum(rs):+7.1f} PF={pf:4.2f} maxDD={dd:6.1f}R")


if __name__ == "__main__":
    step = int(os.getenv("BT_STEP", "4"))
    symbols = (os.getenv("BT_SYMBOLS") or "EURUSD,GBPUSD,USDJPY,XAUUSD").split(",")
    configs = [
        ("1 strategy, NO brains", ["TrendFollowing"], False),
        ("1 strategy, WITH brains", ["TrendFollowing"], True),
        ("3 strategies, WITH brains", ["TrendFollowing", "RSIMeanReversion", "DonchianBreakout"], True),
    ]
    totals = {label: ([], 0, 0) for label, _, _ in configs}
    for sym in symbols:
        path = os.path.join(DATA_DIR, f"{sym}_M15.csv")
        if not os.path.exists(path):
            print(f"skip {sym}: no data"); continue
        candles = load(path, sym)
        print(f"\n=== {sym} ({len(candles)} bars, step={step}) ===")
        for label, strats, brain in configs:
            rs, s, v = run(sym, candles, strats, brain, step)
            report(label, rs, s, v)
            a, b, c = totals[label]
            totals[label] = (a + rs, b + s, c + v)
    print("\n=== ALL SYMBOLS COMBINED ===")
    for label, _, _ in configs:
        rs, s, v = totals[label]
        report(label, rs, s, v)
