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
  # Evidence of life first, and it is decisive. Looking for scary words was
  # not: "LIVE runner stopped" is logged by the OLD runner on every ordinary
  # restart, so this reported a perfectly healthy deploy as a dead engine.
  # A heartbeat in the last 60s means the loop is running now, whatever
  # appeared in the log while it was coming up.
  if docker logs molido-engine --since 60s 2>&1 | grep -qE "equity=|session skip|Reconciled"; then
    echo "runner is cycling: OK"
    # A crash being retried still cycles, so surface it without failing the
    # deploy -- one account can be down while another trades.
    if docker logs molido-engine --since 60s 2>&1 | grep -qiE "Traceback|runner crashed"; then
      echo "note: an account is erroring while others cycle --"
      docker logs molido-engine --since 60s 2>&1 | grep -iE "Traceback|runner crashed|MT5 connect failed" | tail -3
    fi
  else
    echo "ENGINE IS BROKEN -- no heartbeat in 60s:"
    docker logs molido-engine --tail 20 2>&1 | tail -20
    exit 1
  fi
'
echo "==> deployed"
