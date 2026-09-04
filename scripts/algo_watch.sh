#!/bin/bash
# Watch the one flag the engine cannot see from its own logs.
#
# terminal_info().trade_allowed is GUI-only state in the MT5 terminal. When it
# is off, every order the engine sends comes back retcode 10027 "AutoTrading
# disabled by client" -- the engine keeps signalling, risk keeps approving,
# and nothing trades. On 2026-09-02 the box was hard-reset at 19:59 and the
# terminal came back with the flag off; nobody noticed until the next
# afternoon. This runs from cron every two minutes and posts a Telegram alert
# (at most one per 30 minutes) while the flag is off.
#
# One terminal serves one account, so a multi-account deployment runs several
# and each has its own flag. The port is discovered rather than hardcoded:
# checking only 8001 would leave a prop account on 8002 completely unwatched,
# which is the same blind spot this script exists to remove.
#
# PORT can be passed in to check a single bridge; with no argument every
# listening MT5 bridge is checked in turn.
#
# The query goes through the engine container because the host has no rpyc.
set -uo pipefail
cd /opt/molido || exit 0
[ -f /opt/molido/.engine_wanted ] || exit 0
docker inspect -f '{{.State.Running}}' molido-engine 2>/dev/null | grep -qx true || exit 0

probe () {  # $1 = port -> on | off | bridge-down | unknown
  docker compose exec -T trading-engine python3 - "$1" 2>/dev/null <<'EOF'
import sys
import rpyc
try:
    c = rpyc.classic.connect("host.docker.internal", int(sys.argv[1]))
    c._config["sync_request_timeout"] = 15
    c.execute("import MetaTrader5 as mt5")
    ti = c.eval("mt5.terminal_info()")
    print("unknown" if ti is None else ("on" if ti.trade_allowed else "off"))
except Exception:
    print("bridge-down")
EOF
}

# Ports the host is actually serving an MT5 bridge on. Falls back to 8001 so a
# host whose ss output cannot be read still checks the account that exists.
PORTS="${PORT:-}"
if [ -z "$PORTS" ]; then
  # 8001 upward only. 8000 is the API, and probing that as an MT5 bridge
  # reports a perfectly healthy service as a dead bridge.
  PORTS=$(ss -lnt 2>/dev/null | awk '{print $4}' | awk -F: '{print $NF}' | grep -E '^800[1-9]$' | sort -u | paste -sd' ')
  PORTS=${PORTS:-8001}
fi

# When several bridges are checked, re-run this script once per port so each
# gets its own repair counter and its own alert rate limit -- one terminal
# being off must not suppress the alert for another.
set -- $PORTS
if [ "$#" -gt 1 ]; then
  rc=0
  for p in "$@"; do
    PORT="$p" "$0" || rc=$?
  done
  exit $rc
fi
PORT_ONE="${1:-8001}"

state=$(probe "$PORT_ONE")
state=${state:-unknown}
stamp="/run/molido-algo-watch.${PORT_ONE}.alerted"
STATE_DIR=/var/lib/molido-watchdog
mkdir -p "$STATE_DIR"
TRIES="$STATE_DIR/algo.${PORT_ONE}.count"
MAX_TRIES=2

