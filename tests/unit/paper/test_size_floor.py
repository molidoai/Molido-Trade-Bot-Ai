"""A brain's size preference must not be able to veto an approved trade.

The pipeline floors risk_result.lot_size * size_mult to the broker's lot step.
On the $15,000 prop account the approved size IS the minimum (0.01), so any
multiplier under 1.0 floors it to zero and the trade dies -- while the same
signal filled on the $200,000 account, where there was room to shrink.

The risk engine's approval is the hard limit. The brain's multiplier is a
preference, and a preference that cannot be expressed on this account size
must not become a veto.
"""

import math


def floor_to_step(raw: float, step: float) -> float:
    return round(math.floor(raw / step + 1e-9) * step, 4)


def resulting_lot(approved: float, size_mult: float, step: float, min_lot: float) -> float:
    """The pipeline's rule, as fixed."""
    lot = floor_to_step(approved * min(1.0, size_mult), step)
    if lot < min_lot:
        return min_lot if approved >= min_lot else 0.0
    return lot


def test_prop_account_case_the_fix_was_written_for():
    """Approved 0.01, brain wants half: floors to zero, must become 0.01."""
    assert floor_to_step(0.01 * 0.5, 0.01) == 0.0
    assert resulting_lot(0.01, 0.5, 0.01, 0.01) == 0.01


def test_large_account_still_shrinks_normally():
    """0.09 approved at half is 0.04 -- a real reduction, left alone."""
    assert resulting_lot(0.09, 0.5, 0.01, 0.01) == 0.04


def test_untradeable_account_is_still_skipped():
    """If risk never approved the minimum, nothing rescues the trade."""
    assert resulting_lot(0.0, 0.5, 0.01, 0.01) == 0.0


def test_full_size_is_untouched():
    assert resulting_lot(0.09, 1.0, 0.01, 0.01) == 0.09
    assert resulting_lot(0.01, 1.0, 0.01, 0.01) == 0.01


def test_the_floor_never_exceeds_what_risk_approved():
    """The point of the rule: it can round up to the minimum, never past it."""
    for approved in (0.01, 0.02, 0.05, 0.09, 0.38):
        for mult in (0.1, 0.25, 0.5, 0.75, 1.0):
            got = resulting_lot(approved, mult, 0.01, 0.01)
            assert got <= approved, f"{got} exceeds approved {approved}"


def test_a_multiplier_above_one_cannot_increase_size():
    assert resulting_lot(0.09, 2.0, 0.01, 0.01) == 0.09
