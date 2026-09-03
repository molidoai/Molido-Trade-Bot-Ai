"""Score the live configuration from a fixed starting point.

The account's lifetime record mixes configurations: strategies that have since
been switched off, symbols that have since been closed, and a day when every
order was refused by the terminal. Quoting that total against a new setup
measures the history, not the setup.

`--mark` writes the starting point -- time, equity, and the exact
symbol/strategy map in force -- and everything reported afterwards is closed
trades whose entry falls after it. If the map changes, the mark is stale and
the report says so rather than silently scoring two configurations as one.

Deliberately reports per symbol and never pools. Pooled profit factor across
instruments of different point value hides exactly the case that matters:
one symbol carrying the total while the rest lose. A metal and a JPY pair do
not contribute dollars of the same size.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

DATA = os.getenv("MOLIDO_DATA_DIR", "/app/data")
BASELINE = os.path.join(DATA, "forward-baseline.json")
SETTINGS = os.path.join(DATA, "runtime-settings.json")


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _status():
    for name in ("portfolio-status-default.json", "portfolio-status.json"):
        d = _read(os.path.join(DATA, name))
        if d:
            return d
    return {}


def _map_now():
    return (_read(SETTINGS) or {}).get("symbol_strategies") or {}


def mark(note: str) -> None:
    st = _status()
    payload = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "equity": st.get("equity"),
        "balance": st.get("balance"),
        "symbol_strategies": _map_now(),
        "note": note,
    }
    with open(BASELINE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("baseline written to %s" % BASELINE)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def closes_since(ts: str):
    out = []
    for name in sorted(os.listdir(DATA)):
        if not (name.startswith("journal") and name.endswith(".jsonl")):
            continue
        with open(os.path.join(DATA, name), encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("event") != "close":
                    continue
                if r.get("ts", "") <= ts:
                    continue
                out.append(r)
    return out


def report() -> int:
    base = _read(BASELINE)
    if not base:
        print("No baseline yet. Run with --mark first.")
        return 1
    print("Forward record since %s" % base["started_at"])
    if base.get("note"):
        print("  note: %s" % base["note"])
    print("  starting equity: %s" % base.get("equity"))

    now_map = _map_now()
    if now_map != (base.get("symbol_strategies") or {}):
        print("\n  ** the symbol/strategy map changed since this baseline. **")
        print("  The rows below therefore mix two configurations; re-mark to")
        print("  start a clean record.")
        print("  baseline: %s" % json.dumps(base.get("symbol_strategies"), ensure_ascii=False))
        print("  now     : %s" % json.dumps(now_map, ensure_ascii=False))

    rows = closes_since(base["started_at"])
    if not rows:
        print("\n  No closed trades yet since the baseline.")
        st = _status()
        print("  equity now: %s | open positions: %s" % (st.get("equity"), st.get("open_positions")))
        return 0

    per: dict[str, list] = {}
    for r in rows:
        per.setdefault(str(r.get("symbol")), []).append(r)

    print("\n  %-8s %5s %7s %8s %9s %8s" % ("symbol", "n", "wins", "PF", "net$", "sum R"))
    for sym in sorted(per):
        rs = per[sym]
        profits = [float(r.get("profit") or 0) for r in rs]
        gp = sum(p for p in profits if p > 0)
        gl = -sum(p for p in profits if p < 0)
        pf = (gp / gl) if gl else float("inf")
        sr = sum(float(r.get("r_multiple") or 0) for r in rs)
        wins = sum(1 for p in profits if p > 0)
        strat = ",".join(now_map.get(sym) or []) or "-"
        print("  %-8s %5d %7d %8s %+9.2f %+8.2f   %s" % (
            sym, len(rs), wins, ("inf" if gl == 0 else "%.2f" % pf), sum(profits), sr, strat))

    print("\n  Sum of R is the only figure worth adding across symbols here:")
    print("  each trade risked the same fraction of the account, so an R is")
    print("  the same size everywhere, and a dollar is not.")
    st = _status()
    print("  equity now: %s | open positions: %s" % (st.get("equity"), st.get("open_positions")))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", action="store_true", help="set the starting point to now")
    ap.add_argument("--note", default="", help="why this baseline was set")
    a = ap.parse_args()
    if a.mark:
        mark(a.note)
    else:
        raise SystemExit(report())
