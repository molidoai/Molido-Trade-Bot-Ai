from molido_strategies import StrategyEngine
from molido_strategies.engine import parse_symbol_strategies


def test_parse_symbol_strategies_accepts_lists_and_strings():
    m = parse_symbol_strategies({
        "xauusd": ["TrendFollowing"],
        "EURUSD": "RSIMeanReversion, DonchianBreakout",
        "USDCAD": [],
        "": ["TrendFollowing"],
        "GBPUSD": 42,
    })
    assert m == {
        "XAUUSD": {"TrendFollowing"},
        "EURUSD": {"RSIMeanReversion", "DonchianBreakout"},
        "USDCAD": set(),
    }
    assert parse_symbol_strategies(None) == {}
    assert parse_symbol_strategies("nope") == {}


def test_symbol_map_restricts_only_mapped_symbols():
    se = StrategyEngine()
    se.configure_live(["TrendFollowing", "RSIMeanReversion", "DonchianBreakout"])
    se.configure_symbol_map({"XAUUSD": {"TrendFollowing"}, "USDCAD": set()})
    assert se.allowed_for("XAUUSD") == ["TrendFollowing"]
    assert se.allowed_for("usdcad") == []
    # Unmapped symbol keeps every enabled strategy, so old deployments are unchanged.
    assert set(se.allowed_for("EURUSD")) == {"TrendFollowing", "RSIMeanReversion", "DonchianBreakout"}
    # Map only narrows: a name in the map that is not enabled stays off.
    se.configure_symbol_map({"EURUSD": {"TrendPullback"}})
    assert se.allowed_for("EURUSD") == []
