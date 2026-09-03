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
# The query goes through the engine container because the host has no rpyc.
set -uo pipefail
cd /opt/molido || exit 0
[ -f /opt/molido/.engine_wanted ] || exit 0
docker inspect -f '{{.State.Running}}' molido-engine 2>/dev/null | grep -qx true || exit 0

state=$(docker compose exec -T trading-engine python3 - 2>/dev/null <<'EOF'
import rpyc
try:
    c = rpyc.classic.connect("host.docker.internal", 8001)
    c._config["sync_request_timeout"] = 15
    c.execute("import MetaTrader5 as mt5")
    ti = c.eval("mt5.terminal_info()")
    print("unknown" if ti is None else ("on" if ti.trade_allowed else "off"))
except Exception:
    print("bridge-down")
EOF
)
state=${state:-unknown}
stamp=/run/molido-algo-watch.alerted
case "$state" in
  on)
    rm -f "$stamp"
    exit 0 ;;
  off)
    msg="⚠️ Molido: Algo Trading در ترمینال MT5 خاموش است. سفارش‌ها با 10027 رد می‌شوند. /opt/mt5/enable-algo.sh را اجرا کنید." ;;
  bridge-down)
    msg="⚠️ Molido: پل MT5 (پورت 8001) جواب نمی‌دهد. systemctl start mt5.service mt5linux.service" ;;
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
