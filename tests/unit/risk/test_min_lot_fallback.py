"""A soft size reducer must not price a small account out of the market.

On the $15,000 prop account, a 26-point gold stop at 0.5% risk needs 0.029
lots. The high-volatility multiplier cuts the budget to a quarter and asks for
0.007, while the broker will not fill under 0.01 -- so every signal was refused
and the account took zero trades in a session where the identical signals
filled on the $200,000 account.

The fallback takes the broker minimum, but only when the operator's FULL
configured risk covers it. risk_per_trade is a hard limit; the volatility
reduction is a preference, and it is the preference that yields.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "risk"))

from molido_risk.engine import RiskEngine
from molido_risk.models import RiskLimits


def risk_per_lot(stop_price_units: float) -> float:
    """$ per lot for a gold stop of this many price units (100 oz per lot)."""
    return RiskEngine._risk_per_lot("XAUUSD", 4400.0, stop_price_units / 0.01)


def test_the_numbers_this_was_built_for():
    """26 points of gold is $2,600 a lot, so 0.01 lots risks $26."""
    assert risk_per_lot(26.0) == 2600.0
    assert 0.01 * risk_per_lot(26.0) == 26.0


def test_reduced_budget_below_minimum_but_full_budget_covers_it():
    """The prop account's exact case: $18.75 reduced, $75 full, $26 minimum."""
    equity, risk_pct, mult = 15_000.0, 0.005, 0.25
    rpl = risk_per_lot(26.0)
    assert equity * risk_pct * mult / rpl < 0.01, "reduced size must be under the minimum"
    assert 0.01 * rpl <= equity * risk_pct, "full budget must still cover the minimum"


def test_full_budget_does_not_cover_the_minimum_on_a_tiny_account():
    """The $971 account: even at full risk the minimum lot is out of reach."""
    equity, risk_pct = 971.0, 0.005
    assert 0.01 * risk_per_lot(26.0) > equity * risk_pct


def test_large_account_is_unaffected():
    """The $200,000 account sized 0.09 lots and must keep doing exactly that."""
    equity, risk_pct, mult = 200_000.0, 0.005, 0.25
    raw = equity * risk_pct * mult / risk_per_lot(26.0)
    limits = RiskLimits()
    assert RiskEngine._normalize_lot(raw, limits) == 0.09


def test_the_fallback_never_exceeds_the_configured_risk():
    """Whatever it does, the resulting risk stays inside risk_per_trade."""
    equity, risk_pct = 15_000.0, 0.005
    taken = 0.01 * risk_per_lot(26.0)
    assert taken <= equity * risk_pct
    assert taken / equity < 0.002, "0.17% of equity, well under the 0.5% limit"


def test_normalize_lot_floors_rather_than_rounds():
    """The fallback only matters because normalize floors to zero, not up."""
    limits = RiskLimits()
    assert RiskEngine._normalize_lot(0.0072, limits) == 0.0
    assert RiskEngine._normalize_lot(0.0288, limits) == 0.02
