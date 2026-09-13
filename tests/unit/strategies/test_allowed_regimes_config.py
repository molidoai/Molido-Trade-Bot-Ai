"""The regime gate must be settable without editing the strategy class.

Measured on XAUUSD H1 walk-forward, opening TrendFollowing to every regime
took the trade count from 267 to 574 and net profit from +1162 to +1570 while
profit factor fell 1.33 -> 1.15. That trade-off is an operator decision, so it
has to live in configuration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "strategies"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "shared"))

from molido_strategies import StrategyEngine
from molido_strategies.trend.trend_following import TrendFollowingStrategy


DEFAULT = ["Bull", "Bear", "Strong Bull", "Strong Bear"]


def test_default_gate_is_unchanged():
    eng = StrategyEngine()
    eng.configure_live(["TrendFollowing"])
    assert eng._strategies["TrendFollowing"].allowed_regimes == DEFAULT
    assert not eng._strategies["TrendFollowing"].is_regime_allowed("Sideways")


def test_override_opens_the_gate():
    eng = StrategyEngine()
    eng.configure_live(["TrendFollowing"],
                       allowed_regimes=DEFAULT + ["Sideways", "Unknown"])
    strat = eng._strategies["TrendFollowing"]
    assert strat.is_regime_allowed("Sideways")
    assert strat.is_regime_allowed("Bull")


def test_override_applies_on_reconfigure_not_just_first_build():
    """The live runner reconfigures every cycle on existing instances."""
    eng = StrategyEngine()
    eng.configure_live(["TrendFollowing"])
    assert not eng._strategies["TrendFollowing"].is_regime_allowed("Sideways")
    eng.configure_live(["TrendFollowing"], allowed_regimes=["Sideways"])
    assert eng._strategies["TrendFollowing"].is_regime_allowed("Sideways")


def test_empty_or_missing_override_leaves_the_class_default():
    eng = StrategyEngine()
    eng.configure_live(["TrendFollowing"], allowed_regimes=[])
    assert eng._strategies["TrendFollowing"].allowed_regimes == DEFAULT


def test_constructor_override_also_works():
    assert TrendFollowingStrategy(allowed_regimes=["Sideways"]).is_regime_allowed("Sideways")


def test_one_strategy_override_does_not_leak_to_another():
    eng = StrategyEngine()
    eng.configure_live(["TrendFollowing"], allowed_regimes=["Sideways"])
    other = eng._strategies.get("DonchianBreakout")
    if other is not None:
        assert other.allowed_regimes != ["Sideways"]
