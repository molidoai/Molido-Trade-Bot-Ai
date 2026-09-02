"""Is the engine looking at current prices, and is the bar cutoff sane?

The most damaging bug in this project was invisible for its whole life: MT5
stamps candles in broker-local time, the Candle carries no timezone, so
closed_bars() compared them against real UTC and discarded every bar of the
last three hours. Signals were computed on three-hour-old prices and nothing
reported a problem.

Two things are worth measuring, and only one of them is a fault:

* The gap between the live tick and the last bar's close. On a live feed this
  is a fraction of a percent. A large gap on *every* symbol means the candle
  feed has stopped; on one symbol it usually means that instrument is quiet or
  out of session, which is not a fault.

* The broker's clock offset. This is a constant (UTC+3 here) and is NOT
  staleness -- an earlier version of this check read the sign as "the feed is
  11 hours behind" and cried wolf on a perfectly healthy feed, moments after a
  restart. What matters is that the offset is stable and that closed_bars is
  therefore dropping about one bar, not dozens.
"""
import os, json, asyncio, statistics
from datetime import datetime, timezone
from molido_broker import create_broker, BrokerType
from molido_shared.types import TimeFrame
from molido_shared.point_in_time import bar_close_time, closed_bars

rt = json.load(open('/app/data/runtime-settings.json'))

# One quiet instrument is normal; a stale feed hits everything at once.
GAP_FAIL_PCT = 0.20        # per-symbol gap that counts as suspicious
MAJORITY = 0.5             # fraction of symbols that must be suspicious to fail
MAX_DROPPED = 3            # closed_bars should shed the forming bar, not a session


async def go():
    b = create_broker(
        BrokerType.MT5, login=int(rt['mt5_login']), password=rt['mt5_password'],
        server=rt['mt5_server'],
        rpc_host=os.getenv('MT5_RPC_HOST', 'host.docker.internal'), rpc_port=8001,
    )
    await b.connect()
    symbols = [x.strip() for x in (rt.get('symbols') or 'EURUSD').split(',') if x.strip()]
    now = datetime.now(timezone.utc)

    gaps, offsets, worst_drop, checked = [], [], 0, 0
    for s in symbols:
        try:
            tick = await b.get_tick(s)
            bars = await b.get_candles(s, TimeFrame.M15, count=60)
        except Exception:
            print("  WARN %s: no data" % s)
            continue
        if not tick or not bars or not tick.mid:
            print("  WARN %s: empty response" % s)
            continue
        checked += 1
        gap_pct = abs(tick.mid - float(bars[-1].close)) / tick.mid * 100
        gaps.append((gap_pct, s))
        ct = bar_close_time(bars[-1])
        ct = ct if ct.tzinfo else ct.replace(tzinfo=timezone.utc)
        offsets.append((ct - now).total_seconds() / 3600)
        # What the strategies actually get, judged on the broker's own clock.
        kept = closed_bars(bars, as_of=now + (ct - now), min_bars=5)
        worst_drop = max(worst_drop, len(bars) - len(kept))

    if not checked:
        print("  FAIL no symbol returned usable data")
        raise SystemExit(1)

    off = statistics.median(offsets)
    spread = max(offsets) - min(offsets)
    suspicious = [(g, s) for g, s in gaps if g > GAP_FAIL_PCT]
    worst = max(gaps)

    print("  %d symbols checked | worst tick-vs-close gap %.4f%% (%s)"
          % (checked, worst[0], worst[1]))
    print("  broker clock %+.2fh vs UTC (spread across symbols %.2fh)" % (off, spread))
    print("  closed_bars drops at most %d of 60 bars" % worst_drop)

    fails = 0
    if len(suspicious) > checked * MAJORITY:
        print("  FAIL %d of %d symbols are stale -- the candle feed has stopped"
              % (len(suspicious), checked))
        fails += 1
    elif suspicious:
        print("  WARN %s quiet or out of session (not a fault on its own)"
              % ", ".join(s for _, s in suspicious))
    if worst_drop > MAX_DROPPED:
        print("  FAIL closed_bars discards %d bars -- clock handling is wrong again"
              % worst_drop)
        fails += 1
    if spread > 1.0:
        print("  FAIL symbols disagree about the broker clock by %.2fh" % spread)
        fails += 1
    if not fails:
        print("  OK   feed current, clock consistent, bar cutoff sane")
    raise SystemExit(fails)

asyncio.run(go())
