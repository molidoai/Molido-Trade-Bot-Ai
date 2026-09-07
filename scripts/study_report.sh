#!/bin/bash
# Deliver each study's result to Telegram, in Persian, once.
#
# The previous version pasted raw English log lines. The numbers that matter --
# whether a cell passed BOTH bars, and how many did -- were left for the reader
# to work out from columns, which is how "PF 1.29" got read as a good result
# when it failed the fold test at 9/22.
#
# Cron plus a state file rather than a long-running watcher: the watcher died
# with any reboot, and an overnight reboot is exactly when a result would be
# lost, leaving a silence that looks identical to "still computing".
set -u
S=/var/lib/docker/volumes/molido_runtime_data/_data/runtime-settings.json
STATE=/var/lib/molido-study
mkdir -p "$STATE"

send () {
  local msg="$1" tok chat
  [ -r "$S" ] || return 1
  tok=$(python3 -c "import json;print(json.load(open('$S')).get('telegram_bot_token') or '')" 2>/dev/null)
  chat=$(python3 -c "import json;d=json.load(open('$S'));c=d.get('telegram_admin_chat_id') or (d.get('telegram_allowed_chat_ids') or '').split(',')[0];print(str(c or '').strip())" 2>/dev/null)
  [ -n "$tok" ] && [ -n "$chat" ] || return 1
  curl -s --max-time 25 -o /dev/null -w '%{http_code}' \
    -d "chat_id=$chat" --data-urlencode "text=$msg" \
    "https://api.telegram.org/bot$tok/sendMessage" | grep -q 200
}

# Turns a grid log into a Persian summary that states the verdict per cell,
# rather than a column of numbers the reader has to judge.
summarise_grid () {
  python3 - "$1" <<'PY'
import re, sys
rows, cell = [], None
for ln in open(sys.argv[1], errors="ignore"):
    m = re.match(r"#### \w+ :: (\S+) on (\S+)", ln)
    if m:
        cell = (m.group(2), m.group(1)); continue
    m = re.match(r"\s+\S+\s+n=\s*(\d+)\s+PF=\s*([0-9.]+).*?(\d+)/(\d+) folds", ln)
    if m and cell:
        rows.append((cell[0], cell[1], int(m.group(1)), float(m.group(2)),
                     int(m.group(3)), int(m.group(4))))
        cell = None
if not rows:
    print("نتیجه‌ای در لاگ پیدا نشد."); raise SystemExit
rows.sort(key=lambda r: -r[3])
ok = [r for r in rows if r[3] > 1.0 and r[4] > r[5] / 2]
print("سد قبولی: PF بالای ۱.۰ **و** بیش از نیمی از foldها سودده\n")
print("قبول‌شده: %d از %d سلول\n" % (len(ok), len(rows)))
if ok:
    for s, st, n, pf, fp, ft in ok:
        print("✅ %s / %s\n   PF %.2f · %d/%d fold · %d معامله" % (s, st, pf, fp, ft, n))
    print()
near = [r for r in rows if r[3] > 1.0 and r not in ok]
if near:
    print("PF بالای ۱ ولی fold زیر نصف — رد می‌شود:")
    for s, st, n, pf, fp, ft in near:
        print("❌ %s / %s — PF %.2f ولی فقط %d/%d fold" % (s, st, pf, fp, ft))
    print("   (PF بالا با fold کم یعنی چند برد بزرگ، نه لبه)")
    print()
print("رد شده: %d سلول" % (len(rows) - len(ok) - len(near)))
print()
print("یادآوری: %d از %d تقریباً همان نرخی است که شانس محض می‌دهد."
      % (len(ok), len(rows)))
print("یک قبولی از جست‌وجوی گسترده، نامزد است نه یافته — باید روی")
print("داده‌ای که رویش انتخاب نشده دوباره سنجیده شود.")
PY
}

report_grid () {   # unit log title key
  local unit="$1" log="$2" title="$3" key="$4"
  [ -f "$STATE/$key.sent" ] && return 0
  systemctl is-active --quiet "$unit" && return 0
  [ -s "$log" ] || return 0
  send "📊 $title
$(date '+%Y-%m-%d %H:%M')

$(summarise_grid "$log")" && touch "$STATE/$key.sent"
}

report_decisive () {
  local key=decisive log=/root/decisive.log
  [ -f "$STATE/$key.sent" ] && return 0
  systemctl is-active --quiet molido-decisive && return 0
  [ -s "$log" ] || return 0
  local body
  body=$(grep -aE "^  [0-9]\." "$log" | sed \
    -e 's/1\. control (as published: 1.38)/۱. کنترل (باید نزدیک ۱.۳۸ باشد)/' \
    -e 's/2\. + real overnight financing/۲. + بهره‌ی شبانه‌ی واقعی/' \
    -e 's/3\. + financing + the three brains/۳. + بهره + سه مغز (فیلترها)/' \
    -e 's/4\. + financing, close after 12h/۴. + بهره، بستن بعد از ۱۲ ساعت/' \
    -e 's/5\. + financing, close after 8h/۵. + بهره، بستن بعد از ۸ ساعت/' \
    -e 's/6\. + financing, close after 4h/۶. + بهره، بستن بعد از ۴ ساعت/')
  [ -n "$body" ] || body="(نتیجه‌ای در لاگ نبود)"
  send "🎯 آزمون تعیین‌کننده — XAUUSD / TrendFollowing / H1
$(date '+%Y-%m-%d %H:%M')

$body

چطور بخوانید:
• ردیف ۱ باید نزدیک ۱.۳۸ باشد. اگر نبود، چیز دیگری عوض شده
  و هیچ ردیف دیگری معنا ندارد.
• ردیف ۲ عدد صادقانه‌ی امروز است — با هزینه‌ای که هیچ‌وقت
  شمرده نشده بود (بهره ۷۰٪ هزینه‌ی واقعی است).
• ردیف ۳ در برابر ۲: فیلترها کمک می‌کنند یا لبه را می‌خورند.
• ردیف‌های ۴ تا ۶: آیا بستن قبل از رول‌اوور می‌ارزد.

اگر ردیف ۲ زیر ۱.۱۰ بیفتد، لبه‌ی تأییدشده‌ای نداریم و
صبر کردن برای ۵۰ معامله بی‌فایده است." && touch "$STATE/$key.sent"
}

report_grid molido-h1p2 /root/h1p2.log "شبکه‌ی H1 — سلول‌های اکتشافی" h1p2
report_decisive
