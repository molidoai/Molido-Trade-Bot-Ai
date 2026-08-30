#!/bin/bash
# Daily pg_dump of the Molido trading database (positions, users, trade
# history) — scripts/backup_runtime_settings.sh only covers runtime-settings.json,
# not the database itself.
#
# Deployed on the production VPS as /opt/molido/backup-postgres.sh (root-level,
# hyphenated, matching that host's existing backup-runtime.sh / heartbeat.sh
# convention rather than this repo's scripts/ layout), scheduled via cron:
#   30 3 * * * /opt/molido/backup-postgres.sh
set -euo pipefail
umask 077
mkdir -p /opt/molido/backups
chmod 700 /opt/molido/backups

PG_USER=molido
PG_DB=molido_trading

dst=/opt/molido/backups/postgres-$(date +%Y%m%d-%H%M%S).sql.gz
tmp="${dst}.tmp"

if ! docker exec molido-postgres pg_dump -U "$PG_USER" -d "$PG_DB" | gzip > "$tmp"; then
  rm -f "$tmp"
  logger -t molido-backup "postgres backup FAILED (pg_dump/gzip error)"
  exit 1
fi

if [ ! -s "$tmp" ]; then
  rm -f "$tmp"
  logger -t molido-backup "postgres backup FAILED (empty dump)"
  exit 1
fi

mv "$tmp" "$dst"
chmod 600 "$dst"
find /opt/molido/backups -type f -name 'postgres-*.sql.gz' -mtime +14 -delete
logger -t molido-backup "backed up postgres ($(du -h "$dst" | cut -f1))"
echo "$dst"
