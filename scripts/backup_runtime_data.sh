#!/bin/bash
# Back up the runtime_data volume -- the trade journal, brain decision log,
# portfolio snapshots and runtime settings.
#
# This matters more than the Postgres dump: the schema has trades/orders/
# positions/signals tables but the engine never writes to them (verified
# 2026-09-01: all four were empty at 0 rows while the journal held 5,524
# entries). All real trading history lives in these JSONL/JSON files inside
# the Docker volume, so without this the history -- and the expectancy
# figures brain 3 derives from it -- would be lost with the volume.
set -euo pipefail
umask 077
mkdir -p /opt/molido/backups
chmod 700 /opt/molido/backups

dst=/opt/molido/backups/runtime-data-$(date +%Y%m%d-%H%M%S).tar.gz
tmp="${dst}.tmp"

if ! docker run --rm -v molido_runtime_data:/data:ro -v /opt/molido/backups:/out alpine \
      tar czf "/out/$(basename "$tmp")" -C /data . 2>/dev/null; then
  rm -f "$tmp"
  logger -t molido-backup "runtime-data backup FAILED"
  exit 1
fi
[ -s "$tmp" ] || { rm -f "$tmp"; logger -t molido-backup "runtime-data backup EMPTY"; exit 1; }

mv "$tmp" "$dst"
chmod 600 "$dst"
find /opt/molido/backups -type f -name 'runtime-data-*.tar.gz' -mtime +14 -delete
logger -t molido-backup "backed up runtime data ($(du -h "$dst" | cut -f1))"
echo "$dst"
