# GainaAlgo v2 Alpha

An **original** Pine Script v6 implementation of a visual BUY/SELL + risk/reward
concept for TradingView. It reproduces the *observable behaviour* described in
the specification — large signal labels, forward-extending risk/reward zones,
TP/SL status — and is **not** derived from, copied from, or a reverse-engineering
of any proprietary script.

## Files

| File | Type | Use it for |
|---|---|---|
| `GainaAlgo_v2_Alpha.pine` | `indicator()` | Chart visuals, dashboard, **all six `alertcondition()` alerts** |
| `GainaAlgo_v2_Alpha_Strategy.pine` | `strategy()` | Strategy Tester (the "Strategy Mode") |

Why two files: Pine does not allow `alertcondition()` inside a `strategy()`
script, and does not allow orders inside an `indicator()`. The strategy file is
generated from the indicator, so the signal engine and risk logic are identical;
only the header, order placement, and dashboard differ.

## Install

1. TradingView → **Pine Editor** → *New* → paste a file → **Save** → **Add to chart**.
2. For alerts: *Alerts* → *Create* → condition **GA v2α** → pick BUY / SELL /
   STRONG BUY / STRONG SELL / TP HIT / SL HIT, or **Any alert() function call**
   for the full dynamic message.

## How a signal is formed

A signal needs **all** of:

1. A **trigger** on the confirmed bar — a fresh close beyond the previous
   `donLen`-bar channel (breakout), or a rejection candle (wick ≥ 50% of range,
   close in the favourable third).
2. **Score ≥ minimum** (default 70).
3. **Volatility inside band** — ATR / 50-bar ATR average between 0.7 and 2.5.
4. **Momentum agreement** — RSI on the right side of 50, or MACD histogram moving the right way.
5. **Trend or reversal** — price on the right side of EMA 200, *or* the trigger was a rejection candle.
6. `barstate.isconfirmed`, cooldown elapsed, and no conflicting signal on the same bar.

No single indicator can fire a signal.

### Score (0–100)

| Component | Points | Measured by |
|---|---|---|
| Trend | 25 | close vs EMA200 (10), EMA50 vs EMA200 (10), EMA50 slope (5) |
| Momentum | 20 | RSI vs 50 (8), MACD hist sign (6), hist direction (6) |
| Market structure | 15 | break of last confirmed swing (15) or higher low / lower high (8) |
| Volatility | 15 | ATR ratio inside band |
| Breakout / reversal | 15 | channel breakout (15) or rejection candle (10) |
| MTF confirmation | 10 | previous completed HTF close vs HTF EMA |

The raw score is normalised by the maximum available, so turning MTF off does
not lower every score by 10. **STRONG** = score ≥ 85.

## Risk model

- **Entry** = close of the confirmed signal bar.
- **Stop** — `ATR`: entry ∓ ATR(14) × 1.5 · `Swing`: last confirmed swing ± 0.1 ATR
  (falls back to ATR if no valid swing) · `Hybrid`: swing if its distance is
  between 0.5 and 3 ATR, otherwise ATR.
- **Take profit** = entry ± risk × RR (default 2.0).
- States: `ACTIVE` → `TP HIT` / `SL HIT` / `EXPIRED` (default 100 bars).
- If one bar touches **both** TP and SL, the result is recorded as **SL** —
  the order inside a bar cannot be known from OHLC, so the conservative outcome is used.

## Non-repaint design

| Rule | Implementation |
|---|---|
| Final signal only on closed bars | every signal condition includes `barstate.isconfirmed` |
| No self-comparison | breakout channel is `ta.highest(high, n)[1]` |
| MTF without future data | `request.security(..., close[1], lookahead = barmerge.lookahead_on)` — the previous *completed* HTF bar |
| MTF misuse guard | MTF is ignored unless its timeframe is higher than the chart's |
| Pivots | `ta.pivothigh/low(len, len)` values are used only from the bar they are reported, i.e. after the `len`-bar confirmation delay |
| Frozen levels | entry/SL/TP are stored once in a `Setup` object and never recalculated |
| Status | TP/SL/expiry resolution also runs only on confirmed bars, starting the bar after the signal |

Live, a signal therefore appears **at the close** of its bar, never mid-bar,
and never disappears afterwards.

## Strategy Mode

- Fills at the signal bar's close (`process_orders_on_close = true`) so the tester
  entry equals the drawn entry. **Real fills will be slightly worse.**
- One position at a time; each box on the chart corresponds to exactly one tester trade.
- Position size = `Risk per trade %` of equity ÷ (|entry − SL| × point value).
- Defaults: 0.02% commission, 1 tick slippage, $10,000 capital. **Set these to
  your broker's real costs** — results on low-timeframe FX and gold are very
  sensitive to them.
- The tester's own TP/SL fill model is authoritative. The indicator's dashboard
  statistics are cost-free and use the conservative both-hit rule, so they will
  differ somewhat from the Strategy Tester.

## Honest limitations

- **No performance is claimed.** Nothing in this package has been run through
  the Strategy Tester; defaults are reasonable starting values, not optimised
  ones. Evaluate on your own symbols, timeframes and costs, and prefer
  out-of-sample periods you did not look at while choosing settings.
- The same default parameters are used for every asset and timeframe by design
  (spec §17). That favours robustness over looking good on any single chart.
- `Maximum displayed setups` removes the oldest drawings, including any still
  active, once the limit is exceeded.
- TradingView limits scripts to 500 boxes/labels/lines; with two boxes and up to
  four labels per setup, keep the maximum ≤ 100.
