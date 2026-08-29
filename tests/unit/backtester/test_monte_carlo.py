from molido_backtester.monte_carlo import monte_carlo


def test_monte_carlo_warns_on_ruin():
    rs = [-2.0] * 30  # heavy losing sequence
    result = monte_carlo(rs, n_paths=80, ruin_threshold=0.95, seed=1)
    assert result.n_trades == 30
    assert result.ruin_hit is True
    assert "WARNING" in result.warning
    assert "auto-resize" in result.warning.lower() or "human" in result.warning.lower()


def test_monte_carlo_empty():
    result = monte_carlo([], n_paths=10)
    assert result.ruin_hit is False
    assert result.n_trades == 0
