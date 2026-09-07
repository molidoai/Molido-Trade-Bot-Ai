#!/bin/bash
# Ship the engine source and rebuild.
#
# Written after shipping a hand-picked list of changed files and missing one:
# runner.py went up expecting TradeManager(journal=...), trade_manager.py did
# not, and the live runner died with a TypeError the moment the new image
# started. The container still reported "running" -- only the log said the bot
# was dead -- so nothing external would have looked wrong for three minutes.
#
# The fix is to stop choosing. Every tracked Python file under apps/ and
# packages/ goes, so a signature change and its caller cannot be separated.
set -euo pipefail

HOST="${MOLIDO_HOST:-root@198.144.189.80}"
KEY="${MOLIDO_KEY:-$HOME/.ssh/molido_claude_deploy}"
SSH="ssh -i $KEY -o ConnectTimeout=30 -o BatchMode=yes"

command -v git >/dev/null || { echo "git required" >&2; exit 1; }
cd "$(git rev-parse --show-toplevel)"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "WARNING: working tree is dirty -- shipping what is on disk, not HEAD" >&2
fi

echo "==> collecting tracked sources"
FILES=$(git ls-files 'apps/**/*.py' 'packages/**/*.py')
COUNT=$(echo "$FILES" | wc -l)
echo "    $COUNT files"

echo "==> shipping"
# One tar over one connection: far fewer round trips than per-file scp, and
# atomic enough that a dropped link fails loudly instead of leaving a
# half-updated tree that builds into a broken image.
tar czf - $FILES | $SSH "$HOST" 'tar xzf - -C /opt/molido'

echo "==> verifying every file matches"
# One connection, not one per file. Opening 128 back-to-back sessions trips
# sshd's MaxStartups and the drops are reported as MISMATCH, so a perfectly
# good upload fails the check for a reason that has nothing to do with the
# files -- which is exactly what happened on the first run of this fix.
# Compare a single manifest instead: local checksums in, remote result out.
MANIFEST=$(md5sum $FILES)
REMOTE=$(printf '%s
' "$MANIFEST" | $SSH "$HOST" "cd /opt/molido && md5sum -c --quiet - 2>&1" || true)
if [ -n "$REMOTE" ]; then
  echo "$REMOTE" | sed 's/^/    /'
  echo "file(s) did not land; not rebuilding" >&2
  exit 1
fi
echo "    all $COUNT match"

echo "==> rebuilding (CPU-capped)"
$SSH "$HOST" 'systemd-run --unit=molido-rebuild --collect /bin/bash -c "/opt/molido/build.sh trading-engine > /root/rebuild.log 2>&1"'
$SSH "$HOST" 'while systemctl is-active --quiet molido-rebuild; do sleep 15; done; tail -2 /root/rebuild.log'

echo "==> confirming the runner is alive, not merely the container"
sleep 25
$SSH "$HOST" '
  st=$(docker inspect -f "{{.State.Status}}" molido-engine)
  echo "container: $st"
  if docker logs molido-engine --since 60s 2>&1 | grep -qiE "Traceback|TypeError|LIVE runner stopped"; then
    echo "ENGINE IS BROKEN -- the container runs but the runner died:"
    docker logs molido-engine --tail 15 2>&1 | tail -15
    exit 1
  fi
  docker logs molido-engine --since 60s 2>&1 | grep -qE "session skip|evaluating|Reconciled" \
    && echo "runner is cycling: OK" \
    || { echo "no cycle lines in 60s -- check manually"; exit 1; }
'
echo "==> deployed"
