#!/bin/bash
# Send the forward record to Telegram once a day, unasked.
#
# Everything this bot knows about its own performance lived behind an SSH
# session: someone had to log in and run a script to find out whether the live
# configuration was making or losing money. That is the one job that genuinely
# required a person every day, and it is the reason a losing week could go
# unnoticed -- on 2026-09-03 the account had been refusing every order for
# most of a day and nothing said so until someone looked.
#
# Reports per symbol and never pools, for the same reason the report script
# does: a pooled figure across a metal and a JPY pair hides one symbol
# carrying the total.
set -u
cd /opt/molido || exit 0
[ -f /opt/molido/.engine_wanted ] || exit 0
docker inspect -f '{{.State.Running}}' molido-engine 2>/dev/null | grep -qx true || exit 0

docker cp /opt/molido/scripts/forward_record.py molido-engine:/tmp/fr.py >/dev/null 2>&1 || exit 0
BODY=$(docker compose exec -T trading-engine python3 /tmp/fr.py 2>&1)
[ -n "$BODY" ] || exit 0

python3 - "$BODY" <<'EOF'
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
body = sys.argv[1][:3500]
text = "\U0001F4CA <b>گزارش روزانه Molido</b>\n<pre>%s</pre>" % (
    body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
try:
    urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=data, timeout=20)
except Exception:
    pass
EOF
