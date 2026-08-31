"""Re-anchoring SL/TP from the signal's candle close to the live order price.

Regression cover for MT5 retcode 10016 "Invalid stops": the strategy sets
absolute SL/TP against the last closed candle while the order goes in at the
live bid/ask, so drift between the two can put the stops on the wrong side
of the order -- and even when the broker accepts it, the risk/reward the
position was sized for is no longer the one being traded.
"""

from molido_execution.limit_entry import shift_stops_to_price


def test_stop_distance_is_preserved_exactly():
    """Position size was computed from this distance, so it must not change."""
    entry, sl, tp = 1.35448, 1.353953, 1.355535
    order_price = 1.35478  # price drifted up before the order went in
    # max_drift_r is deliberately wide here: this test is about the maths of
    # the shift, not about the staleness cap (covered separately below).
    new_sl, new_tp, drift, reject = shift_stops_to_price(
        entry, sl, tp, order_price, max_drift_r=99
    )
    assert reject is None
    assert abs((order_price - new_sl) - (entry - sl)) < 1e-9
    assert abs((new_tp - order_price) - (tp - entry)) < 1e-9


def test_buy_stops_stay_on_the_correct_sides():
    entry, sl, tp = 1.35448, 1.353953, 1.355535
    order_price = 1.35470
    new_sl, new_tp, _, reject = shift_stops_to_price(entry, sl, tp, order_price)
    assert reject is None
    assert new_sl < order_price < new_tp


def test_sell_stops_stay_on_the_correct_sides():
    entry, sl, tp = 1.35448, 1.355007, 1.353425   # SELL: sl above, tp below
    order_price = 1.35438                          # ~0.2R drift, inside the cap
    new_sl, new_tp, _, reject = shift_stops_to_price(entry, sl, tp, order_price)
    assert reject is None
    assert new_tp < order_price < new_sl


def test_unshifted_levels_would_have_been_rejected_by_the_broker():
    """The exact failure mode: price runs past the take-profit, so the raw
    levels put TP on the wrong side of the entry."""
    entry, sl, tp = 1.35448, 1.353953, 1.35500
    order_price = 1.35510                      # already beyond the take-profit
    assert not (sl < order_price < tp)          # raw levels -> invalid stops
    new_sl, new_tp, _, reject = shift_stops_to_price(entry, sl, tp, order_price, max_drift_r=99)
    assert new_sl < order_price < new_tp        # shifted levels -> valid again


def test_stale_setup_is_skipped_rather_than_chased():
    entry, sl, tp = 1.35448, 1.353953, 1.355535
    stop_distance = entry - sl                  # ~0.000527
    order_price = entry + stop_distance         # 1.0R away, over the 0.5R cap
    _, _, drift, reject = shift_stops_to_price(entry, sl, tp, order_price, max_drift_r=0.5)
    assert reject is not None
    assert "drifted" in reject
    assert drift > 0


def test_drift_within_tolerance_is_accepted():
    entry, sl, tp = 1.35448, 1.353953, 1.355535
    order_price = entry + 0.4 * (entry - sl)    # 0.4R, inside the 0.5R cap
    _, _, _, reject = shift_stops_to_price(entry, sl, tp, order_price, max_drift_r=0.5)
    assert reject is None


def test_no_take_profit_is_handled():
    new_sl, new_tp, _, reject = shift_stops_to_price(1.35448, 1.353953, None, 1.35470)
    assert reject is None
    assert new_tp is None
    assert new_sl > 1.353953


def test_zero_stop_distance_does_not_divide_or_reject():
    """Degenerate signal: no distance to scale against. Must not crash or
    silently reject everything -- the risk engine rejects zero-stop trades."""
    new_sl, new_tp, drift, reject = shift_stops_to_price(1.35, 1.35, 1.36, 1.3505)
    assert reject is None
    assert drift == 0.0005 or abs(drift - 0.0005) < 1e-9
