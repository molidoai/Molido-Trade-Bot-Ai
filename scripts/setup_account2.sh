#!/bin/bash
# Configure the second trading account.
#
# Deployed on the VPS as /opt/mt5/setup-account2.sh (alongside the other
# MT5/Wine host scripts, which live outside this repo); this is the
# version-controlled copy. Run it interactively ON THE SERVER:
#   sudo /opt/mt5/setup-account2.sh
#
# Prerequisites, already provisioned: a second MT5 terminal installation at
# C:\Program Files\MT5-acc2 inside the shared Wine prefix, its own Xvfb
# display :100, and an RPyC bridge on 127.0.0.1:8002 -- see the
# xvfb-mt5-acc2 / mt5-acc2 / mt5linux-acc2 / mt5linux-proxy-acc2 systemd
# units. Each MT5 terminal serves exactly one account, which is why a
# second account needs a second terminal rather than just a config entry.
# The password is read with `read -s` and written only to files owned by
# root with mode 600 -- it is never echoed, never passed as an argument
# (so it stays out of `ps` and shell history), and never leaves this host.
set -euo pipefail

read -rp "MT5 login (account number): " LOGIN
read -rp "MT5 server (e.g. MetaQuotes-Demo): " SERVER
read -rsp "MT5 password: " PASSWORD; echo
read -rp "Account name for the dashboard [Account 2]: " NAME
NAME="${NAME:-Account 2}"
read -rp "Mode DEMO/PROP/REAL [DEMO]: " MODE
MODE="${MODE:-DEMO}"

if [ -z "$LOGIN" ] || [ -z "$SERVER" ] || [ -z "$PASSWORD" ]; then
  echo "login, server and password are all required" >&2; exit 1
fi

# 1) terminal startup config
umask 077
cat > "/opt/wine-mt5/drive_c/MT5cfg/start2.ini" <<INI
[Common]
Login=$LOGIN
Password=$PASSWORD
Server=$SERVER
ProxyEnable=0
NewsEnable=0
KeepPrivate=1

[Experts]
AllowLiveTrading=1
Enabled=1
Account=1
Chart=1
Api=1
INI
chmod 600 "/opt/wine-mt5/drive_c/MT5cfg/start2.ini"
echo "wrote start2.ini"

# 2) engine account entry (runtime-settings.json lives in the docker volume)
export ACC2_LOGIN="$LOGIN" ACC2_SERVER="$SERVER" ACC2_PASSWORD="$PASSWORD" ACC2_NAME="$NAME" ACC2_MODE="$MODE"
docker exec -e ACC2_LOGIN -e ACC2_SERVER -e ACC2_PASSWORD -e ACC2_NAME -e ACC2_MODE \
  molido-api python3 - <<PY
import json, os
p = "/app/data/runtime-settings.json"
d = json.load(open(p))
accounts = d.get("accounts")
if not isinstance(accounts, list) or not accounts:
    # Promote the existing single-account settings to account 1 so nothing
    # about the running account changes when the list is introduced.
    accounts = [{
        "id": "default", "name": "Account 1", "enabled": True,
        "trading_account_mode": d.get("trading_account_mode", "DEMO"),
        "mt5_login": d.get("mt5_login") or d.get("mt5_real_login"),
        "mt5_password": d.get("mt5_password") or d.get("mt5_real_password"),
        "mt5_server": d.get("mt5_server") or d.get("mt5_real_server"),
        "rpc_port": 8001,
    }]
acc2 = {
    "id": "acc2", "name": os.environ["ACC2_NAME"], "enabled": True,
    "trading_account_mode": os.environ["ACC2_MODE"],
    "mt5_login": os.environ["ACC2_LOGIN"],
    "mt5_password": os.environ["ACC2_PASSWORD"],
    "mt5_server": os.environ["ACC2_SERVER"],
    "mt5_path": "C:\\Program Files\\MT5-acc2\\terminal64.exe",
    "rpc_port": 8002,
}
accounts = [a for a in accounts if a.get("id") != "acc2"] + [acc2]
d["accounts"] = accounts
json.dump(d, open(p, "w"), indent=2)
print("accounts now:", [a.get("id") for a in accounts])
PY

# 3) bring the second terminal up
systemctl enable --now xvfb-mt5-acc2.service mt5-acc2.service mt5linux-acc2.service mt5linux-proxy-acc2.service
echo
echo "Started. Remaining manual steps:"
echo "  1) Open port 8002 to the docker bridges (firewall is yours to change):"
echo "       sudo ufw insert 1 allow from 172.18.0.0/16 to any port 8002 proto tcp"
echo "       sudo ufw insert 1 allow from 172.17.0.0/16 to any port 8002 proto tcp"
echo "  2) Enable algo trading in the SECOND terminal (display :100), same as"
echo "     account 1: Tools > Options > Experts >"
echo "       [x] Allow algorithmic trading"
echo "       [ ] Disable algorithmic trading via external Python API   <- must be OFF"
echo "  3) Restart the engine so it picks up the new account:"
echo "       cd /opt/molido && docker compose restart trading-engine"
