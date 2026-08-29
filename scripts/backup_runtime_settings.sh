#!/usr/bin/env bash
# Copy runtime-settings.json to a dated file (mode 600). Used on VPS later.
set -euo pipefail
SRC="${RUNTIME_SETTINGS_PATH:-/app/data/runtime-settings.json}"
DEST_DIR="${RUNTIME_BACKUP_DIR:-$(dirname "$SRC")/backups}"
mkdir -p "$DEST_DIR"
chmod 700 "$DEST_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEST_DIR/runtime-settings-${STAMP}.json"
if [[ ! -f "$SRC" ]]; then
  echo "missing $SRC" >&2
  exit 1
fi
cp -p "$SRC" "$DEST"
chmod 600 "$DEST"
echo "$DEST"
