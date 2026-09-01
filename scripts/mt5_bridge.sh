#!/bin/bash
# Relay the MT5 RPyC ports from the Wine host into the docker bridges.
#
# MT5 (under Wine) listens on 127.0.0.1 only, so containers cannot reach it
# directly. socat bridges each terminal's port onto every docker gateway IP.
# This used to be started by hand, which meant it did NOT survive a reboot:
# containers and MT5 would come back and trading would silently do nothing
# because nothing was listening on the bridge.
#
# 8001 = account 1, 8002 = account 2 (second terminal, display :100). A port
# is only relayed once its terminal is actually listening locally, so this is
# safe to run with one account or two.
#
# Binds to the bridge gateways only -- never 0.0.0.0, which would expose the
# broker RPC to the internet.
set -u

PORTS="${MT5_BRIDGE_PORTS:-8001 8002}"

local_up() { ss -lnt 2>/dev/null | grep -q "127.0.0.1:$1 "; }

start_one() {
  local ip="$1" port="$2"
  ip -4 addr show 2>/dev/null | grep -qw "$ip" || return 0
  pgrep -f "TCP-LISTEN:$port,bind=$ip" >/dev/null 2>&1 && return 0
  /usr/bin/socat "TCP-LISTEN:$port,bind=$ip,fork,reuseaddr" "TCP:127.0.0.1:$port" &
}

while true; do
  # Discover the gateways rather than hardcoding them: docker assigns project
  # network subnets dynamically, so the molido bridge is not guaranteed to be
  # 172.18.0.1 after a reboot.
  gws=$(docker network ls -q 2>/dev/null | while read -r n; do
          docker network inspect "$n" \
            --format '{{range .IPAM.Config}}{{.Gateway}}{{"\n"}}{{end}}' 2>/dev/null
        done | grep -E '^172\.' | sort -u)
  for port in $PORTS; do
    local_up "$port" || continue
    for gw in $gws; do start_one "$gw" "$port"; done
  done
  sleep 30
done
