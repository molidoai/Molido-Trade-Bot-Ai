"""for_symbol must not overwrite a spread the caller measured.

It used to: any XAU symbol had its spread replaced by a hardcoded 25, so every
gold backtest measured 25 points whatever its cost model said. The tell was
two studies that differed only in spread returning byte-identical net profit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "backtester"))

from molido_backtester.costs import CostModel


def test_explicit_gold_spread_is_kept():
    assert CostModel(spread_points=5.0).for_symbol("XAUUSD").spread_points == 5.0
    assert CostModel(spread_points=52.0).for_symbol("XAUUSD").spread_points == 52.0


def test_unspecified_gold_spread_falls_back_to_the_metals_default():
    """A caller that expressed no opinion still gets a sane metals number."""
    assert CostModel().for_symbol("XAUUSD").spread_points == CostModel.XAU_DEFAULT_SPREAD_POINTS


def test_fx_spread_is_untouched():
    assert CostModel(spread_points=2.0).for_symbol("EURUSD").spread_points == 2.0


def test_contract_and_point_still_specialise():
    xau = CostModel(spread_points=5.0).for_symbol("XAUUSD")
    assert xau.point_size == 0.01 and xau.contract_size == 100.0
    jpy = CostModel(spread_points=2.0).for_symbol("USDJPY")
    assert jpy.point_size == 0.01
    eur = CostModel(spread_points=2.0).for_symbol("EURUSD")
    assert eur.point_size == 0.0001 and eur.contract_size == 100_000.0


def test_a_different_spread_changes_the_fill():
    """The point of the fix: the number has to reach the price."""
    cheap = CostModel(spread_points=5.0).for_symbol("XAUUSD")
    dear = CostModel(spread_points=52.0).for_symbol("XAUUSD")
    assert dear.entry_cost_price("BUY", 4400.0) > cheap.entry_cost_price("BUY", 4400.0)
