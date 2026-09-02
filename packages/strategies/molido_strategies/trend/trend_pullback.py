"""Trend entry as an event, with a graded quality score.

Written after measuring why TrendFollowing has no edge. Its entry is

    bullish = ema_fast > ema_slow and price > ema_fast

which is a *state*: on EURUSD H1 it is true on 70.6% of all bars, against 183
genuine EMA crosses -- 15.2 signal bars per real decision point. That is not an
edge, it is a description of trend direction, and it explains the record far
better than the stop and target settings did. Entering at an arbitrary bar
inside a move, including the exhausted end of one, has close to zero
expectancy, which is exactly what the walk-forward measured: -2.9 across 330
trades before costs.

This strategy keeps the same underlying idea -- trade with the trend -- but
makes four changes, each aimed at one identified weakness:

1. **Event, not state.** The cross must be recent (within `fresh_bars`). A
   trend that has been running for forty bars is not a new signal.

2. **Only trends worth trading.** The EMA separation must exceed a fraction of
   ATR, which rejects the flat, tangled regime where the pair is not trending
   at all and a cross is noise.

3. **Enter on the pullback, not the extension.** Price must be within
   `max_ext_atr` of the fast EMA. Buying after an extended run is buying the
   part of the move that is already over -- and it is where a fixed ATR stop
   is most likely to be hit by ordinary retracement.

4. **A score that actually varies.** TrendFollowing's confidence is 50 + 15 +
   10, so it lands on 75 almost always and min_confidence of 55 filters
   nothing. Here each condition contributes proportionally to how well it is
   met, so the threshold is a real filter and the number means something.

No claim is made that this is better. It is a candidate to be measured against
the incumbent out of sample, on several symbols, with costs charged -- and
rejected if it does not clear PF > 1 with a majority of folds in profit.
"""

from __future__ import annotations

from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide


class TrendPullback(Strategy):
    name = "TrendPullback"
    strategy_type = "trend"
    allowed_regimes = ["Bull", "Bear", "Strong Bull", "Strong Bear"]

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        atr_sl_mult: float = 1.5,
        rr: float = 3.0,
        min_confidence: float = 60.0,
        # How recently the cross must have happened to count as a signal.
        fresh_bars: int = 8,
        # EMA separation below this fraction of ATR means no real trend.
        min_sep_atr: float = 0.25,
        # How far above the fast EMA price may be and still count as a
        # pullback rather than an extension.
        max_ext_atr: float = 1.0,
        **kwargs,
    ):
        super().__init__(
            fast_period=fast_period, slow_period=slow_period,
            atr_sl_mult=atr_sl_mult, rr=rr, min_confidence=min_confidence,
            **kwargs,
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_sl_mult = atr_sl_mult
        self.rr = rr
        self.min_confidence = min_confidence
        self.fresh_bars = fresh_bars
        self.min_sep_atr = min_sep_atr
        self.max_ext_atr = max_ext_atr

    # -- helpers -----------------------------------------------------------
    def _no_trade(self, ctx, why: str) -> StrategySignal:
        return StrategySignal(
            symbol=ctx.symbol, side=SignalSide.NO_TRADE, timeframe=ctx.timeframe,
            strategy_name=self.name, reasons=[why], market_regime=ctx.regime,
        )

    def _emas(self, candles, period: int) -> list[float]:
        """EMA over a bounded tail, so the cross can be located in time.

        The indicator engine returns only the latest value and this strategy
        needs to know *when* the cross happened, so the series is computed
        here. Only the tail is walked: the backtester feeds a growing window,
        and recomputing from bar zero each time made this quadratic -- an A/B
        run that should take minutes was still on its first configuration
        after twelve. An EMA converges geometrically, so seeding a few
        multiples of the period back is indistinguishable from seeding at the
        start, at constant cost per call.
        """
        k = 2.0 / (period + 1.0)
        span = max(period * 6, self.fresh_bars + period + 20)
        tail = candles[-span:] if len(candles) > span else candles
        out: list[float] = []
        ema = tail[0].close
        for c in tail:
            ema = c.close * k + ema * (1 - k)
            out.append(ema)
        return out

    # -- entry -------------------------------------------------------------
    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        candles = ctx.candles
        need = self.slow_period + self.fresh_bars + 5
        if not candles or len(candles) < need:
            return self._no_trade(ctx, f"need {need} bars")

        atr_res = ctx.indicators.get("ATR") or ctx.indicators.get("atr14")
        rsi_res = ctx.indicators.get("RSI") or ctx.indicators.get("rsi14")
        atr = atr_res.get("atr") if atr_res else None
        rsi = rsi_res.get("rsi") if rsi_res else None
        if not atr or atr <= 0:
            return self._no_trade(ctx, "ATR unavailable")

        fast = self._emas(candles, self.fast_period)
        slow = self._emas(candles, self.slow_period)
        price = candles[-1].close

        up_now = fast[-1] > slow[-1]

        # 1. The cross must be recent. Walk back until the ordering flips.
        bars_since = None
        for back in range(1, self.fresh_bars + 2):
            if len(fast) <= back:
                break
            if (fast[-1 - back] > slow[-1 - back]) != up_now:
                bars_since = back
                break
        if bars_since is None:
            return self._no_trade(ctx, f"no cross in last {self.fresh_bars} bars")

        # 2. The trend must be worth trading.
        sep = abs(fast[-1] - slow[-1]) / atr
        if sep < self.min_sep_atr:
            return self._no_trade(ctx, f"EMAs too tangled (sep {sep:.2f} ATR)")

        # 3. Price must not be extended away from the fast EMA.
        ext = abs(price - fast[-1]) / atr
        if ext > self.max_ext_atr:
            return self._no_trade(ctx, f"price extended {ext:.2f} ATR from EMA")

        # Direction must agree with the fresh cross.
        if up_now and price < fast[-1]:
            return self._no_trade(ctx, "bullish cross but price below fast EMA")
        if not up_now and price > fast[-1]:
            return self._no_trade(ctx, "bearish cross but price above fast EMA")

        if ctx.open_position_side is not None:
            return self._no_trade(ctx, "position already open")

        # 4. A score that varies with how well each condition is met.
        reasons = []
        score = 40.0
        fresh = 1.0 - (bars_since - 1) / max(self.fresh_bars, 1)
        score += 20.0 * max(0.0, fresh)
        reasons.append(f"cross {bars_since} bars ago")
        strength = min(1.0, (sep - self.min_sep_atr) / 0.75)
        score += 20.0 * strength
        reasons.append(f"EMA separation {sep:.2f} ATR")
        closeness = 1.0 - min(1.0, ext / self.max_ext_atr)
        score += 15.0 * closeness
        reasons.append(f"{ext:.2f} ATR from EMA")
        if rsi is not None:
            # Momentum agreeing, without being stretched.
            good = (50 <= rsi <= 70) if up_now else (30 <= rsi <= 50)
            if good:
                score += 5.0
                reasons.append(f"RSI {rsi:.0f} supportive")
            elif (rsi > 75 and up_now) or (rsi < 25 and not up_now):
                score -= 15.0
                reasons.append(f"RSI {rsi:.0f} overextended")

        score = max(0.0, min(95.0, score))
        if score < self.min_confidence:
            return self._no_trade(ctx, f"score {score:.0f} < {self.min_confidence:.0f}")

        if up_now:
            sl = price - self.atr_sl_mult * atr
            tp = price + self.rr * (price - sl)
            side = SignalSide.BUY
        else:
            sl = price + self.atr_sl_mult * atr
            tp = price - self.rr * (sl - price)
            side = SignalSide.SELL

        return StrategySignal(
            symbol=ctx.symbol, side=side, timeframe=ctx.timeframe,
            strategy_name=self.name, entry=price,
            stop_loss=round(sl, 6), take_profit=round(tp, 6),
            confidence=score, score=score, reasons=reasons,
            market_regime=ctx.regime,
        )
