# Changelog

## 2.0.0-alpha — 2026-09-13

First release.

### Added
- Pine Script v6 indicator `GainaAlgo_v2_Alpha.pine`:
  - weighted 0–100 signal score (trend 25, momentum 20, structure 15,
    volatility 15, breakout/reversal 15, optional MTF 10), normalised when MTF is off
  - BUY / SELL and STRONG BUY / STRONG SELL labels on confirmed bars only
  - risk and reward zones that extend forward until TP, SL or expiry
  - ATR / Swing / Hybrid stop modes; RR-based take profit
  - compact info box (Entry, TP, SL, RR, Score) with individual show/hide toggles
  - `ACTIVE`, `TP ✓`, `SL ✕`, `EXPIRED` states; configurable history limit (default 20)
  - six `alertcondition()` alerts plus a dynamic `alert()` message with symbol,
    timeframe, signal, entry, SL, TP, RR and score
  - dashboard with resolved count, TP/SL/expired, win rate, average R
- Strategy companion `GainaAlgo_v2_Alpha_Strategy.pine` generated from the
  indicator: risk-%-sized entries, fixed SL/TP exits, expiry close, dashboard
  with total trades, wins/losses, win rate, profit factor, net profit, max
  drawdown, average R and expectancy.

### Design decisions
- Two files because Pine forbids `alertcondition()` in strategies and orders in indicators.
- A bar touching both TP and SL is recorded as SL (conservative).
- MTF uses the previous completed higher-timeframe bar and is ignored if the
  selected timeframe is not higher than the chart's.