case "$state" in
  on)
    rm -f "$stamp" "$TRIES"
    exit 0 ;;
  bridge-down)
    # watchdog.sh owns repairing the bridge; only report it here.
    msg="⚠️ Molido: پل MT5 روی پورت $PORT_ONE جواب نمی‌دهد."
    ;;
  off)
    # Try to fix it rather than only reporting it. This is the one failure of
    # 2026-09-03 that needed a human at the GUI: the flag is not settable from
    # any config file, so 114 orders were refused with retcode 10027 over
    # 45 minutes while every internal log looked healthy.
    #
    # Capped at MAX_TRIES because the repair drives the terminal's UI with
    # synthetic mouse clicks. If two attempts have not taken, a third is not
    # more likely to work and each one clicks inside a live trading window --
    # past that point the honest move is to stop and ask for a human.
    n=0; [ -f "$TRIES" ] && n=$(cat "$TRIES" 2>/dev/null || echo 0)
    # Each terminal lives on its own X display, and driving the wrong one
    # sends synthetic clicks into a different account's live trading window.
    # The repair therefore takes the display as an argument and the mapping
    # from bridge port to display is explicit here -- a default would be a
    # guess, and a wrong guess clicks inside someone's open positions.
    case "$PORT_ONE" in
      8001) DISP=":99";  HINT="MetaQuotes-Demo" ;;
      8002) DISP=":100"; HINT="" ;;
      *)    DISP="";     HINT="" ;;
    esac
    if [ -z "$DISP" ]; then
      msg="⚠️ Molido: Algo Trading روی ترمینال پورت $PORT_ONE خاموش است، ولی نمایشگر این ترمینال شناخته‌شده نیست. باید دستی روشن شود."
    elif [ "$n" -lt "$MAX_TRIES" ] && [ -x /opt/mt5/enable-algo.sh ]; then
      echo $((n + 1)) > "$TRIES"
      logger -t molido-algo-watch "port $PORT_ONE ($DISP) trade_allowed off; attempt $((n+1))/$MAX_TRIES"
      timeout 180 /opt/mt5/enable-algo.sh "$DISP" "$HINT" >/tmp/algo-repair-$PORT_ONE.log 2>&1 || true
      # The script's own output is not evidence: it reports clicks, not state.
      # Ask the terminal what it actually thinks now.
      after=$(probe "$PORT_ONE")
      if [ "${after:-off}" = "on" ]; then
        logger -t molido-algo-watch "repaired: trade_allowed is on again"
        rm -f "$stamp" "$TRIES"
        python3 - "🔧 Molido: Algo Trading روی ترمینال پورت $PORT_ONE خاموش شده بود و خودکار روشن شد. معاملات از سر گرفته می‌شود." <<'SEND'
import json, sys, urllib.parse, urllib.request
p = "/var/lib/docker/volumes/molido_runtime_data/_data/runtime-settings.json"
try:
    d = json.load(open(p, encoding="utf-8"))
except Exception:
    sys.exit(0)
tok = (d.get("telegram_bot_token") or "").strip()
chat = d.get("telegram_admin_chat_id")
if not tok or not chat:
    sys.exit(0)
data = urllib.parse.urlencode({"chat_id": chat, "text": sys.argv[1]}).encode()
try:
    urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=data, timeout=15)
except Exception:
    pass
SEND
        exit 0
      fi
      msg="⚠️ Molido: Algo Trading خاموش است و تلاش خودکار برای روشن کردنش ($((n+1)) از $MAX_TRIES) کار نکرد. سفارش‌ها با 10027 رد می‌شوند."
    else
      msg="⚠️ Molido: Algo Trading خاموش است و تعمیر خودکار به سقف تلاش رسید. باید دستی از رابط MT5 روشن شود."
    fi
    ;;
  *)
    exit 0 ;;
esac
logger -t molido-algo-watch "state=$state"
# One alert per 30 minutes while the condition persists.
if [ -f "$stamp" ] && [ $(( $(date +%s) - $(stat -c %Y "$stamp") )) -lt 1800 ]; then
  exit 0
fi
touch "$stamp"
python3 - "$msg" <<'EOF'
import json, sys, urllib.parse, urllib.request
p = "/var/lib/docker/volumes/molido_runtime_data/_data/runtime-settings.json"
try:
    d = json.load(open(p, encoding="utf-8"))
except Exception:
    sys.exit(0)
tok = (d.get("telegram_bot_token") or "").strip()
chat = d.get("telegram_admin_chat_id")
if not tok or not chat:
    sys.exit(0)
data = urllib.parse.urlencode({"chat_id": chat, "text": sys.argv[1]}).encode()
try:
    urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=data, timeout=15)
except Exception:
    pass
EOF
