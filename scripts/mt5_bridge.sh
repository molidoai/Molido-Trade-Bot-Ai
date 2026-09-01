#!/bin/bash
# Relay the MT5 RPyC port from the Wine host into the docker bridges.
#
# MT5 (under Wine) listens on 127.0.0.1:8001 only, so containers cannot reach
# it directly. socat bridges it onto each docker gateway IP. This used to be
# started by hand, which meant it did NOT survive a reboot: the containers
# would come back, MT5 would come back, and trading would silently do nothing
# because nothing was listening on the bridge. Hence this unit.
#
# Binds to the bridge gateways only -- never 0.0.0.0, which would expose the
# broker RPC to the internet.
set -u

start_one() {
  local ip="$1"
  ip -4 addr show 2>/dev/null | grep -qw "$ip" || return 1
  pgrep -f "TCP-LISTEN:8001,bind=$ip" >/dev/null 2>&1 && return 0
  /usr/bin/socat "TCP-LISTEN:8001,bind=$ip,fork,reuseaddr" TCP:127.0.0.1:8001 &
  return 0
}

while true; do
  # Discover the gateways rather than hardcoding them: docker assigns project
  # network subnets dynamically, so the molido bridge is not guaranteed to be
  # 172.18.0.1 after a reboot.
  gws=$(docker network ls -q 2>/dev/null | while read -r n; do
          docker network inspect "$n" \
            --format '{{range .IPAM.Config}}{{.Gateway}}{{"\n"}}{{end}}' 2>/dev/null
        done | grep -E '^172\.' | sort -u)
  for gw in $gws; do start_one "$gw"; done
  sleep 30
done
