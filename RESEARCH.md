# QUANT FX ALPHA LAB — research log

Status of this project against the brief. Written so the next session can see
what has been measured, what has been refuted, and what is genuinely missing,
without re-deriving any of it.

## §11 Data audit — done, and it bounds everything below

    11 symbols, 50,000 M15 bars each, 2024-08-22 .. 2026-08-28 (~2 years)
    AUDUSD EURGBP EURJPY EURUSD GBPJPY GBPUSD NZDUSD USDCAD USDCHF USDJPY XAUUSD

**DATA NOT AVAILABLE** — stated rather than worked around:

- 17 of the ~28 symbols in the brief, including XAGUSD, EURCHF, AUDNZD,
  and every NZD/CAD cross beyond NZDUSD/USDCAD.
- D1 walk-forward. 50,000 M15 bars is ~520 daily bars; a 1500/500 split
  leaves no folds. H4 gives ~3,100 bars and about 3 folds, which is not a
  fold test.
- The brief's "3 years training / 6 months testing" window (§15). Total
  history is two years, so the实 split used is 1500 train / 500 test on H1,
  giving 22 folds.
- Oil, indices, the dollar index.
- Tick data. Everything is M15 OHLC resampled upward, so intrabar path is
  unknown and stop/target ordering inside a bar is an assumption.

## §12 Backtesting protocol — where we actually are

    IN-SAMPLE        done
    OUT-OF-SAMPLE    done (walk-forward is OOS-only)
    WALK-FORWARD     done, 22 folds per cell on H1
    MONTE CARLO      NOT DONE
    STRESS TEST      NOT DONE
    FORWARD TEST     running live since 2026-09-07 on a demo account

## §10 Costs — a defect found and fixed today

Spread, slippage and commission were charged. **Swap was not charged at all**,
while the surviving candidate holds for tens of hours and crosses one or two
rollovers per trade. Measured on the live terminals: XAUUSD costs 12.6 points
a night long at one broker and 60 at another, against a modelled spread of 25
points paid once. Every profit factor produced before 2026-09-07 is therefore
optimistic, and most optimistic for the strategies that hold longest.

Fixed: `CostModel.swap_cost()` charges by rollovers crossed, counts Wednesday
three times, and preserves sign, so a short on a symbol with positive short
swap is correctly paid rather than charged.

Also fixed: yen-quoted pairs had profit computed as `move * volume * 100_000`
and called dollars, overstating JPY cells by roughly the USDJPY rate. PF and
fold counts shift only ~2% from this (the conversion divides by exit price,
which is nearly constant across a cell), but the currency amounts were wrong
by two orders of magnitude.

## §4 Strategy families — 4 of 8 tested

    Trend following      TESTED   TrendFollowing (EMA cross + price filter)
    Mean reversion       TESTED   RSIMeanReversion
    Breakout             TESTED   DonchianBreakout
    Cross-sectional      TESTED   StrengthReversion — refuted, all variants
    Market structure     NOT TESTED
    Volatility           NOT TESTED
    Carry                NOT TESTED — now possible, swap is modelled
    Statistical / pairs  NOT TESTED

## §23 Current standing

One cell survives both bars on H1 with full history:

    XAUUSD / TrendFollowing / H1    PF 1.38   17/22 folds   267 trades

Re-measured on 4x the data it was admitted on: PF 1.43 -> 1.38 while the fold
rate rose 56% -> 77%. That is confirmation rather than decay.

Two cells pass marginally and are candidates, not findings:

    AUDUSD / RSIMeanReversion    PF 1.05   13/22
    XAUUSD / DonchianBreakout    PF 1.02   12/22

**Selection bias, stated plainly (§13):** two sweeps, 2 of 53 and 2 of 22
cells passed. Both are the rate chance alone produces. Only the XAUUSD cell
has standing, because it was re-measured on independent data and held.

## The two largest gaps, in the brief's own order of importance

**§13/§14 Parameter sensitivity — NOT DONE.** Nothing has tested whether the
surviving cell sits on a plateau or a spike. It uses EMA 9/21, ATR 1.5 stop,
3R target. If neighbouring parameters collapse, it is an overfit artifact and
everything above is noise. This is the single most informative test remaining
and it is the next one run.

**§21 Metrics — INCOMPLETE.** Only net, PF, expectancy and fold count are
produced. Sharpe, Sortino, Calmar, max/average drawdown, recovery factor,
streaks and holding period are not, so §22's composite ranking cannot be
computed honestly yet.

## §24 Honest verdict at this point

Not "NO ROBUST EDGE FOUND", but not far from it. One candidate has survived
out-of-sample replication on 4x data. It has not yet survived: full costs
including the swap that was never charged, parameter perturbation, or Monte
Carlo. Until those three, the correct label is 🟡 RESEARCH FURTHER, not
🟢 DEPLOY CANDIDATE.

---

