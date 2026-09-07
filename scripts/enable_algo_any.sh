#!/bin/bash
# Re-enable algorithmic trading on ANY terminal, not just the one on :99.
#
# Usage: enable-algo-any.sh <display> <window-name-regex>
#   e.g. enable-algo-any.sh :100 RoboForex-ECN
#
# Why this exists: enable-algo.sh hardcodes DISPLAY=:99 and searches for a
# "MetaQuotes-Demo" window, so it cannot repair account 2 -- and algo-watch.sh
# says so itself, reporting other terminals instead of fixing them. Account 2
# is now the only account that trades, so the gap covered the whole bot.
#
# It also differs in a way that matters. enable-algo.sh clicks all four
# "Disable algorithmic trading when/via ..." boxes unconditionally. On the
# RoboForex terminal two of those were already clear, including "via external
# Python API" -- the one the bot's own RPyC path depends on -- so the blanket
# version would have switched the block ON while reporting success. Every box
# here is read before it is touched and clicked only if it is in the wrong
# state, which also makes the script safe to re-run.
set -u
DISP="${1:-:100}"
NAME="${2:-RoboForex-ECN}"
export DISPLAY="$DISP"

SHOT=$(mktemp /tmp/algo-XXXXXX.png)
cleanup() { rm -f "$SHOT"; }
trap cleanup EXIT

# xdotool windowactivate needs a window manager or it fails with
# "no _NET_ACTIVE_WINDOW". One per display.
if ! ps -eo pid= -o args= | grep "[m]atchbox-window-manager" | awk '{print $1}' | while read -r p; do
      tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qx "DISPLAY=$DISP" && echo y; done | grep -q y; then
  nohup matchbox-window-manager -use_titlebar no >/dev/null 2>&1 &
  sleep 3
fi

visible_dialog() { xdotool search --onlyvisible --name '^Options' 2>/dev/null | head -1; }

open_dialog() {
  for attempt in 1 2 3 4 5; do
    [ -n "$(visible_dialog)" ] && return 0
    local wid; wid=$(xdotool search --onlyvisible --name "$NAME" | head -1)
    [ -z "$wid" ] && { echo "no window matching '$NAME' on $DISP"; return 1; }
    xdotool windowactivate "$wid" 2>/dev/null; sleep 1
    xdotool mousemove 205 11 click 1; sleep 2      # Tools
    xdotool mousemove 231 240; sleep 1
    xdotool mousemove 231 245; sleep 1             # motion highlights the row
    xdotool click 1; sleep 3                       # Options
    [ -n "$(visible_dialog)" ] && return 0
    xdotool key Escape 2>/dev/null; sleep 1
  done
  return 1
}

open_dialog || { echo "FAILED: Options dialog never became visible"; exit 1; }
DID=$(visible_dialog)
eval "$(xdotool getwindowgeometry --shell "$DID")"

# Offsets are relative to the geometry xdotool reports, so they survive the
# dialog opening at a different position. Verified against a screenshot:
# reported origin sits above-left of the drawn frame, which is why absolute
# coordinates from a screenshot cannot be reused directly.
tab_x=$((X + 157)); tab_y=$((Y - 4))
xdotool mousemove $tab_x $tab_y; sleep 1; xdotool click 1; sleep 2   # Experts tab

# name:dx:dy:wanted   (wanted=1 checked, 0 clear)
BOXES="allow_algo_trading:31:40:1
disable_on_account_change:46:66:0
disable_on_profile_change:46:90:0
disable_on_symbol_change:46:115:0
disable_via_python_api:46:139:0"

state_of() {  # $1=x $2=y -> "1" checked / "0" clear, by sampling the box interior
  local px py val
  px=$1; py=$2
  # Darkest pixel, not the average. Measured on this dialog with the state
  # known: a checked box reads 23, a clear one 174 -- while the 9x9 *means*
  # were 222 and 245, which is why an average-based test read a ticked box as
  # empty and switched algorithmic trading off. The tick is a few thin dark
  # pixels; it moves the minimum decisively and the mean barely at all.
  val=$(import -window root -crop 7x7+$((px-3))+$((py-3)) +repage -format '%[fx:int(255*minima)]' info: 2>/dev/null)
  [ -z "$val" ] && { echo "?"; return; }
  if [ "$val" -lt 100 ]; then echo 1; else echo 0; fi
}

changed=0
echo "$BOXES" | while IFS=: read -r nm dx dy want; do
  [ -z "$nm" ] && continue
  bx=$((X + dx)); by=$((Y + dy))
  cur=$(state_of "$bx" "$by")
  if [ "$cur" = "?" ]; then
    echo "  $nm: could not read state -- leaving alone"
  elif [ "$cur" = "$want" ]; then
    echo "  $nm: already $want"
  else
    echo "  $nm: $cur -> $want (clicking)"
    xdotool mousemove $bx $by; sleep 1; xdotool click 1; sleep 1
    changed=1
  fi
  # The four sub-boxes are greyed out while the master is off, so a click on
  # them does nothing until the master has been set. Give the dialog a moment
  # after the master flips.
  [ "$nm" = "allow_algo_trading" ] && sleep 2
done

import -window root "$SHOT" 2>/dev/null
if [ -n "$(visible_dialog)" ]; then
  xdotool mousemove $((X + 408)) $((Y + 350)); sleep 1; xdotool click 1; sleep 3   # OK
  echo "OK clicked"
else
  echo "WARNING: dialog closed before OK -- nothing was saved"
  exit 1
fi
