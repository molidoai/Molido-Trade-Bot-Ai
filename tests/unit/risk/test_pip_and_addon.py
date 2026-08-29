"""Pip size by symbol and no-average-down."""

from molido_risk import RiskEngine, RiskLimits, RiskContext, AccountState, RiskDecision


def _account(**kw) -> AccountState:
    d = dict(
        equity=10_000.0,
        balance=10_000.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        peak_equity=10_000.0,
        open_positions=0,
        symbol_exposure={},
        portfolio_risk=0.0,
        account_mode="DEMO",
        open_symbols=[],
        margin_level=800.0,
        free_margin=8_000.0,
    )
    d.update(kw)
    return AccountState(**d)


def test_jpy_pip_size_is_0_01():
    assert RiskEngine._estimate_pip_size("USDJPY", 150.0) == 0.01
    assert RiskEngine._estimate_pip_size("EURJPY", 160.0) == 0.01
    assert RiskEngine._estimate_pip_size("EURUSD", 1.08) == 0.0001
    assert RiskEngine._estimate_pip_size("XAUUSD", 2400.0) == 0.01


def test_jpy_pip_value_not_always_10():
    rpl = RiskEngine._risk_per_lot("USDJPY", 150.0, 1.0)
    assert 5.0 < rpl < 8.0
    eurusd = RiskEngine._risk_per_lot("EURUSD", 1.08, 1.0)
    assert abs(eurusd - 10.0) < 1e-6


def test_no_average_down_denied():
    engine = RiskEngine()
    acc = _account(open_positions=1, open_symbols=["EURUSD"], symbol_exposure={"EURUSD": 20.0}, open_side_by_symbol={"EURUSD": "BUY"})
    ctx = RiskContext(
        symbol="EURUSD",
        side="BUY",
        entry=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        risk_reward=2.0,
        spread_points=1.2,
        account=acc,
        limits=RiskLimits(),
    )
    result = engine.evaluate(ctx)
    assert result.decision == RiskDecision.DENY
    assert "average down" in result.reasons[0].lower()


def test_margin_level_denies():
    engine = RiskEngine()
    acc = _account(margin_level=200.0, free_margin=1000.0)
    ctx = RiskContext(
        symbol="EURUSD",
        side="BUY",
        entry=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        risk_reward=2.0,
        spread_points=1.2,
        account=acc,
        limits=RiskLimits(),
    )
    result = engine.evaluate(ctx)
    assert result.decision == RiskDecision.DENY
    assert "margin" in result.reasons[0].lower()
