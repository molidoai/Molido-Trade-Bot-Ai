"""Break-even-only management, tested apart from the 1R scale-out.

The live 1R scale-out (stop to entry, close half, trail) measured worse than a
fixed stop: PF 1.18 vs 1.27 and 10/22 vs 15/22 profitable folds, because it
stopped out winners that would have reached the 3R target. breakeven_at_r is
the gentler candidate: one stop move to entry at a later trigger, no partial,
no trail. These pin that rule so a study measures exactly that and nothing else.
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

T0 = datetime(2026, 9, 7, 8, tzinfo=timezone.utc)


def bar(i, o, h, l, c):
    return Candle(symbol="XAUUSD", timeframe=TimeFrame.H1, open_time=T0 + timedelta(hours=i),
                  open=o, high=h, low=l, close=c, volume=1.0)


def window():
    return [bar(i, 100, 101, 99, 100) for i in range(20)]


def costs():
    return CostModel(spread_points=0.0, slippage_points=0.0, commission_per_lot=0.0).for_symbol("XAUUSD")


def engine(at_r=2.0):
    return BacktestEngine(indicator_engine=None, strategy_engine=None, breakeven_at_r=at_r)


def pos(side="BUY", volume=0.10):
    # entry 100, risk 10 -> 1R at 110 / 90, 2R at 120 / 80, 3R target at 130 / 70
    return _OpenPos(side=side, volume=volume, entry_price=100.0, entry_time=T0,
                    stop_loss=90.0 if side == "BUY" else 110.0,
                    take_profit=130.0 if side == "BUY" else 70.0,
                    strategy="TrendFollowing", entry_bar=0, initial_stop_dist=10.0)


def manage(e, p, b):
    e._manage_like_live(p, b, window(), costs(), "XAUUSD")


def test_off_by_default():
    assert BacktestEngine(indicator_engine=None, strategy_engine=None).breakeven_at_r == 0.0


def test_one_r_is_not_enough_at_a_two_r_trigger():
    """The whole point: 1R must no longer move the stop."""
    p = pos()
    manage(engine(2.0), p, bar(20, 100, 111, 99, 110))
    assert (p.stop_loss, p.be_done) == (90.0, False)


def test_two_r_moves_stop_to_entry():
    p = pos()
    manage(engine(2.0), p, bar(20, 100, 120, 99, 118))
    assert p.stop_loss == 100.0 and p.be_done


def test_no_partial_and_no_trail_ever():
    e, p = engine(2.0), pos()
    manage(e, p, bar(20, 100, 121, 99, 120))
    manage(e, p, bar(21, 120, 128, 119, 127))   # would trail if trailing existed
    assert p.volume == 0.10 and not p.partial_done and p.realized_net == 0.0
    assert p.stop_loss == 100.0, "break-even only: the stop must not trail"


def test_sell_side_mirrors():
    p = pos("SELL")
    manage(engine(2.0), p, bar(20, 100, 101, 81, 82))
    assert (p.stop_loss, p.be_done) == (110.0, False)
    manage(engine(2.0), p, bar(21, 82, 83, 80, 81))
    assert p.stop_loss == 100.0 and p.be_done


def test_minimum_lot_behaves_the_same():
    """No halving involved, so 0.01 gets exactly the same single stop move."""
    p = pos(volume=0.01)
    manage(engine(2.0), p, bar(20, 100, 120, 99, 119))
    assert p.stop_loss == 100.0 and p.volume == 0.01


def test_live_management_takes_precedence():
    """With both set, the existing 1R live rules run unchanged."""
    e = BacktestEngine(indicator_engine=None, strategy_engine=None, live_management=True, breakeven_at_r=2.0)
    p = pos()
    manage(e, p, bar(20, 100, 111, 99, 100.5))
    assert p.partial_done and p.volume == 0.05
