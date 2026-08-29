from molido_strategies import StrategyEngine, DEFAULT_LIVE_STRATEGIES, STRATEGY_REGISTRY


def test_configure_live_enables_only_trendfollowing():
    se = StrategyEngine()
    se.configure_live()
    assert DEFAULT_LIVE_STRATEGIES == ["TrendFollowing"]
    enabled = se.enabled_names()
    assert enabled == ["TrendFollowing"]
    listed = {row["name"]: row["enabled"] for row in se.list_strategies()}
    assert set(listed) == set(STRATEGY_REGISTRY)
    assert listed["DonchianBreakout"] is False
    assert listed["RSIMeanReversion"] is False
    assert listed["TrendFollowing"] is True
