#!/bin/bash
# RPyC bridge for the second terminal, in the same prefix as that terminal.
#
# It must match start_mt5_acc2.sh: the MetaTrader5 Python module talks to
# whichever terminal shares its wineserver, so a bridge in the wrong prefix
# reaches the wrong account -- or none -- while looking correctly configured.
export WINEARCH=win64
export WINEPREFIX=/opt/wine-mt5-acc2
export DISPLAY=:100
export WINEDLLOVERRIDES=mscoree,mshtml=
export WINEDEBUG=-all
# Forward slashes on purpose here: Python on Windows accepts them and they
# survive bash. The backslash form silently became C:mt5rpyc_server2.py and the
# unit restart-looped 365 times while systemd reported it as 'activating'.
exec /usr/bin/wine /opt/wine-mt5-acc2/drive_c/Python311/python.exe C:/mt5/rpyc_server2.py
