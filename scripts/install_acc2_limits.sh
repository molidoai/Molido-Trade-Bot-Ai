#!/bin/bash
# Install the resource cage for the second MT5 terminal, then prove it applied.
#
# Run on the server after a reboot and BEFORE starting the second terminal:
#   sudo bash install_acc2_limits.sh
#
# Starting a second Wine + MT5 + Xvfb stack unconstrained took this 5.8 GB box
# down completely on 2026-09-04: TCP handshakes still succeeded while sshd and
# nginx answered nothing, which cannot be repaired from inside and needed a
# power cycle. The cage is what makes a second account survivable here.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/../infra/systemd"
UNITS="mt5-acc2 mt5linux-acc2 mt5linux-proxy-acc2 xvfb-mt5-acc2"

[ -f "$SRC/molido-mt5-acc2.slice" ] || { echo "missing $SRC/molido-mt5-acc2.slice" >&2; exit 1; }

install -m 644 "$SRC/molido-mt5-acc2.slice" /etc/systemd/system/molido-mt5-acc2.slice
echo "installed molido-mt5-acc2.slice"

for u in $UNITS; do
  if ! systemctl list-unit-files "$u.service" >/dev/null 2>&1; then
    echo "  skip $u -- no such unit on this host"
    continue
  fi
  mkdir -p "/etc/systemd/system/$u.service.d"
  install -m 644 "$SRC/$u.service.d/slice.conf" "/etc/systemd/system/$u.service.d/slice.conf"
  echo "  drop-in for $u"
done

systemctl daemon-reload
echo "daemon reloaded"

# The slice existing is not evidence that anything runs inside it. Only the
# unit's resolved Slice= property is, and it is the piece that silently does
# nothing when the drop-in is missing or misnamed.
echo
echo "resolved slice per unit:"
fail=0
for u in $UNITS; do
  systemctl list-unit-files "$u.service" >/dev/null 2>&1 || continue
  got=$(systemctl show -p Slice --value "$u.service" 2>/dev/null || echo "?")
  printf "  %-22s %s" "$u" "$got"
  if [ "$got" = "molido-mt5-acc2.slice" ]; then echo "  ok"; else echo "  *** NOT CAGED ***"; fail=1; fi
done

echo
echo "cage limits:"
systemctl show molido-mt5-acc2.slice -p MemoryHigh -p MemoryMax -p CPUQuotaPerSecUSec -p MemorySwapMax 2>/dev/null \
  | sed 's/^/  /'

echo
free -m | sed -n '1,2p' | sed 's/^/  /'
exit $fail
