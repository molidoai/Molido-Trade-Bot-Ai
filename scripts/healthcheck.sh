#!/bin/bash
# One-shot health check for the whole Molido stack.
#
# Written because checking this by hand meant a dozen separate commands every
# time, and half the incidents in this project were things that check would
# have caught: the MT5 bridge not surviving a reboot, the engine trading on
# three-hour-old candles, closes never being journalled so every adaptive
# limit sat on an empty tank.
#
# Exit code is the number of FAIL lines, so it can gate a deploy or a cron.
#
#   /opt/molido/healthcheck.sh
set -u

FAILS=0
WARNS=0
ok()   { printf '  \033[32mOK  \033[0m %s\n' "$1"; }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$1"; WARNS=$((WARNS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILS=$((FAILS+1)); }
head_() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

S=/var/lib/docker/volumes/molido_runtime_data/_data
J="$S/journal-default.jsonl"

head_ "Containers"
for c in molido-engine molido-api molido-web molido-postgres molido-redis molido-telegram; do
  st=$(docker inspect "$c" --format '{{.State.Status}}' 2>/dev/null || echo missing)
  rc=$(docker inspect "$c" --format '{{.RestartCount}}' 2>/dev/null || echo 0)
  if [ "$st" = "running" ]; then
    [ "${rc:-0}" -gt 3 ] && warn "$c running but restarted $rc times" || ok "$c running"
  else
    bad "$c is $st"
  fi
done

head_ "MT5 stack"
for s in mt5 mt5linux mt5linux-proxy xvfb-mt5 molido-mt5-bridge; do
  systemctl is-active --quiet "$s" && ok "$s active" || bad "$s is $(systemctl is-active "$s" 2>/dev/null)"
done
n=$(ss -lnt 2>/dev/null | grep -c '172\..*:8001')
[ "$n" -ge 1 ] && ok "MT5 bridge listening on $n docker gateway(s)" \
               || bad "MT5 bridge has no docker-side listener -- engine cannot reach the broker"

head_ "Broker link"
if docker exec molido-engine python3 - <<'PY' 2>/dev/null
import os, json, asyncio, sys
from molido_broker import create_broker, BrokerType
rt = json.load(open('/app/data/runtime-settings.json'))
async def go():
    b = create_broker(BrokerType.MT5, login=int(rt['mt5_login']), password=rt['mt5_password'],
                      server=rt['mt5_server'],
                      rpc_host=os.getenv('MT5_RPC_HOST', 'host.docker.internal'), rpc_port=8001)
    if not await b.connect():
        sys.exit(1)
    a = await b.get_account_info()
    ti = b._mt5.terminal_info()
    print('balance=%.2f equity=%.2f trade_allowed=%s' % (a.balance, a.equity,
          getattr(ti, 'trade_allowed', None)))
    sys.exit(0 if getattr(ti, 'trade_allowed', False) else 2)
asyncio.run(go())
PY
then ok "broker reachable and algo trading enabled"
else
  code=$?
  [ $code -eq 2 ] && bad "broker reachable but trade_allowed=False (GUI setting -- see /opt/mt5)" \
                  || bad "cannot reach broker through the bridge"
fi