# 2026-09-08 — costs, sensitivity, and two defects in the measurement itself

## §12 Decisive test — COMPLETE (6 rows, XAUUSD TrendFollowing H1)

| # | arm | n | PF | net | folds |
|---|---|---|---|---|---|
| 1 | control (published 1.38) | 267 | 1.38 | +1310.7 | 17/22 |
| 2 | + real overnight financing | 267 | 1.33 | +1162.4 | 14/22 |
| 3 | + financing + the three brains | 232 | **1.41** | +1187.9 | 15/22 |
| 4 | + financing, close after 12h | 423 | 1.20 | +761.6 | 15/22 |
| 5 | + financing, close after 8h | 530 | 1.18 | +761.7 | 13/22 |
| 6 | + financing, close after 4h | 815 | 1.12 | +580.1 | 11/22 |

Row 1 reproduced the published number exactly, so the harness had not drifted.

Financing costs 0.05 PF and three profitable folds — real, and previously
uncharged. The brains earn it back and more (1.33 → 1.41) on 35 fewer trades,
which answers the standing question of whether the filters are worth their
cost: they are.

Rows 4-6 refute the holding-horizon idea outright. Cutting the hold to avoid
rollover raises trade count and lowers PF monotonically. The strategy needs to
hold; paying the swap is cheaper than exiting early.

## §13/§14 Parameter sensitivity — two axes valid, one invalid

**ATR stop, 5 of 5 pass:** 1.0→1.23, 1.5→1.38, 2.0→1.32, 2.5→1.47, 3.0→1.50.
**Reward ratio, 4 of 4 pass:** 1.5→1.21, 2.0→1.22, 3.0→1.38, 4.0→1.40.

Nine of nine neighbouring settings clear PF>1.0 with more than half the folds
profitable. That is the brief's GREEN FLAG: a plateau, not a spike. The 1.38
is one point on a broad surface rather than a fitted maximum.

**The EMA axis result was an artefact and is void.** It reported n=0 for every
pair except 9/21, which reads exactly like the RED FLAG the brief describes.
It was a bug in the test: `molido_regime/engine.py:43` addresses `ema_9` and
`ema_21` by name, so sweeping MultiEMA to other periods removed those keys,
the regime came back unclassified, and TrendFollowing — which only trades
Bull/Bear — never entered. Zero trades is not a strategy failing; a fragile
edge still trades and still loses. Re-running with 9/21 always published for
the regime engine and the swept pair added on top.

## §10/§11 Costs — the assumption was optimistic by 4x

Live spreads sampled from an open session (RoboForex ECN, median of 12):

| symbol | assumed in every backtest above | measured live |
|---|---|---|
| XAUUSD | 1.2 | **5.0** |
| EURUSD | — | 2.0 |

So every PF above is computed against roughly a quarter of the real spread.
The numbers are internally comparable but optimistic in absolute terms, and
the queued studies now read `live_spreads.json` instead.

**FundedNext is a different instrument commercially.** Its XAUUSD spread is
**52-53 points against RoboForex's 5-6** — the same quote, ten times the toll,
and about 43x what these backtests assumed. On 267 trades the spread
difference alone exceeds the entire net profit several times over. The prop
account is connected and armed at the operator's explicit instruction, with
its cap raised to 60 and the prop floor armed at 13500, but the arithmetic
says this strategy cannot pay for that spread. Finding an instrument whose
cost structure suits that broker is the open question, not tuning this one.

## Defects found in the platform (not the strategy)

1. **The candle cache never expired.** No timestamp, no TTL, no invalidation.
   Its only reader is the H1 trend filter behind Brain1Setup's hard veto, so
   the veto was judging live signals against hours-old bars: 30 of 30 XAUUSD
   entries refused as "against H1 filter (SELL vs BUY)" while the strategy saw
   a fresh up-cross. This is why the bot had never opened a trade.
2. **`compute_latest` recomputed every indicator over all history, per bar.**
   O(n²): one study row took about an hour, which is what made a 15-cell sweep
   impractical. Now bounded to ten times the longest lookback, proven to
   produce identical output at 1e-6 and identical study results (267 trades,
   PF 1.38, +1310.7, 17/22 — unchanged).
3. **`max_spread_points` was unreachable.** Two different hardcoded caps (20 in
   risk, 30 in execution) and no setting reached either. Now per account.
4. **`prop_initial_balance: 0` silently disables the prop loss floor** rather
   than meaning "no limit". The challenge account was fully configured with
   its hard protection inert.

## §24 Verdict, updated

Still 🟡 RESEARCH FURTHER, but the case is stronger than yesterday. The
candidate now survives full costs including swap, and sits on a parameter
plateau on both axes tested honestly. What it has not survived: the real
spread (the plateau was measured at 1.2, not 5.0), Monte Carlo, stress
testing, and the EMA axis re-run. No 🟢 until at least the first of those.
