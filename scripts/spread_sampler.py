"""Sample a symbol's real spread across a full trading day.

A single reading is worthless for comparing brokers. Spread on XAUUSD moves by
several multiples between the Asian session and the London/NY overlap, and it
blows out around the Sunday open and daily rollover -- the 0.42 measured on a
Sunday evening is not the number the bot will actually pay. What decides
whether an edge survives is the spread during the hours it trades, so that is
what this measures.

Reports the median (what you normally pay), the 90th percentile (what you pay
when it matters), and a per-session breakdown. Median rather than mean because
rollover spikes are real but rare, and a mean lets them dominate a figure that
is supposed to describe the typical bar.

Usage inside the engine container:
    MT5_BRIDGE_HOST=172.18.0.1 SYMBOL=XAUUSD MINUTES=1440 python3 spread_sampler.py
"""
import os, sys, time, json
from datetime import datetime, timezone

import rpyc

HOST = os.getenv("MT5_BRIDGE_HOST", "172.18.0.1")
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
MINUTES = int(os.getenv("MINUTES", "1440"))
EVERY = int(os.getenv("EVERY_SEC", "60"))
OUT = os.getenv("OUT", "/app/data/spread-%s.jsonl" % SYMBOL)


def session(hour_utc: int) -> str:
    # Rough but standard: what matters is separating the cheap hours from the
    # expensive ones, not exchange-precise boundaries.
    if 0 <= hour_utc < 7:   return "asia"
    if 7 <= hour_utc < 12:  return "london"
    if 12 <= hour_utc < 17: return "overlap"
    if 17 <= hour_utc < 21: return "ny"
    return "late"


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[i]


def main() -> int:
    try:
        c = rpyc.classic.connect(HOST, 8001)
    except Exception as e:
        print("BRIDGE UNREACHABLE via %s: %s" % (HOST, e))
        return 1
    mt5 = c.modules["MetaTrader5"]
    ai = mt5.account_info()
    broker = getattr(ai, "server", "?")
    c.execute("import MetaTrader5 as _m")
    c.execute("_m.symbol_select(%r, True)" % SYMBOL)
    si = mt5.symbol_info(SYMBOL)
    if si is None:
        print("symbol %s not available on %s" % (SYMBOL, broker))
        return 1
    point = float(getattr(si, "point", 0.01) or 0.01)
    print("broker=%s symbol=%s point=%s sampling %d min every %ds"
          % (broker, SYMBOL, point, MINUTES, EVERY))

    rows = []
    end = time.time() + MINUTES * 60
    fh = open(OUT, "a", encoding="utf-8")
    while time.time() < end:
        try:
            t = mt5.symbol_info_tick(SYMBOL)
            if t and t.ask and t.bid:
                now = datetime.now(timezone.utc)
                # Measured from the live quote, not symbol_info.spread: the
                # latter is the broker's advertised figure and can lag what is
                # actually quoted.
                spread_price = float(t.ask) - float(t.bid)
                rec = {"ts": now.isoformat(), "broker": broker,
                       "symbol": SYMBOL, "spread_price": round(spread_price, 6),
                       "spread_points": round(spread_price / point, 1),
                       "session": session(now.hour), "bid": t.bid, "ask": t.ask}
                rows.append(rec)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
        except Exception as e:
            print("sample failed (continuing): %s" % e)
        time.sleep(EVERY)
    fh.close()

    if not rows:
        print("no samples collected")
        return 1
    allv = [r["spread_price"] for r in rows]
    print()
    print("=== %s on %s -- %d samples ===" % (SYMBOL, broker, len(rows)))
    print("median   %.3f" % pct(allv, 50))
    print("p90      %.3f" % pct(allv, 90))
    print("worst    %.3f" % max(allv))
    print()
    for s in ("asia", "london", "overlap", "ny", "late"):
        v = [r["spread_price"] for r in rows if r["session"] == s]
        if v:
            print("  %-8s n=%4d  median %.3f  p90 %.3f" % (s, len(v), pct(v, 50), pct(v, 90)))
    print()
    print("For comparison: the registry modelled XAUUSD at 0.25 and the broker")
    print("quoted 0.29 when that edge was validated. The edge survives on a")
    print("cost-to-gross ratio of 4.5%, so a median far above 0.29 erases it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
