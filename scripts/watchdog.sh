#!/bin/bash
# Repair the three failures that took this bot down on 2026-09-02/03 and each
# time needed a human to notice and fix.
#
# Each check here exists because the failure actually happened, was diagnosed,
# and had a known repair. Nothing speculative is automated: a watchdog that
# guesses does more damage than one that waits.
#
#   1. MT5 chain broken   engine crash-loops on "stream has been closed" while
#                         mt5.service and the bridge both report active. The
#                         cause is that stopping mt5.service also stops
#                         mt5linux.service through a dependency, and starting
#                         mt5.service does NOT bring it back. Nothing listens
#                         on 8001 and every cycle skips new entries.
#
#   2. Disk full          docker build cache reached 100% of the root volume.
#                         sshd and nginx both need to write per connection, so
#                         both stopped answering while the kernel still
#                         accepted TCP -- indistinguishable from a hang, and it
#                         survives a reboot. Three reboots were spent on it.
#
#   3. Engine not cycling  the container is up and healthy-looking but the run
#                         loop has stopped. Only the log says so.
#
# Runs from cron. Repairs are idempotent and rate-limited by a state file, so a
# genuinely broken host is not restarted in a loop -- after MAX_REPAIRS in a
# row it stops trying and only alerts, because past that point a human needs to
# look rather than another restart.
set -u

STATE=/var/lib/molido-watchdog
mkdir -p "$STATE"
MAX_REPAIRS=3
LOG=/var/log/molido-watchdog.log

log () { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }

notify () {
  # Best effort. The bot's own Telegram settings are the single source of the
  # token, so nothing is duplicated here and rotating it in one place is enough.
  local msg="$1"
  local S=/var/lib/docker/volumes/molido_runtime_data/_data/runtime-settings.json
  [ -r "$S" ] || return 0
  local tok chat
  tok=$(python3 -c "import json;print(json.load(open('$S')).get('telegram_bot_token') or '')" 2>/dev/null)
  chat=$(python3 -c "import json;d=json.load(open('$S'));c=d.get('telegram_admin_chat_id') or (d.get('telegram_allowed_chat_ids') or '').split(',')[0];print(str(c or '').strip())" 2>/dev/null)
  [ -n "$tok" ] && [ -n "$chat" ] || return 0
  curl -s --max-time 15 -o /dev/null \
    -d "chat_id=$chat" --data-urlencode "text=$msg" \
    "https://api.telegram.org/bot$tok/sendMessage" || true
}

# Count consecutive repairs of one kind; refuse past the cap.
may_repair () {
  # Declared one per line on purpose: in a single `local a=.. b=$a` statement
  # bash expands every value before any of them is in scope, so under `set -u`
  # the second one aborts the script with "key: unbound variable" -- which is
  # how the first live repair attempt died after correctly detecting the fault.
  local key="$1"
  local f="$STATE/$key.count"
  local n=0
  [ -f "$f" ] && n=$(cat "$f" 2>/dev/null || echo 0)
  [ "$n" -ge "$MAX_REPAIRS" ] && return 1
  echo $((n + 1)) > "$f"
  return 0
}
clear_repairs () { rm -f "$STATE/$1.count" 2>/dev/null || true; }

# --- 1. disk ---------------------------------------------------------------
USE=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "${USE:-0}" -ge 90 ]; then
  log "disk at ${USE}% -- pruning build cache"
  BEFORE=$(df --output=avail / | tail -1)
  docker builder prune -af >/dev/null 2>&1 || true
  docker image prune -f  >/dev/null 2>&1 || true
  AFTER=$(df --output=avail / | tail -1)
  NOW=$(df --output=pcent / | tail -1 | tr -dc '0-9')
  log "disk ${USE}% -> ${NOW}% (freed $(( (AFTER-BEFORE)/1024 )) MB)"
  if [ "${NOW:-100}" -ge 90 ]; then
    notify "⚠️ Molido: disk still ${NOW}% after pruning docker. Needs a look — when root fills, sshd and nginx stop answering."
  fi
fi

# NOTE: the check is for 127.0.0.1:8001, not any :8001. The socat bridge binds
# the docker-bridge addresses and keeps those listeners open whether or not the
# RPyC server behind them is alive. A bare :8001 match therefore reported
# healthy straight through the outage this exists to catch -- proven by stopping
# mt5linux and watching the check pass with the service dead.
# --- 2. MT5 chain ----------------------------------------------------------
# The port is the fact; the unit states are not. Both reported active while
# nothing was listening.
# `is-enabled` first, because a disabled terminal is a decision, not a fault.
# Running two accounts means switching one off so the other can hold the MT5
# API port, and without this guard the watchdog restarted the account that was
# deliberately stopped -- every three minutes, silently undoing the change
# while its log called it a repair. It took an hour to notice the fight.
if systemctl is-enabled mt5.service >/dev/null 2>&1    && ! ss -lnt 2>/dev/null | grep -q '127\.0\.0\.1:8001 '; then
  log "8001 not listening -- MT5 chain is down"
  if may_repair mt5; then
    systemctl start mt5.service      >/dev/null 2>&1 || true
    sleep 5
    systemctl start mt5linux.service >/dev/null 2>&1 || true
    sleep 20
    if ss -lnt 2>/dev/null | grep -q '127\.0\.0\.1:8001 '; then
      log "8001 restored; restarting the engine to drop its stale connection"
      # The engine holds a dead RPyC stream and will not reconnect on its own.
      docker compose -f /opt/molido/docker-compose.yml restart trading-engine >/dev/null 2>&1 || true
      notify "🔧 Molido: MT5 bridge was down (port 8001 silent). Restarted mt5linux and the engine. Trading resumes automatically."
      clear_repairs mt5
    else
      log "8001 still silent after repair attempt"
      notify "⚠️ Molido: MT5 bridge did not come back after a restart. The engine cannot trade until this is fixed."
    fi
  else
    log "mt5 repair cap reached; not retrying"
  fi
else
  clear_repairs mt5
fi

# --- 3. engine actually cycling -------------------------------------------
# "Up" is not the same as "working": the container stayed up for an hour while
# every cycle aborted on a dead broker connection.
if docker ps --filter name=molido-engine --filter status=running -q | grep -q .; then
  CYCLES=$(docker logs --since 5m molido-engine 2>&1 | grep -cE 'equity=|session skip' || true)
  if [ "${CYCLES:-0}" -eq 0 ]; then
    log "engine produced no cycle lines in 5 minutes"
    if may_repair engine; then
      docker compose -f /opt/molido/docker-compose.yml restart trading-engine >/dev/null 2>&1 || true
      notify "🔧 Molido: the engine stopped cycling and was restarted."
    else
      notify "⚠️ Molido: the engine is not cycling and restarting has not helped. Needs a look."
    fi
  else
    clear_repairs engine
  fi
fi

exit 0
