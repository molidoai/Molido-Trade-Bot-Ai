"""The backtester can manage trades the way the live bot does.

Live TradeManager moves the stop to entry and closes half at +1R, then trails
the remainder at 1.5 ATR. Every published result was measured with a fixed
stop and a 3R target instead, so the rules that actually trade had never been
tested. These pin the simulated rules to the live ones.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for pkg in ("backtester", "shared", "indicators", "strategies"):
    sys.path.insert(0, str(ROOT / "packages" / pkg))

from molido_backtester.engine import BacktestEngine, _OpenPos
from molido_backtester.costs import CostModel
from molido_shared.types import Candle, TimeFrame

T0 = datetime(2026, 9, 7, 8, tzinfo=timezone.utc)   # a Monday; no rollover crossed


def bar(i, o, h, l, c):
    return Candle(symbol="XAUUSD", timeframe=TimeFrame.H1, open_time=T0 + timedelta(hours=i),
                  open=o, high=h, low=l, close=c, volume=1.0)


def flat_window(n=20, price=100.0):
    return [bar(i, price, price + 1, price - 1, price) for i in range(n)]


def free_costs():
    return CostModel(spread_points=0.0, slippage_points=0.0, commission_per_lot=0.0).for_symbol("XAUUSD")


def engine():
    return BacktestEngine(indicator_engine=None, strategy_engine=None, live_management=True)


def pos(volume=0.10, side="BUY"):
    stop = 90.0 if side == "BUY" else 110.0
    return _OpenPos(side=side, volume=volume, entry_price=100.0, entry_time=T0,
                    stop_loss=stop, take_profit=130.0 if side == "BUY" else 70.0,
                    strategy="TrendFollowing", entry_bar=0, initial_stop_dist=10.0)


def test_off_by_default():
    assert BacktestEngine(indicator_engine=None, strategy_engine=None).live_management is False


def test_below_one_r_nothing_happens():
    p = pos()
    engine()._manage_like_live(p, bar(20, 100, 109, 99, 108), flat_window(), free_costs(), "XAUUSD")
    assert (p.stop_loss, p.volume, p.be_done, p.partial_done) == (90.0, 0.10, False, False)


def test_at_one_r_half_closes_and_stop_goes_to_entry():
    p = pos()
    engine()._manage_like_live(p, bar(20, 100, 111, 99, 100.5), flat_window(), free_costs(), "XAUUSD")
    assert p.be_done and p.partial_done
    assert p.volume == 0.05
    # 0.05 lots banked at exactly +10 on 100 oz a lot = $50, no costs.
    assert abs(p.realized_net - 50.0) < 1e-6
    assert p.stop_loss >= 100.0, "stop must be at entry or trailed above it"


def test_sell_side_mirrors():
    p = pos(side="SELL")
    engine()._manage_like_live(p, bar(20, 100, 101, 89, 99.5), flat_window(), free_costs(), "XAUUSD")
    assert p.partial_done and p.volume == 0.05
    assert abs(p.realized_net - 50.0) < 1e-6
    assert p.stop_loss <= 100.0


def test_minimum_lot_gets_break_even_but_no_partial_or_trail():
    """0.01 cannot be halved: live moves the stop and keeps full size."""
    p = pos(volume=0.01)
    engine()._manage_like_live(p, bar(20, 100, 111, 99, 110), flat_window(), free_costs(), "XAUUSD")
    assert p.be_done and not p.partial_done
    assert p.volume == 0.01 and p.stop_loss == 100.0 and p.realized_net == 0.0


def test_trail_only_ever_tightens():
    e, c, w = engine(), free_costs(), flat_window()
    p = pos()
    e._manage_like_live(p, bar(20, 100, 111, 99, 120), w, c, "XAUUSD")
    tightened = p.stop_loss
    e._manage_like_live(p, bar(21, 120, 121, 105, 106), w, c, "XAUUSD")
    assert p.stop_loss >= tightened, "a falling close must not loosen the stop"


def test_partial_happens_once():
    e, c, w = engine(), free_costs(), flat_window()
    p = pos()
    e._manage_like_live(p, bar(20, 100, 111, 99, 105), w, c, "XAUUSD")
    e._manage_like_live(p, bar(21, 105, 115, 104, 112), w, c, "XAUUSD")
    assert p.volume == 0.05 and abs(p.realized_net - 50.0) < 1e-6
