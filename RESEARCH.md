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
