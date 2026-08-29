from molido_broker.latency import probe_tcp, WARN_MS


def test_probe_tcp_records_ms():
    rec = probe_tcp("127.0.0.1", port=1, timeout=0.2)
    assert "ms" in rec
    assert rec["threshold_ms"] == WARN_MS
    assert rec["ok"] is False
