#!/bin/bash
# Put the second MT5 terminal in its own Wine prefix, then prove both accounts
# can serve the Python API at the same time.
#
#   sudo bash install_multi_account.sh
#
# Why a second prefix at all: two terminals sharing one WINEPREFIX share one
# wineserver, and MT5 serves its Python API on a fixed local port (22346) that
# only one of them can own. The loser starts, signs in, and looks entirely
# healthy in its own log, while every mt5.initialize() against it fails with
# "IPC timeout" -- an error that names neither the port nor the conflict. That
# cost an afternoon, so the check at the end asserts the thing that actually
# matters rather than that the files landed.
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/../infra/mt5"
PREFIX2=/opt/wine-mt5-acc2

[ -d "$PREFIX2" ] || { echo "missing $PREFIX2 -- copy the prefix first" >&2; exit 1; }

echo "=== installing launchers"
install -m 755 "$SRC/start_mt5_acc2.sh"      /opt/mt5/start_mt5_acc2.sh
install -m 755 "$SRC/start_mt5linux_acc2.sh" /opt/mt5/start_mt5linux_acc2.sh
grep -h WINEPREFIX /opt/mt5/start_mt5_acc2.sh /opt/mt5/start_mt5linux_acc2.sh | sed 's/^/  /'

echo "=== the terminal config must live in the new prefix too"
mkdir -p "$PREFIX2/drive_c/MT5cfg"
if [ -f /opt/wine-mt5/drive_c/MT5cfg/start2.ini ]; then
  install -m 600 /opt/wine-mt5/drive_c/MT5cfg/start2.ini "$PREFIX2/drive_c/MT5cfg/start2.ini"
  echo "  start2.ini copied (login/server only shown):"
  tr -d '\r' < "$PREFIX2/drive_c/MT5cfg/start2.ini" | grep -iE '^(Login|Server)=' | sed 's/^/    /'
else
  echo "  WARNING: no start2.ini -- the terminal will start without signing in"
fi

echo "=== restarting account 2 in its own prefix"
systemctl restart xvfb-mt5-acc2 >/dev/null 2>&1; sleep 5
systemctl restart mt5-acc2      >/dev/null 2>&1; sleep 45
systemctl restart mt5linux-acc2 mt5linux-proxy-acc2 >/dev/null 2>&1; sleep 20

echo "=== wineservers (one per prefix is the point)"
pgrep -a wineserver 2>/dev/null | wc -l | sed 's/^/  wineserver processes: /'
ss -lntp 2>/dev/null | grep -c 22346 | sed 's/^/  listeners on 22346: /'

echo "=== bridges"
ss -lnt 2>/dev/null | awk '{print $4}' | awk -F: '{print $NF}' \
  | grep -E '^800[1-9]$' | sort -u | paste -sd' ' | sed 's/^/  /'

echo
echo "=== the only check that matters: can BOTH answer at once?"
fail=0
for port in 8001 8002; do
  out=$(docker compose -f /opt/molido/docker-compose.yml exec -T trading-engine python3 - "$port" 2>/dev/null <<'PY'
import sys, rpyc
try:
    c = rpyc.classic.connect("host.docker.internal", int(sys.argv[1]))
    c._config["sync_request_timeout"] = 45
    c.execute("import MetaTrader5 as mt5; ok = mt5.initialize()")
    if not c.eval("ok"):
        print("initialize failed: %s" % (c.eval("mt5.last_error()"),))
    else:
        c.execute("ai = mt5.account_info(); ti = mt5.terminal_info()")
        print("login=%s server=%s balance=%s trade_allowed=%s" % (
            c.eval("ai.login if ai else None"),
            c.eval("ai.server if ai else None"),
            c.eval("ai.balance if ai else None"),
            c.eval("ti.trade_allowed if ti else None")))
except Exception as exc:
    print("unreachable: %s" % exc)
PY
)
  printf '  %s -> %s\n' "$port" "${out:-no answer}"
  case "$out" in login=*) ;; *) fail=1 ;; esac
done

echo
free -m | sed -n 2p | sed 's/^/  /'
[ "$fail" -eq 0 ] && echo "  BOTH ACCOUNTS LIVE" || echo "  *** at least one account is not answering ***"
exit $fail