head_ "Data freshness"
# The bug that made every signal act on three-hour-old prices was invisible
# until someone compared a candle to the clock. Check it every time.
docker exec molido-engine python3 - <<'PY' 2>/dev/null || echo "  (could not evaluate)"
import os, json, asyncio
from datetime import datetime, timezone
from molido_broker import create_broker, BrokerType
from molido_shared.types import TimeFrame
from molido_shared.point_in_time import bar_close_time
rt = json.load(open('/app/data/runtime-settings.json'))
async def go():
    b = create_broker(BrokerType.MT5, login=int(rt['mt5_login']), password=rt['mt5_password'],
                      server=rt['mt5_server'],
                      rpc_host=os.getenv('MT5_RPC_HOST', 'host.docker.internal'), rpc_port=8001)
    await b.connect()
    sym = (rt.get('symbols') or 'EURUSD').split(',')[0].strip()
    t = await b.get_tick(sym)
    cs = await b.get_candles(sym, TimeFrame.M15, count=3)
    gap = abs(t.mid - float(cs[-1].close))
    off = (bar_close_time(cs[-1]).replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600
    print('  %-6s tick-vs-last-close gap %.5f | broker clock %+.2fh vs UTC' % (sym, gap, off))
asyncio.run(go())
PY

head_ "Trading state"
python3 - <<PY
import json
d = json.load(open("$S/runtime-settings.json"))
print("  master=%s mode=%s tf=%s risk=%s daily_cap=%s" % (
    d.get("master_bot_enabled"), d.get("trading_account_mode"), d.get("timeframe"),
    d.get("default_risk_per_trade"), d.get("max_daily_loss")))
print("  symbols:", d.get("symbols"))
rpt, dl = float(d.get("default_risk_per_trade") or 0), float(d.get("max_daily_loss") or 0)
if rpt and dl and rpt >= dl:
    print("  INCOHERENT: risk per trade >= daily cap; one loss ends the day")
PY

head_ "Outcome loop"
# Every adaptive limit reads these. They were all silently empty once.
if [ -f "$J" ]; then
  closes=$(grep -c '"event": "close"' "$J" 2>/dev/null || echo 0)
  withr=$(grep '"event": "close"' "$J" 2>/dev/null | grep -c 'r_multiple' || echo 0)
  fills=$(grep -c '"event": "fill"' "$J" 2>/dev/null || echo 0)
  echo "  fills=$fills closes=$closes closes_with_R=$withr"
  [ "$fills" -gt 0 ] && [ "$closes" -eq 0 ] && bad "trades open but no close is ever recorded -- learning and streak limits are blind" || ok "close recording present"
else
  warn "no journal yet at $J"
fi

head_ "Engine errors (last 500 log lines)"
e=$(docker logs --tail 500 molido-engine 2>&1 | grep -ciE 'traceback|exception' || true)
[ "${e:-0}" -eq 0 ] && ok "no tracebacks" || bad "$e traceback/exception lines"

head_ "Web"
code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' https://mtrade.molido.shop/login 2>/dev/null)
[ "$code" = "200" ] && ok "site 200" || bad "site returned $code"
h=$(curl -s -m 15 http://localhost:8000/api/v1/health 2>/dev/null)
echo "  api: $h"
exp=$(certbot certificates 2>/dev/null | grep -oE 'VALID: [0-9]+ days' | head -1)
[ -n "$exp" ] && ok "TLS $exp" || warn "could not read certificate expiry"

head_ "Resources"
echo "  cores=$(nproc)  load=$(cut -d' ' -f1-3 /proc/loadavg)"
free -m | awk '/Mem:/{printf "  ram %s MB used of %s, %s available\n", $3, $2, $7}'
df -h / | awk 'NR==2{printf "  disk %s used of %s (%s)\n", $3, $2, $5}'
lpc=$(awk -v c="$(nproc)" '{printf "%.2f", $1/c}' /proc/loadavg)
awk -v l="$lpc" 'BEGIN{exit !(l>1.5)}' && warn "load per core $lpc -- oversubscribed" || ok "load per core $lpc"
avail=$(free -m | awk '/Mem:/{print $7}')
[ "$avail" -lt 500 ] && bad "only ${avail}MB available -- builds will swap" || ok "${avail}MB available"

head_ "Backups"
b=$(ls -1 /opt/molido/backups 2>/dev/null | wc -l)
[ "$b" -gt 0 ] && ok "$b backup files" || bad "no backups"
newest=$(find /opt/molido/backups -type f -mtime -2 2>/dev/null | wc -l)
[ "$newest" -gt 0 ] && ok "$newest backup(s) newer than 48h" || warn "no backup in the last 48h"

head_ "Security updates"
u=$(apt list --upgradable 2>/dev/null | grep -c '\-security' || true)
[ "${u:-0}" -eq 0 ] && ok "no pending security updates" || warn "$u pending security updates"

printf '\n\033[1m== SUMMARY ==\033[0m\n  %d FAIL, %d WARN\n' "$FAILS" "$WARNS"
exit "$FAILS"
