#!/bin/bash
# Stops the SSH flood. $1 = the admin IP to never ban (this session's source).
#
# Ordering is deliberate: fail2ban first, because it alone removes most of the
# load and needs no config change; the sshd change second, validated and
# rolled back on failure. Nothing here restarts sshd -- reload keeps every
# existing session alive -- and the provider console is unaffected regardless.
exec > /root/harden.log 2>&1
set -uo pipefail
ADMIN_IP="${1:-}"
echo "===== harden $(date -Is)  admin_ip=${ADMIN_IP:-none} ====="

echo; echo "--- 0. refuse to proceed without key access ---"
KEYS=$(grep -csE '^(ssh|ecdsa)-' /root/.ssh/authorized_keys 2>/dev/null || echo 0)
if [ "$KEYS" -lt 1 ]; then
  echo "ABORT: no authorized_keys for root. Turning off passwords would lock you out."
  exit 1
fi
echo "authorized_keys: $KEYS key(s) -- safe to disable passwords"

echo; echo "--- 1. fail2ban ---"
DEBIAN_FRONTEND=noninteractive apt-get install -y fail2ban python3-systemd >/dev/null 2>&1
IGN="127.0.0.1/8 ::1"
[ -n "$ADMIN_IP" ] && IGN="$IGN $ADMIN_IP"
cat > /etc/fail2ban/jail.d/sshd.local <<CONF
[sshd]
enabled  = true
backend  = systemd
maxretry = 4
findtime = 10m
bantime  = 2h
ignoreip = $IGN
CONF
systemctl enable --now fail2ban >/dev/null 2>&1
sleep 4
# Verify rather than assume: a jail that failed to load is silent about it.
if fail2ban-client status sshd >/dev/null 2>&1; then
  echo "sshd jail ACTIVE:"; fail2ban-client status sshd | sed 's/^/  /'
else
  echo "sshd jail NOT running -- falling back to the file backend"
  sed -i 's/^backend  = systemd/backend  = auto/' /etc/fail2ban/jail.d/sshd.local
  systemctl restart fail2ban; sleep 4
  fail2ban-client status sshd 2>&1 | sed 's/^/  /' || echo "  still not running"
fi

echo; echo "--- 2. sshd config ---"
MAIN=/etc/ssh/sshd_config
DROPIN=/etc/ssh/sshd_config.d/99-molido-harden.conf
cp "$MAIN" "$MAIN.bak.$(date +%F-%H%M)"
CONF_BODY='# Keys only. Root keeps key login (the deploy key needs it); passwords are
# refused, which is the whole of what the flood is attempting.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
# Room for real connections, and a per-source cap so one attacker cannot fill
# the unauthenticated queue and make sshd drop everyone else before the banner.
MaxStartups 60:30:200
PerSourceMaxStartups 6'

# The drop-in only works if the main config includes it. If it does not, the
# settings would sit on disk doing nothing and look applied -- so check.
if grep -qE '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/\*\.conf' "$MAIN"; then
  echo "drop-in directory is included -> writing $DROPIN"
  mkdir -p /etc/ssh/sshd_config.d; printf '%s\n' "$CONF_BODY" > "$DROPIN"
  REVERT="rm -f $DROPIN"
else
  echo "no Include directive -> appending to $MAIN directly"
  printf '\n# --- molido hardening ---\n%s\n' "$CONF_BODY" >> "$MAIN"
  REVERT="cp $MAIN.bak.$(date +%F-%H%M) $MAIN"
fi

if sshd -t 2>&1; then
  echo "config valid -> reload"
  systemctl reload ssh
else
  echo "CONFIG INVALID -- reverting, sshd left exactly as it was"
  eval "$REVERT"
  exit 1
fi

echo; echo "--- 3. what is actually in effect ---"
sshd -T 2>/dev/null | grep -iE 'maxstartups|persourcemaxstartups|passwordauthentication|permitrootlogin' | sed 's/^/  /'
echo "  fail2ban: $(systemctl is-active fail2ban)"
echo "  sshd:     $(systemctl is-active ssh)"
echo; echo "===== done $(date -Is) ====="
