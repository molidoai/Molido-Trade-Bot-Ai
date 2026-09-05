#!/bin/bash
# Deliver study results to Telegram when they finish, so nobody has to SSH in
# to learn the answer. Same token source as the watchdog -- one place to rotate.
set -u
S=/var/lib/docker/volumes/molido_runtime_data/_data/runtime-settings.json

send () {
  local msg="$1" tok chat
  [ -r "$S" ] || return 0
  tok=$(python3 -c "import json;print(json.load(open('$S')).get('telegram_bot_token') or '')" 2>/dev/null)
  chat=$(python3 -c "import json;d=json.load(open('$S'));c=d.get('telegram_admin_chat_id') or (d.get('telegram_allowed_chat_ids') or '').split(',')[0];print(str(c or '').strip())" 2>/dev/null)
  [ -n "$tok" ] && [ -n "$chat" ] || return 0
  curl -s --max-time 20 -o /dev/null \
    -d "chat_id=$chat" --data-urlencode "text=$msg" \
    "https://api.telegram.org/bot$tok/sendMessage"
}

watch_one () {   # unit logfile title
  local unit="$1" log="$2" title="$3"
  while systemctl is-active --quiet "$unit"; do sleep 120; done
  local body
  body=$(grep -E '^  |^####|^====' "$log" 2>/dev/null | tail -40)
  [ -n "$body" ] || body="(no result lines found in $log)"
  send "$title
$(date '+%Y-%m-%d %H:%M')

$body

PF above 1.0 and more than half the folds profitable is the bar. Anything
below that is a refusal, not a near miss."
}

watch_one molido-v2  /root/v2b.log "StrengthReversion v2 -- final row"
watch_one molido-m15 /root/m15.log "M15 validation sweep -- what the bot actually trades"
send "Both studies are finished. Nothing else is queued."
