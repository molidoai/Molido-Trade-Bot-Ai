#!/bin/bash
# Turn on algorithmic trading in one MT5 terminal, for the external Python API.
#
#   enable_algo.sh [display] [window-name-fragment]
#   enable_algo.sh :99                 # account 1 (the default)
#   enable_algo.sh :100 FundedNext     # account 2
#
# terminal_info().trade_allowed is GUI-only state. It cannot be set from
# start.ini or common.ini -- AllowLiveTrading=1 there is not enough, and the
# values persist across a restart while the running state does not. It also
# reverts on every terminal restart unless all four "Disable algorithmic
# trading when/via ..." boxes are cleared, because the startup re-login counts
# as an account change.
#
# The four boxes, in order down the Experts tab:
#   1. ... when the account has been changed      <- why it kept reverting
#   2. ... when the profile has been changed
#   3. ... when the charts symbol or period ...
#   4. ... via external Python API                <- what blocks mt5linux/RPyC
#
# The display argument is the whole point of this file existing separately
# from a hardcoded one: a second account runs its own terminal on its own
# display, and driving :99 to fix :100 sends synthetic clicks into a different
# account's live trading window. That is a repair that does damage.
set -u

DISPLAY_ID="${1:-:99}"
WINDOW_HINT="${2:-}"
export DISPLAY="$DISPLAY_ID"

log () { printf '%s %s\n' "$(date -Is)" "$*"; }

# matchbox is needed for windowactivate: without a window manager there is no
# _NET_ACTIVE_WINDOW and xdotool refuses.
if ! pgrep -f "matchbox-window-manager.*$DISPLAY_ID" >/dev/null 2>&1; then
  if ! pgrep -x matchbox-window-manager >/dev/null 2>&1; then
    matchbox-window-manager -use_titlebar no >/dev/null 2>&1 &
    sleep 3
  fi
fi

visible_dialog () { xdotool search --onlyvisible --name '^Options' 2>/dev/null | head -1; }

open_dialog () {
  local attempt wid
  for attempt in 1 2 3 4 5; do
    [ -n "$(visible_dialog)" ] && { log "dialog already visible"; return 0; }
    if [ -n "$WINDOW_HINT" ]; then
      wid=$(xdotool search --onlyvisible --name "$WINDOW_HINT" 2>/dev/null | head -1)
      [ -n "$wid" ] && xdotool windowactivate "$wid" 2>/dev/null
    fi
    sleep 1
    xdotool mousemove 204 11 click 1; sleep 2      # Tools
    xdotool mousemove 290 240; sleep 1
    xdotool mousemove 290 245; sleep 1              # motion highlights the row
    xdotool click 1; sleep 3                        # Options
    [ -n "$(visible_dialog)" ] && { log "dialog opened on attempt $attempt"; return 0; }
    xdotool key Escape 2>/dev/null; sleep 1
  done
  log "FAILED: Options dialog never became visible on $DISPLAY_ID"
  return 1
}

open_dialog || exit 1

DID=$(visible_dialog)
eval "$(xdotool getwindowgeometry --shell "$DID")"   # sets X, Y, WIDTH, HEIGHT
log "dialog at X=$X Y=$Y ${WIDTH}x${HEIGHT} on $DISPLAY_ID"

# Offsets are relative to the dialog origin, not absolute, so they survive the
# dialog opening in a different place -- which it does.
for dy in 104 129 153 178; do
  xdotool mousemove $((X + 54)) $((Y + dy)); sleep 1; xdotool click 1; sleep 1
done

import -window "$DID" "/tmp/algo_dialog${DISPLAY_ID//:/_}.png" 2>/dev/null \
  || import -window root "/tmp/algo_dialog${DISPLAY_ID//:/_}.png" 2>/dev/null

if [ -n "$(visible_dialog)" ]; then
  xdotool mousemove $((X + 413)) $((Y + 389)); sleep 1; xdotool click 1; sleep 3
  log "OK clicked"
else
  log "WARNING: dialog closed before OK -- settings were not saved"
  exit 1
fi

# Clicking a checkbox that was already clear turns it back ON, so the clicks
# are never proof. Only the terminal's own answer is, and this script cannot
# ask for it -- the caller checks trade_allowed through the bridge.
log "done; verify with terminal_info().trade_allowed on this account's bridge"
