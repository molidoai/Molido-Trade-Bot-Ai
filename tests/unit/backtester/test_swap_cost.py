"""Overnight financing.

The cost model charged spread, slippage and commission but not swap, while the
one validated edge holds positions for tens of hours and so crosses one or two
rollovers per trade. Measured on the live terminals, XAUUSD costs 12.6 points a
night to hold long at MetaQuotes and 60 at RoboForex-ECN, against a modelled
spread of 25 points paid once -- so for a two-night hold the missing cost was
several times the cost being counted, and every profit factor was optimistic in
proportion to how long the strategy held.
"""

from datetime import datetime, timezone

from molido_backtester import CostModel


def _cm(**kw):
    base = dict(point_size=0.01, contract_size=100.0,
                swap_long_points=-60.0, swap_short_points=19.0)
    base.update(kw)
    return CostModel(**base)


def d(day, hour=12):
    # 2024-01-01 is a Monday, so weekday arithmetic in the tests is legible.
    return datetime(2024, 1, day, hour, tzinfo=timezone.utc)


def test_a_trade_closed_the_same_day_pays_nothing():
    """Charging by elapsed hours would bill an intraday trade; brokers bill
    rollovers, and an intraday trade crosses none."""
    assert _cm().swap_cost("BUY", 1.0, d(1, 9), d(1, 17)) == 0.0


def test_two_hours_across_midnight_is_still_one_night():
    """23:00 to 01:00 lives two hours and crosses one rollover. Dividing
    elapsed time by 24 would call it zero."""
    c = _cm().swap_cost("BUY", 1.0, d(1, 23), d(2, 1))
    assert c == 60.0          # 60 points * 0.01 * 100 * 1 lot * 1 night


def test_a_long_is_charged_and_a_short_is_paid():
    """Sign matters: this broker pays to hold XAUUSD short, and treating that
    as a cost would hide the strategies it actually suits."""
    long_cost = _cm().swap_cost("BUY", 1.0, d(1), d(2))
    short_cost = _cm().swap_cost("SELL", 1.0, d(1), d(2))
    assert long_cost > 0
    assert short_cost < 0
    assert short_cost == -19.0


def test_wednesday_is_charged_three_times():
    """Wednesday carries the weekend. 2024-01-03 is a Wednesday."""
    one_night_tue = _cm().swap_cost("BUY", 1.0, d(2), d(3))
    one_night_wed = _cm().swap_cost("BUY", 1.0, d(3), d(4))
    assert one_night_tue == 60.0
    assert one_night_wed == 180.0


def test_cost_scales_with_volume_and_nights():
    one = _cm().swap_cost("BUY", 1.0, d(1), d(2))
    two_lots = _cm().swap_cost("BUY", 2.0, d(1), d(2))
    two_nights = _cm().swap_cost("BUY", 1.0, d(1), d(3))
    assert two_lots == 2 * one
    assert two_nights == 2 * one


def test_zero_swap_settings_change_nothing():
    """Existing callers that never set swap must behave exactly as before."""
    c = CostModel(point_size=0.01, contract_size=100.0)
    assert c.swap_cost("BUY", 1.0, d(1), d(5)) == 0.0


def test_for_symbol_carries_swap_and_uses_the_metal_contract_size():
    """XAUUSD is quoted per 100 units. Inheriting the FX 100,000 would
    overstate gold's financing by a factor of a thousand."""
    base = CostModel(swap_long_points=-60.0, swap_short_points=19.0)
    gold = base.for_symbol("XAUUSD")
    assert gold.swap_long_points == -60.0
    assert gold.contract_size == 100.0
    fx = base.for_symbol("EURUSD")
    assert fx.contract_size == 100_000.0
