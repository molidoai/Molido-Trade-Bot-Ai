from molido_observability import metrics


def test_metrics_render():
    metrics.orders_total.inc(symbol="EURUSD", side="BUY")
    metrics.equity.set(10000.0)
    metrics.circuit_breaker.set(0)
    text = metrics.render()
    assert "molido_orders_total" in text
    assert "molido_equity" in text


def test_security_check():
    from molido_security import check_env_safety
    report = check_env_safety()
    assert isinstance(report.ok, bool)
    assert isinstance(report.findings, list)


def test_anomaly_stale():
    from datetime import datetime, timezone, timedelta
    from molido_shared.types import Tick
    from molido_anomaly import AnomalyDetector
    det = AnomalyDetector(stale_seconds=5)
    tick = Tick(
        symbol="EURUSD", bid=1.1, ask=1.1001,
        time=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    events = det.check_tick(tick)
    assert any(e.kind == "stale_data" for e in events)
    assert any(e.should_halt_entries for e in events)
