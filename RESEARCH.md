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

## §10/§11 Costs — CORRECTION: the assumption was *pessimistic*, not optimistic

**This section originally recorded the opposite of the truth and is corrected
here rather than deleted.** It said the gold studies assumed 1.2 points while
reality was 5.0, and therefore that every PF above was optimistic. Both halves
were wrong, because the number those studies passed in was never used:
`CostModel.for_symbol` replaced the spread of any XAU symbol with a hardcoded
25 points. The tell was the regime test and decisive row 2 returning identical
net profit to the decimal while nominally differing in spread.

So every gold result above was measured at **25 points against a live quote of
5-6** — roughly four times the real cost. The edge is understated, not
overstated. It also means no spread sensitivity study on gold measured
anything, and FundedNext's 52 is about twice the tested cost rather than the
43x claimed below.

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

---

# 2026-09-08 (later) — sensitivity complete, and the first risk numbers

## §13/§14 Parameter sensitivity — COMPLETE, 15 of 15 pass

| axis | settings tested | passed | PF range |
|---|---|---|---|
| EMA pair (corrected) | 5/13, 7/17, 9/21, 12/26, 15/34, 20/50 | **6/6** | 1.34 – 1.40 |
| ATR stop | 1.0, 1.5, 2.0, 2.5, 3.0 | **5/5** | 1.23 – 1.50 |
| Reward ratio | 1.5, 2.0, 3.0, 4.0 | **4/4** | 1.21 – 1.40 |

Every neighbouring setting on every axis clears PF > 1.0 with more than half
the folds profitable. This is the brief's GREEN FLAG in its strongest form:
the result is a property of the surface, not of a chosen point.

The corrected EMA axis is worth contrasting with the void one. Buggy, it read
"1 of 6 pass, PF range 0.00 – 1.38" — a textbook parameter spike, and grounds
under §13 to reject the candidate outright. Fixed, it reads 6 of 6, PF 1.34 –
1.40. Same market, same strategy; the entire difference was that the regime
engine addresses `ema_9`/`ema_21` by name. A test can invert a conclusion.

## §21 Metrics — first complete set, live configuration

XAUUSD H1, out-of-sample trades only, spread 5.0, swap −60/+19, regime gate
open, $15,000 starting equity — i.e. exactly what the bot is running:

```
trades 574   PF 1.16   net +1685.2   win rate 29.6%   expectancy +2.94
avg win +71.4   avg loss −25.9
MAX DRAWDOWN 5.64%   avg drawdown 1.59%   total return +11.23%
Sharpe 1.26   Sortino 2.15   Calmar 1.99   Recovery 1.99
longest losing streak 13   longest winning streak 4
```

**Max drawdown 5.64% against the prop floor of 10%** — it survives, on this
path. Three things temper that:

1. It is one ordering of 574 trades. Sequence is luck, and 5.64 against 10 is
   not a wide margin. §16 Monte Carlo is the test that answers it and is
   running now.
2. A 13-trade losing run happened. At 0.25% risk that is ~3.3%, survivable,
   but it is a real observed streak and not a tail scenario.
3. A 29.6% win rate means seven trades in ten lose. The edge is entirely in
   the 2.8:1 ratio of average win to average loss. That is arithmetically
   sound and psychologically punishing, and the operator should expect it.

## §10 Costs — swap dominates, and it is directional

Measured per lot per night on the live terminals:

| | RoboForex | FundedNext |
|---|---|---|
| XAUUSD long | −$60.00 | −$57.94 |
| XAUUSD short | **+$19.00** | −$15.70 |
| XAUUSD spread | $9 | $51 |
| triple-swap day | Wednesday | Wednesday |

One night of long carry costs 6.7x the entire spread, and Wednesday triples
it to −$180. For a strategy holding tens of hours, financing is the dominant
cost, not spread — and it is asymmetric by $79/lot/night between directions,
while the strategy scores both sides identically. Whether the edge survives
only on the short side is queued as its own test.

FundedNext is structurally worse on both axes at once: 5.7x the spread and a
short side that pays instead of earning. That is the case against running this
particular strategy there, and it does not depend on the erroneous 43x claim
retracted above.

## §24 Verdict

🟡 RESEARCH FURTHER, close to 🟢. Now survives: full costs including swap,
out-of-sample walk-forward, a complete parameter plateau, and a first
drawdown measurement inside the prop floor. Still missing: Monte Carlo
(running), stress testing, and any forward record at all — the bot has yet to
open its first trade.

---

# 2026-09-08 (evening) — first live trade, and the carry surprise

## The bot opened its first position

XAUUSD SELL 0.09 lots at 4391.69, stop 4417.69, target 4313.56 — risk $234
against a $703 target, the 3R the strategy is built on. It arrived after the
stale-cache fix removed the veto that had refused every signal, and it sized
exactly as the risk engine intends: high-volatility regime, 0.25x multiplier,
$200,000 x 0.5% x 0.25 = $250 budget / $2,600 per lot = 0.09.

## §16 Monte Carlo — COMPLETE (10,000 resamples)

| stress | median dd | p95 | p99 | worst | breaches the 10% floor |
|---|---|---|---|---|---|
| reshuffled | 5.67% | 8.87% | 10.59% | 15.82% | **1.81%** |
| reshuffled, omit 10% | 5.52% | 8.76% | 10.38% | 14.75% | 1.53% |
| reshuffled, **costs +50%** | 8.26% | 12.40% | 14.24% | 18.43% | **22.25%** |
| worst 5% dealt first | 15.45% | 17.61% | 19.05% | 22.87% | 100% |

