# Production Hardening – Molido Trade Bot AI

> This software does **not** guarantee profits. Trading involves substantial risk of loss.

## 1. Pre-flight checklist (before any DEMO broker connection)

- [ ] `.env` created from `.env.example` with strong `SECRET_KEY` (≥32 chars)
- [ ] `ENGINE_INTERNAL_TOKEN` set (≥16 chars) — required for trading-engine to authenticate `POST /ops/heartbeat`; API refuses to start without it
- [ ] `TRADING_ACCOUNT_MODE=DEMO` (never start on REAL)
- [ ] `MASTER_BOT_ENABLED=false` until manual enable
- [ ] No secrets in git (`git status` clean of `.env`)
- [ ] `check_env_safety()` reports `ok=True` — enforced automatically: the API now runs this at startup and refuses to boot in production if it fails
- [ ] Docker resource limits fit VPS RAM (target ≤10GB total)
- [x] PostgreSQL backup cron configured — see §6 below
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
- [ ] 2-step confirmation path for mode switch verified: `POST /ops/mode {mode:"REAL"}` is rejected without `confirm_token=CONFIRM_REAL`, and going live is two separate authenticated calls (`/ops/mode` then `/ops/master`, or `/ops/live` with the same token) — never automatic
- [x] Disaster recovery restore tested once — see §6

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

## 6. Backup and restore

Two independent backups, both cron'd on the VPS, both under `/opt/molido/backups/`
(mode 700 dir, mode 600 files):

| What | Script | Schedule | Retention |
|------|--------|----------|-----------|
| `runtime-settings.json` (mode, MT5 login, risk limits — no secrets in git, never a DB) | `/opt/molido/backup-runtime.sh` | `15 3 * * *` | 7 days |
| Postgres (`molido_trading`: users, positions, orders, trades, signals, ...) | `/opt/molido/backup-postgres.sh` (repo copy: `scripts/backup_postgres.sh`) | `30 3 * * *` | 14 days |

The Postgres backup is a plain `pg_dump \| gzip`, verified restorable (2026-08-30:
restored into a scratch `restore_test` database, all 11 tables + row counts
checked, then dropped). To restore for real:

```bash
# on the VPS, as root
zcat /opt/molido/backups/postgres-<timestamp>.sql.gz | \
  docker exec -i molido-postgres psql -U molido -d molido_trading
```

Restoring into the live `molido_trading` database while the API/engine are
running will conflict with in-flight writes — stop `api` and `trading-engine`
first (`docker compose stop api trading-engine`), restore, then
`docker compose up -d api trading-engine`. For a partial/point-in-time
restore, restore into a scratch database first (as tested above) and copy
out only what's needed, rather than restoring straight over production.
