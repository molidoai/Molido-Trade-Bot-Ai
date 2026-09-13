"""Pre-market check. Builds the request in the REMOTE process.

MetaTrader5.order_check takes a dict, and a dict handed across an RPyC classic
boundary arrives as a netref the MT5 extension refuses ("Unnamed arguments not
allowed"). So the request is constructed and the call made on the far side,
and only the scalar result comes back.
"""
import os, sys
import rpyc

host = os.getenv("MT5_BRIDGE_HOST", "172.18.0.1")
try:
    c = rpyc.classic.connect(host, 8001)
except Exception as e:
    print("BRIDGE UNREACHABLE via %s: %s" % (host, e)); sys.exit(1)

mt5 = c.modules["MetaTrader5"]
ti, ai = mt5.terminal_info(), mt5.account_info()
print("terminal connected : %s" % getattr(ti, "connected", None))
print("trade_allowed      : %s" % getattr(ti, "trade_allowed", None))
print("account            : %s (%s)" % (getattr(ai, "login", "?"), getattr(ai, "server", "?")))
print("equity / free      : %.2f / %.2f" % (getattr(ai, "equity", 0), getattr(ai, "margin_free", 0)))

SYM = "XAUUSD"
c.execute("import MetaTrader5 as _m")
c.execute("_m.symbol_select(%r, True)" % SYM)
si = mt5.symbol_info(SYM)
t = mt5.symbol_info_tick(SYM)
pt = float(getattr(si, "point", 0.01) or 0.01)
sp_pts = float(getattr(si, "spread", 0) or 0)
print("%s bid/ask       : %s / %s" % (SYM, t.bid, t.ask))
print("spread             : %s points = %.2f price (registry modelled 0.25, "
      "broker was 0.29)" % (int(sp_pts), sp_pts * pt))

c.execute(
    "_req = {'action': _m.TRADE_ACTION_DEAL, 'symbol': %r, 'volume': %r, "
    "'type': _m.ORDER_TYPE_BUY, 'price': _m.symbol_info_tick(%r).ask, "
    "'deviation': 20, 'magic': 0, 'comment': 'premarket', "
    "'type_time': _m.ORDER_TIME_GTC, 'type_filling': _m.ORDER_FILLING_IOC}"
    % (SYM, float(getattr(si, "volume_min", 0.01) or 0.01), SYM)
)
rc = c.eval("(lambda r: (r.retcode, r.comment) if r else (None, str(_m.last_error())))(_m.order_check(_req))")
retcode, comment = rc[0], rc[1]
print()
print("order_check        : retcode=%s (%s)" % (retcode, comment))
if retcode == 0:
    print("VERDICT: the broker WOULD accept an order. Ready to trade.")
else:
    print("VERDICT: orders would be REFUSED -- fix this before the open.")
    sys.exit(1)
