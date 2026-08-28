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
