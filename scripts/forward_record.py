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


def _accounts():
    """Every account with a status snapshot, as {account_id: snapshot}.

    One terminal serves one account, so a prop challenge alongside the demo
    means two of everything: two status files, two journals, two records. A
    reader that takes the first file it finds reports one account and gives no
    sign the other exists -- which is worse than reporting nothing, because
    the number looks complete.
    """
    out = {}
    for name in sorted(os.listdir(DATA)):
        if not (name.startswith("portfolio-status") and name.endswith(".json")):
            continue
        d = _read(os.path.join(DATA, name))
        if not d:
            continue
        acc = str(d.get("account_id") or "default")
        out.setdefault(acc, d)
    return out


def _status(account_id="default"):
    return _accounts().get(account_id, {})


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


def _account_of(journal_name: str) -> str:
    """journal-<account>.jsonl -> <account>; the unsuffixed file is account 1."""
    stem = journal_name[len("journal"):-len(".jsonl")]
    return stem.lstrip("-") or "default"


def closes_since(ts: str, account_id: str | None = None):
    out = []
    for name in sorted(os.listdir(DATA)):
        if not (name.startswith("journal") and name.endswith(".jsonl")):
            continue
        if account_id is not None and _account_of(name) != account_id:
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


def _account_block(acc_id: str, snap: dict, base: dict, now_map: dict) -> None:
    label = snap.get("account_name") or acc_id
    mode = snap.get("account_mode") or "?"
    print("\n  === %s (%s)" % (label, mode))

    rows = closes_since(base["started_at"], acc_id)
    if not rows:
        print("     no closed trades yet since the baseline")
    else:
        per: dict[str, list] = {}
        for r in rows:
            per.setdefault(str(r.get("symbol")), []).append(r)
        print("     %-8s %5s %6s %8s %10s %8s   %s" % (
            "symbol", "n", "wins", "PF", "net$", "sum R", "strategy"))
        total_r = 0.0
        for sym in sorted(per):
            rs = per[sym]
            profits = [float(x.get("profit") or 0) for x in rs]
            gp = sum(v for v in profits if v > 0)
            gl = -sum(v for v in profits if v < 0)
            sr = sum(float(x.get("r_multiple") or 0) for x in rs)
            total_r += sr
            wins = sum(1 for v in profits if v > 0)
            strat = ",".join(now_map.get(sym) or []) or "-"
            print("     %-8s %5d %6d %8s %+10.2f %+8.2f   %s" % (
                sym, len(rs), wins,
                "inf" if gl == 0 else "%.2f" % (gp / gl),
                sum(profits), sr, strat))
        print("     %-8s %5d %6s %8s %10s %+8.2f" % (
            "TOTAL", sum(len(v) for v in per.values()), "", "", "", total_r))

    eq = snap.get("equity")
    print("     equity %s | open %s" % (eq, snap.get("open_positions")))

    # A prop account is judged against a floor that does not move. Showing the
    # distance to it is the only number that says how much room is left; equity
    # alone does not, and by the time it matters it is too late to ask.
    floor_base = float(snap.get("prop_initial_balance") or 0)
    if floor_base > 0:
        pct = float(snap.get("prop_max_loss_pct") or 0.10)
        floor = floor_base * (1.0 - pct)
        try:
            room = float(eq) - floor
            print("     prop floor %.2f -- %.2f of room left (%.1f%% of the allowance)"
                  % (floor, room, 100.0 * room / (floor_base * pct)))
        except (TypeError, ValueError):
            print("     prop floor %.2f (equity unreadable)" % floor)


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

    accounts = _accounts() or {"default": {}}
    for acc_id in sorted(accounts):
        _account_block(acc_id, accounts[acc_id], base, now_map)

    print("\n  Sum of R is the only figure worth adding, and only within an")
    print("  account: every trade risks the same fraction of that account, so")
    print("  an R is the same size on gold and on EURUSD, and a dollar is not.")
    print("  Accounts are never combined -- they have different balances and,")
    print("  for a prop challenge, a different thing at stake.")
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