The historical 5.64% was not luck: the resampled median is 5.67%. Sequence
risk is real but bounded — under two percent of orderings end the challenge.

**The strategy is robust to luck and fragile to cost.** A 50% cost increase
takes the breach rate from 1.81% to 22.25%. That single row is the most
decision-relevant number produced all day, and it is what makes the prop
account's spread a structural problem rather than a preference: FundedNext
quotes 52 points against RoboForex's 5, which is an order of magnitude past
the stress that already breaches one run in five.

The last row is a bound, not a probability — dealing the worst 5% of trades
first is adversarial, not random — but it says plainly that a bad opening run
ends this challenge, and openings are exactly when a challenge is thinnest.

## §19 Multi-symbol at real measured costs

```
XAUUSD  267 trades  spread 5.0  PF 1.34  net +1215.8  17/22  PASS
EURUSD  289 trades  spread 2.0  PF 0.61  net -2477.8   4/22  FAIL
```

EURUSD is not marginal, it is refuted: it loses twice what gold makes, on
more trades, in 18 of 22 folds. Gold-only is a measured conclusion.

## The carry result, which inverts the obvious guess

RoboForex charges gold longs 60 points a night and pays shorts 19 — a
$79/lot/night gap, tripled on Wednesdays, against a $9 spread. Financing, not
spread, is the dominant cost for a strategy holding tens of hours, and it is
directional while the strategy is not. The obvious inference was that the
edge should live on the short side.

Measured out-of-sample with that financing charged:

```
both sides   267 trades   PF 1.34   net +1215.8   win 33.3%
BUY only     185 trades   PF 1.53   net +1254.1   win 37.8%
SELL only     82 trades   PF 0.97   net   -38.3   win 23.2%
```

The longs carry the entire result **while paying the expensive side of the
carry**, and the shorts lose money **while being paid to hold**. Whatever the
edge is, it is not carry, and it is strong enough on the long side to absorb
$60 a night.

**Held as a hypothesis, not a finding.** The split was chosen after seeing the
data; 82 short trades at PF 0.97 is not distinguishable from 1.0; and with two
sides and 22 folds an accident of this size is unremarkable. A fold-level
consistency check is running before anything is dropped. Worth noting against
the current live position, which is a short.

## Defect found today, and the reason it nearly cost a conclusion

`BacktestTrade` had no `swap` field. Financing was computed at all three close
paths and subtracted into `pnl_net`, but never recorded, so the long/short
study printed "total financing charged: -0.0" and read exactly as though swap
had not been applied. The conclusion above was nearly discarded over a missing
dataclass field. Costs that cannot be attributed get re-derived wrongly.

## §24 Verdict

🟡 RESEARCH FURTHER, and now with a forward record of one open trade.

Survives: full costs, out-of-sample walk-forward, a 15-of-15 parameter
plateau, drawdown inside the prop floor, and Monte Carlo resampling.

Does not yet survive: a cost structure meaningfully worse than RoboForex's,
which is what the prop account is. Still missing: a forward record of any
length, and confirmation that the long-side asymmetry is real.

---

# 2026-09-13 — the long-side "edge" was gold's direction

The fold-level test (BUY beat SELL in 15 of 20 folds, no single trade carrying
it) looked like a strategy property. It was tested once more against the
boring explanation before anything was changed, and the boring explanation
won.

Gold rose **+87.9%** across the sample (2373 → 4458). Splitting folds by what
gold itself did in each window:

| gold in the window | BUY won | SELL won |
|---|---|---|
| rose | 11 | 1 |
| fell | 4 | 4 |

When gold fell the two sides split evenly, and in the steepest decline
(−10.6%) shorts made +198.6 while longs lost −85.9. The asymmetry is the
market's trend over two years, not the strategy. Restricting to longs would
have fitted that trend and inverted in the first sustained gold decline.

**Decision: both directions stay.** The PF 1.53 long-only figure is withdrawn
as a candidate improvement.

## Found while reviewing the first live week: live exits were never tested

TradeManager moves the stop to entry and closes half the position at +1R,
then trails the remainder at 1.5 ATR. The backtester had none of this —
every published result (PF 1.38, the 15/15 plateau, Monte Carlo) assumed a
fixed stop and a 3R target. In the first live week two winners reached
+1.93R and +2.04R of favourable excursion and banked about +0.9R each.

The backtester now has `live_management=True`, mirroring TradeManager, so the
validated exits and the live exits can be compared on identical signals.

## Result: the live exits fail the acceptance bar

Identical signals, live configuration (open regime gate, the three brains,
spread 5.0, swap −60/+19), XAUUSD H1 walk-forward, out-of-sample only. Only
exit management differs:

| exits | trades | PF | net | win | profitable folds |
|---|---|---|---|---|---|
| fixed stop, 3R target (tested) | 380 | **1.27** | **+1343.1** | 32.4% | **15/22** |
| BE + half at 1R + 1.5 ATR trail (live) | 474 | 1.18 | +795.1 | 27.0% | **10/22** |

The management that was trading live **loses 41% of the net and drops to 10
of 22 profitable folds — below the "more than half" bar every candidate has
had to clear.** It trades more (474 vs 380) because early exits free the
single position slot sooner, and each extra trade is weaker: moving the stop
to entry turns winners that would have run into break-even exits that lose
the spread, and banking half at 1R caps exactly the tail the strategy's
3:1 payoff depends on.

The validated edge exists only with the tested exits. Live management is to
follow them.
