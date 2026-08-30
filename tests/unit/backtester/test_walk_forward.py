from datetime import datetime, timedelta, timezone
from pathlib import Path

from molido_shared.types import Candle, TimeFrame
from molido_backtester import walk_forward, CostModel
from molido_backtester.walk_forward import WalkForwardResult


def _candles(n=48):
    t0 = datetime(2024, 1, 3, 13, 0, tzinfo=timezone.utc)
    p = 1.085
    out = []
    for i in range(n):
        o = p
        c = p + (0.00012 if i % 4 else -0.00008)
        out.append(
            Candle(
                "EURUSD", TimeFrame.M15, t0 + timedelta(minutes=15 * i),
                o, max(o, c) + 0.00015, min(o, c) - 0.00015, c, 50,
            )
        )
        p = c
    return out


def test_walk_forward_smoke():
    result = walk_forward(
        _candles(48),
        "EURUSD",
        TimeFrame.M15,
        train_bars=24,
        test_bars=8,
        warmup=16,
        cost_model=CostModel(spread_points=1.2, commission_per_lot=7.0),
    )
    assert isinstance(result, WalkForwardResult)
    assert result.metrics is not None
    assert any("spread" in n or "commission" in n for n in result.notes)


def test_walk_forward_csv_fixture():
    csv_path = Path(__file__).resolve().parents[2] / "fixtures" / "sample_m15.csv"
    assert csv_path.exists()
    text = csv_path.read_text()
    assert "open" in text and "close" in text
    assert len(text.splitlines()) > 20
