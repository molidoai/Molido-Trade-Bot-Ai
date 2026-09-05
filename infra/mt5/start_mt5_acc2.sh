#!/bin/bash
# Launch the SECOND MT5 terminal in its own Wine prefix.
#
# The prefix is the whole point. Two terminals sharing one WINEPREFIX share one
# wineserver, and MT5 serves its Python API on a fixed local port (22346) that
# only one of them can own. The second terminal then starts, logs in, looks
# entirely healthy in its own log -- and every mt5.initialize() against it dies
# with "IPC timeout", which says nothing about the real cause. Separate
# prefixes give each terminal its own wineserver and its own API.
export WINEARCH=win64
export WINEPREFIX=/opt/wine-mt5-acc2
export DISPLAY=:100
export WINEDLLOVERRIDES=mscoree,mshtml=
export WINEDEBUG=-all
# Single-quoted, not bare and not forward-slashed. Bare, bash eats the
# backslashes; with forward slashes MT5 truncates the argument at the first
# slash and starts with no config at all -- its log then reads
# 'launched with C:\' and the terminal never signs in.
exec /usr/bin/wine "/opt/wine-mt5-acc2/drive_c/Program Files/MT5-acc2/terminal64.exe" '/config:C:\MT5cfg\start2.ini'
