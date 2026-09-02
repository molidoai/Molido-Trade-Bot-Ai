"""Walk-forward / out-of-sample validation harness.

packages/backtester/walk_forward.py has always been correct -- time-ordered
folds, only trades whose entry falls inside the test window, costs included --
and has never been run by anything. There was no way to ask the question it
answers, so every "improvement" so far has been argued rather than measured.

This is the runner. It splits history into consecutive train/test folds,
reports each fold separately and then the pooled out-of-sample result, and
does the same for several configurations so they can be compared on the only
number that matters: how they did on bars the parameters never saw.

Design notes, all of them deliberate:

* **Nothing is fitted here.** The strategies have fixed parameters, so the
  train window is not used to optimise anything -- it is warmup and nothing
  more. That means these numbers are honest but also conservative: this
  harness cannot flatter a strategy by tuning it. When a future change *does*
  fit parameters, it must fit them on train and be scored on test, and this
  layout already enforces that.

* **Per-fold results are printed, not just the average.** A strategy that
  makes all its money in one fold and loses in the other five is not an edge,
  it is one lucky regime. The spread across folds is the honest signal, and
  averaging it away is how backtests lie.

* **Costs are on.** Spread, slippage and commission are charged, because a
  mid-price backtest of a strategy this active is a fiction -- the live PF of
  0.72 already showed what costs do to it.

Run inside the engine container, which has the packages and the CSVs:

    docker exec -e WF_SYMBOLS=EURUSD molido-engine python3 -u /tmp/wf.py
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime

from molido_shared.types import Candle, TimeFrame
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_backtester.walk_forward import walk_forward
from molido_backtester.costs import CostModel

DATA_DIR = os.getenv("COLLECT_OUT_DIR", "/app/data/historical")

# Fold geometry in bars. On M15, 4000 train / 1000 test is roughly six weeks
# of context scored against a fortnight of unseen bars, repeated down the
# series -- enough folds to see whether an edge is persistent or a one-off.
TRAIN_BARS = int(os.getenv("WF_TRAIN", "4000"))
TEST_BARS = int(os.getenv("WF_TEST", "1000"))
WARMUP = 120


def load(path: str, symbol: str, limit: int | None = None) -> list[Candle]:
    out: list[Candle] = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=TimeFrame.M15,
                    open_time=datetime.fromisoformat(r["time"].replace("Z", "+00:00")),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r.get("volume") or 1),
                    is_closed=True,
                )
            )
    return out[-limit:] if limit else out


def resample(candles: list[Candle], factor: int, timeframe: TimeFrame) -> list[Candle]:
    """Aggregate M15 bars into a larger timeframe.

    Costs are charged per trade, not per bar, so the ratio that decides
    profitability is "move captured per trade" against a fixed ~7.25 of
    friction. On M15 the walk-forward paid 6,906 in costs to lose 7,877 --
    88% of the loss was friction on 953 small trades. A bigger bar is the
    direct test of that: fewer, larger trades against the same per-trade cost.

    Built from the M15 series rather than downloaded so it is provably the
    same underlying data -- a different feed would confound the comparison
    with a different history.
    """
    out: list[Candle] = []
    for i in range(0, len(candles) - factor + 1, factor):
        chunk = candles[i:i + factor]
        if len(chunk) < factor:
            break
        out.append(
            Candle(
                symbol=chunk[0].symbol,
                timeframe=timeframe,
                open_time=chunk[0].open_time,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(c.volume for c in chunk),
                is_closed=True,
            )
        )
    return out


def engines(strategies: list[str]) -> tuple[IndicatorEngine, StrategyEngine]:
    ind = IndicatorEngine()
    # Mirror what the live engine registers. The harness previously loaded
    # four indicators and DonchianBreakout needs DonchianChannel, so it got
    # None and returned no trade every single bar -- zero trades in twenty
    # folds, reported as "no edge" when it had never been given its inputs.
    for name, kw in (
        ("MultiEMA", {}),
        ("RSI", {"period": 14}),
        ("ATR", {"period": 14}),
        ("MACD", {}),
        ("BollingerBands", {"period": 20}),
        ("DonchianChannel", {"period": 20}),
        ("Supertrend", {"period": 10, "multiplier": 3.0}),
    ):
        try:
            ind.add_from_registry(name, **kw)
        except Exception:
            pass
    strat = StrategyEngine()
    try:
        strat.configure_live(strategies)
    except Exception:
        pass
    return ind, strat


def pf_of(gross_profit: float, gross_loss: float) -> float:
    return (gross_profit / gross_loss) if gross_loss else float("inf")


def report(label: str, res) -> dict:
    m = res.metrics
    pf = pf_of(m.gross_profit, m.gross_loss)
    exp = (m.net_profit / m.total_trades) if m.total_trades else 0.0

    print(f"\n--- {label} ---")
    print(f"  folds: {len(res.folds)}   out-of-sample trades: {m.total_trades}")

    # Per fold, because the spread across folds is the honest signal.
    profitable = 0
    for i, f in enumerate(res.folds, 1):
        fm = f.oos.metrics
        fpf = pf_of(fm.gross_profit, fm.gross_loss)
        n = fm.total_trades
        if n == 0:
            print(f"   fold {i:2d}: no trades")
            continue
        if fm.net_profit > 0:
            profitable += 1
        print(
            f"   fold {i:2d}: n={n:4d}  win={fm.win_rate:5.1f}%  "
            f"net={fm.net_profit:+9.2f}  PF={fpf:5.2f}"
        )

    print(
        f"  POOLED OOS: win={m.win_rate:.1f}%  net={m.net_profit:+.2f}  "
        f"PF={pf:.2f}  expectancy={exp:+.2f}/trade"
    )
    print(f"  costs paid: commission {m.total_commission:.2f} + slippage {m.total_slippage:.2f}")
    print(f"  folds in profit: {profitable}/{len(res.folds)}")
    return {"label": label, "pf": pf, "net": m.net_profit, "n": m.total_trades,
            "folds": len(res.folds), "profitable": profitable}


# M15 bars per bar of the target timeframe, with fold geometry scaled so each
# timeframe is judged over a comparable stretch of real time rather than a
# comparable number of bars.
TIMEFRAMES = [
    ("M15", 1, TimeFrame.M15, 4000, 1000),
    ("H1", 4, TimeFrame.H1, 1000, 250),
    ("H4", 16, TimeFrame.H4, 250, 60),
]


def main() -> None:
    symbols = (os.getenv("WF_SYMBOLS") or "EURUSD").split(",")
    limit = int(os.getenv("WF_BARS", "20000"))

    # Configurations to compare. Each must justify itself out of sample; a
    # config that only wins in-sample is exactly what this harness exists to
    # catch.
    # Each strategy alone by default. The combinations were useless: the
    # backtester runs max_open=1, so TrendFollowing takes the only slot and
    # the other two never get to trade -- all three "configs" returned
    # byte-identical results, which is how the combination runs went unnoticed
    # as meaningless. Only a strategy tested on its own has been tested at all.
    default_cfg = "TrendFollowing,RSIMeanReversion,DonchianBreakout"
    # Judge each strategy in a regime it is actually allowed to trade in.
    # Live computes the regime per bar; testing a mean-reversion strategy
    # under a trend regime it explicitly excludes measures nothing.
    REGIME_FOR = {
        "TrendFollowing": "Bull",
        "DonchianBreakout": "Bull",
        "RSIMeanReversion": "Sideways",
    }
    configs = [(name.strip(), [name.strip()], REGIME_FOR.get(name.strip(), "Bull"))
               for name in (os.getenv("WF_STRATEGIES") or default_cfg).split(",") if name.strip()]

    costs = CostModel(spread_points=1.2, slippage_points=0.5, commission_per_lot=7.0)

    # M15's verdict is already in (0/16 folds, PF 0.58), and re-running it
    # costs hours that H1/H4 need. WF_TF lets a run skip straight to the
    # timeframes still in question.
    wanted = [x.strip().upper() for x in (os.getenv("WF_TF") or "").split(",") if x.strip()]
    frames = [t for t in TIMEFRAMES if not wanted or t[0].upper() in wanted]

    for symbol in symbols:
        symbol = symbol.strip()
        path = os.path.join(DATA_DIR, f"{symbol}_M15.csv")
        if not os.path.exists(path):
            print(f"skip {symbol}: no data at {path}")
            continue
        candles = load(path, symbol, limit)
        print(f"\n=== {symbol}: {len(candles)} bars, "
              f"train={TRAIN_BARS} test={TEST_BARS} (costs on) ===")

        rows = []
        for tf_name, factor, tf, train, test in frames:
            bars = candles if factor == 1 else resample(candles, factor, tf)
            if len(bars) < train + test:
                print("  %s: only %d bars, need %d -- skipped" % (tf_name, len(bars), train + test))
                continue
            print("########## %s (%d bars, train=%d test=%d) ##########" % (tf_name, len(bars), train, test))
            for label, strategies, regime in configs:
                ind, strat = engines(strategies)
                res = walk_forward(
                    bars, symbol, tf,
                    train_bars=train, test_bars=test, warmup=min(WARMUP, train // 4),
                    cost_model=costs, indicator_engine=ind, strategy_engine=strat,
                    regime=regime,
                )
                row = report("%s / %s [%s]" % (tf_name, label, regime), res)
                # Cost share is the number that explains M15: 88% of the loss
                # there was friction, so track it per timeframe.
                m = res.metrics
                row["cost"] = m.total_commission + m.total_slippage
                row["per_trade_cost"] = (row["cost"] / m.total_trades) if m.total_trades else 0.0
                rows.append(row)

        print("=== %s VERDICT ===" % symbol)
        for r in sorted(rows, key=lambda x: -x["pf"]):
            verdict = "EDGE" if r["pf"] > 1.0 and r["profitable"] > r["folds"] / 2 else "no edge"
            gross = r["net"] + r.get("cost", 0.0)
            print("  %-34s PF=%5.2f  n=%5d  net=%+9.1f  pre-cost=%+9.1f  cost/trade=%5.2f  %d/%d folds  -> %s" % (
                r["label"], r["pf"], r["n"], r["net"], gross,
                r.get("per_trade_cost", 0.0), r["profitable"], r["folds"], verdict))
        print("")
        print("  EDGE requires PF > 1 AND profit in more than half the folds.")
        print("  pre-cost shows whether the entry has any edge before friction;")
        print("  if pre-cost is negative too, a bigger bar will not save it and")
        print("  the entry logic itself is what needs replacing.")


if __name__ == "__main__":
    main()
