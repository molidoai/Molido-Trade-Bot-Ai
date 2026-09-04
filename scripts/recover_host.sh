#!/bin/bash
# Diagnose and recover the box after it stops answering, then leave exactly one
# MT5 terminal running.
#
# Run on the server right after a power cycle:
#   sudo bash recover_host.sh            # diagnose and clean, change nothing else
#   sudo bash recover_host.sh --prop     # ...and switch to the prop account only
#   sudo bash recover_host.sh --demo     # ...and switch to the demo account only
#
# On 2026-09-04 the host stopped answering on 22, 443 and 80 while still
# completing TCP handshakes. That symptom does not identify the cause: a full
# root disk, exhausted memory and total CPU starvation all produce it, because
# sshd and nginx each need to allocate and write per connection. Guessing wrong
# wastes a reboot, and in the disk case a reboot does not help at all -- the
# disk is still full when it comes back.
#
# So this measures first and prints what it found before touching anything.
set -uo pipefail

say () { printf '\n=== %s\n' "$*"; }

say "disk"
df -h / | sed 's/^/  /'
USE=$(df --output=pcent / | tail -1 | tr -dc '0-9')

say "memory"
free -m | sed -n '1,3p' | sed 's/^/  /'

say "load (per core, 8 cores here)"
uptime | sed 's/^/  /'

say "what docker is holding"
docker system df 2>/dev/null | sed 's/^/  /' || echo "  docker not responding"

say "anything OOM-killed since boot?"
if dmesg -T 2>/dev/null | grep -i "out of memory\|oom-kill" | tail -5 | grep -q .; then
  dmesg -T | grep -i "out of memory\|oom-kill" | tail -5 | sed 's/^/  /'
  echo "  -> memory was the constraint"
else
  echo "  none -- memory was probably NOT the constraint"
fi

# --- clean, but only what is safe to lose --------------------------------
# Build cache and dangling images are reproducible from the repo. Volumes are
# never touched: molido_runtime_data holds the journals, the settings and the
# credentials, and losing it loses the trading history.
if [ "${USE:-0}" -ge 75 ]; then
  say "root at ${USE}% -- pruning docker build cache and unused images"
  BEFORE=$(df --output=avail / | tail -1)
  docker builder prune -af >/dev/null 2>&1 || true
  docker image prune -af  >/dev/null 2>&1 || true
  AFTER=$(df --output=avail / | tail -1)
  echo "  freed $(( (AFTER - BEFORE) / 1024 )) MB; now $(df --output=pcent / | tail -1 | tr -d ' ')"
else
  say "root at ${USE}% -- no prune needed"
fi

# --- one terminal at a time ----------------------------------------------
# Two Wine terminals plus six containers is what this box was carrying when it
# went down. Whichever resource ran out, halving that load is the change that
# makes the next hour survivable.
ACC1="mt5 mt5linux mt5linux-proxy xvfb-mt5"
ACC2="mt5-acc2 mt5linux-acc2 mt5linux-proxy-acc2 xvfb-mt5-acc2"

stop_stack () {
  for u in $1; do
    systemctl list-unit-files "$u.service" >/dev/null 2>&1 || continue
    systemctl disable --now "$u.service" >/dev/null 2>&1 || true
    echo "  stopped and disabled $u"
  done
}

case "${1:-}" in
  --prop)
    say "leaving the PROP terminal only"
    stop_stack "$ACC1"
    for u in $ACC2; do
      systemctl list-unit-files "$u.service" >/dev/null 2>&1 || continue
      systemctl enable --now "$u.service" >/dev/null 2>&1 || true
    done
    echo "  started account 2 (display :100, bridge 8002)"
    ;;
  --demo)
    say "leaving the DEMO terminal only"
    stop_stack "$ACC2"
    for u in $ACC1; do
      systemctl list-unit-files "$u.service" >/dev/null 2>&1 || continue
      systemctl enable --now "$u.service" >/dev/null 2>&1 || true
    done
    echo "  started account 1 (display :99, bridge 8001)"
    ;;
  *)
    say "no --prop/--demo given; terminals left exactly as they are"
    ;;
esac

say "bridges listening"
ss -lnt 2>/dev/null | awk '{print $4}' | awk -F: '{print $NF}' \
  | grep -E '^800[1-9]$' | sort -u | sed 's/^/  /' || echo "  none"

say "final state"
df -h / | tail -1 | sed 's/^/  /'
free -m | sed -n 2p | sed 's/^/  /'
echo
echo "Next: enable algorithmic trading in the terminal that is now running,"
echo "then confirm with terminal_info().trade_allowed -- the clicks are not proof."
