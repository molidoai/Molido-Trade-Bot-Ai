# Production Hardening – Molido Trade Bot AI

> This software does **not** guarantee profits. Trading involves substantial risk of loss.

## 1. Pre-flight checklist (before any DEMO broker connection)

- [ ] `.env` created from `.env.example` with strong `SECRET_KEY` (≥32 chars)
- [ ] `TRADING_ACCOUNT_MODE=DEMO` (never start on REAL)
- [ ] `MASTER_BOT_ENABLED=false` until manual enable
- [ ] No secrets in git (`git status` clean of `.env`)
- [ ] `check_env_safety()` reports `ok=True`
- [ ] Docker resource limits fit VPS RAM (target ≤10GB total)
- [ ] PostgreSQL backup cron configured
- [ ] HTTPS / reverse proxy ready (domain you already have)
- [ ] Telegram token restricted to admin chat IDs only

## 2. Before first DEMO order

- [ ] MT5 terminal reachable (Wine or Windows) if using real DEMO
- [ ] Broker adapter connects and `reconcile()` succeeds
- [ ] Market data not stale
- [ ] Risk Engine denies missing SL (unit test + manual)
- [ ] Kill Switch / Circuit Breaker path tested
- [ ] PaperRunner completed ≥1 clean cycle on Mock

## 3. Before Micro-Live (requires explicit human approval)

- [ ] All Acceptance Criteria in `docs/ACCEPTANCE_CRITERIA.md` reviewed
- [ ] Capital amount and max risk written down by operator
- [ ] PROP rules loaded if prop account
- [ ] 2-step confirmation path for mode switch verified
- [ ] Disaster recovery restore tested once

## 4. Forbidden in production

- Hardcoded passwords / tokens
- Auto-enable REAL or Master ON on deploy
- Bypassing Risk Engine from UI / Telegram / AI
- Running without Stop-Loss requirement
- Sharing Investor and Trading passwords broadly

## 5. Resource guidance (8 vCPU / 10GB VPS)

| Service    | CPU limit | RAM limit |
|------------|-----------|-----------|
| postgres   | 1.0       | 1G        |
| redis      | 0.5       | 300M      |
| api        | 1.0       | 512M      |
| trading-engine | 1.5   | 1G        |
| frontend   | 0.5       | 512M      |
| prometheus | 0.5       | 512M      |
| reserved OS | —        | ~2G       |

Backtest / Monte Carlo: run off-peak or with `nice` so Live engine is not starved.
