# Operator Incident Runbook (Master Prompt §27.1.28)

## Circuit Breaker open

1. Check `/api/v1/system/status` and Telegram alerts
2. Verify equity, daily PnL, open positions on broker terminal
3. Do **not** reset circuit until cause known (daily loss vs data vs broker)
4. If data stale: fix market data / restart MD engine, then `reconcile()`
5. If daily loss: no new entries until next day / policy reset
6. Resume only after written note of root cause

## Kill Switch level 3 (full stop)

1. Confirm Master OFF via Dashboard and Telegram
2. Reconcile positions with broker
3. Decide manually whether to close positions (not automatic)
4. Review audit log for who triggered stop
5. Restart services only after checklist in PRODUCTION_HARDENING.md

## Reconciliation mismatch

1. Trust **broker** as source of truth
2. Run Reconciler – local-only tickets are dropped; broker-only adopted
3. If repeated mismatches: stop entries, check for manual trades on terminal

## Data quality alerts repeating

1. Compare WebSocket vs REST if both enabled
2. Switch symbol feed or broker server if spikes are feed errors
3. Keep entries halted while critical anomalies fire

## Config drift

1. Diff running env vs last known-good `.env` / DB settings
2. Never hot-fix REAL credentials without audit
3. Restart API after config correction

---

# Running this without help (added 2026-09-04)

The system repairs itself for every failure that has actually happened so far.
This section says what runs on its own, what it will tell you, and the short
list of things it deliberately will not decide for you.

## What repairs itself

Four cron jobs on the production host. None of them guesses: every repair
exists because that exact failure happened, was diagnosed, and had a known fix.

| job | every | what it does |
|---|---|---|
| `watchdog.sh` | 3 min | prunes docker when the root disk passes 90%; restarts `mt5linux` + the engine when nothing listens on 8001; restarts the engine when it stops producing cycle lines |
| `algo-watch.sh` | 2 min | detects the terminal's algorithmic-trading flag being off, runs the GUI repair, and verifies by re-reading `trade_allowed` |
| `heartbeat.sh` | 2 min | alerts when the engine container is down but was meant to be up |
| `molido-web-watch.sh` | 1 min | restarts the frontend when `/login` stops answering |

Inside the engine, `LiveRunner._recover_broker` rebuilds the MT5 connection,
restarts the tick stream and reconciles whenever a cycle fails on a dead
bridge, so a terminal restart no longer needs anyone.

Repairs are capped. `watchdog.sh` stops after three consecutive attempts of the
same kind and `algo-watch.sh` after two, then alerts instead. Past that point
another restart is not more likely to work, and a person should look.

## What it tells you, unasked

* **Every fill and every close** — Telegram, from the engine.
* **A daily record** — Telegram, weekdays 21:30 local, after the New York
  close. Per symbol, never pooled, counted from a fixed starting point rather
  than account lifetime.
* **Every automatic repair**, and every repair that failed.

If Telegram goes quiet for a whole weekday, that is itself the signal: the
daily report is the only message guaranteed to arrive.

## Reading the daily report

```
symbol       n    wins       PF      net$    sum R
XAUUSD       7       3     1.31    +18.40    +1.12   TrendFollowing
```

`sum R` is the only figure to add across symbols. Every trade risks the same
fraction of the account, so an R is the same size on gold and on EURUSD, and a
dollar is not. Never read pooled `net$` across symbols — a metal or a JPY pair
will dominate it and hide a losing symbol. That mistake is exactly how a
five-symbol PF of 1.09 survived review on 2026-09-02 before breaking down to
four symbols under 1.0.

## Changing what it trades

`symbol_strategies` in `runtime-settings.json` maps a symbol to the strategies
allowed on it. The engine re-reads it every cycle — no restart, no rebuild.

```json
"symbol_strategies": {
  "XAUUSD": ["TrendFollowing"],
  "EURUSD": ["RSIMeanReversion"],
  "GBPUSD": []
}
```

An empty list closes a symbol. A symbol absent from the map runs every enabled
strategy.

**The one trap:** the map only ever *narrows*. Naming a strategy there does not
enable it — if it is missing from `strategy_names`, that symbol silently trades
nothing and no error is raised. This has caused a silent no-op twice. After any
change, confirm what the engine actually resolved:

```
docker compose exec -T trading-engine python3 -c "
import sys, json; sys.path.insert(0, '/app')
from molido_strategies.engine import StrategyEngine, parse_strategy_names, parse_symbol_strategies
d = json.load(open('/app/data/runtime-settings.json'))
se = StrategyEngine(); se.configure_live(parse_strategy_names(d.get('strategy_names')))
se.configure_symbol_map(parse_symbol_strategies(d.get('symbol_strategies')))
for s in d['symbols'].split(','): print(s, '->', se.allowed_for(s) or '(closed)')"
```

## Before adding a symbol or a strategy

Measure it. `scripts/walk_forward_report.py` runs the walk-forward; the bar was
fixed before any result was seen and is enforced in code by
`ProvenEdge.is_valid()`: at least 30 out-of-sample trades, PF above 1.0,
positive cost-adjusted expectancy, and profit in **more than** half the folds.

Of 53 measured symbol/strategy cells on 2026-09-03, two cleared it. Five had a
PF above 1.1 and four of those five failed the fold test — a high PF with few
profitable folds almost always means a handful of large winners, not an edge.
Do not move the bar to admit one of them. `GBPUSD/DonchianBreakout` is live as
an explicit operator override, recorded as such in `symbol_strategies_note`,
and is the first thing to close if its live record trails the other two.

## What it will not decide for you

* **Closing an open position.** Positions carry a stop and a target at the
  broker. Closing the map's symbols only stops new entries.
* **Going to a real account.** `trading_account_mode` stays `DEMO` until a
  person changes it. Two of the three live symbols are hypotheses from a single
  sweep, not established edges.
* **Loosening a filter to trade more often.** Fewer trades is what the evidence
  supports; the measurements say loosening costs money rather than making it.
