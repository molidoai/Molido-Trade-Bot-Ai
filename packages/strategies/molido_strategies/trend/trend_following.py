"""
Trend Following strategy – classic EMA crossover + trend filter.
"""

from __future__ import annotations
from molido_shared.types import TimeFrame
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide


class TrendFollowingStrategy(Strategy):
    name = "TrendFollowing"
    strategy_type = "trend"
    default_timeframe = TimeFrame.H1
    allowed_regimes = ["Bull", "Bear", "Strong Bull", "Strong Bear"]
    risk_profile = "normal"

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        atr_sl_mult: float = 1.5,
        # 3.0, not 2.0, on walk-forward evidence rather than preference.
        # At 2.0 the target sits exactly at the strategy's own breakeven: the
        # measured out-of-sample win rate is 33.6% and 2.0 needs 33.3%, which
        # is why pre-cost expectancy came out at -2.9 across 330 trades --
        # zero to within rounding -- and every penny of friction went straight
        # to the loss. At 3.0 the same entries produce +528 pre-cost across
        # 203 trades and 11 of 20 folds in profit against 7 of 20.
        #
        # It wins under all four cost models tested, not just the favourable
        # ones, so this is not a knife-edge fit. It is still only validated on
        # EURUSD H1, and the result only clears PF 1.0 on a raw/ECN cost
        # structure -- on the current model it is 0.95, better but still short.
        rr: float = 3.0,
        min_confidence: float = 55.0,
        **kwargs,
    ):
        super().__init__(
            fast_period=fast_period,
            slow_period=slow_period,
            atr_sl_mult=atr_sl_mult,
            rr=rr,
            min_confidence=min_confidence,
            **kwargs,
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_sl_mult = atr_sl_mult
        self.rr = rr
        self.min_confidence = min_confidence

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        if not self.is_regime_allowed(ctx.regime):
            return self._no_trade(ctx, f"Regime {ctx.regime} not allowed")

        # Expect indicators already computed by the engine
        multi = ctx.indicators.get("MultiEMA") or ctx.indicators.get("ema")
        atr_res = ctx.indicators.get("ATR") or ctx.indicators.get("atr14")
        rsi_res = ctx.indicators.get("RSI") or ctx.indicators.get("rsi14")

        if multi is None:
            return self._no_trade(ctx, "MultiEMA not available")

        ema_fast = multi.get(f"ema_{self.fast_period}") or multi.get("ema_9")
        ema_slow = multi.get(f"ema_{self.slow_period}") or multi.get("ema_21")
        if ema_fast is None or ema_slow is None:
            return self._no_trade(ctx, "EMA values missing")

        if not ctx.candles:
            return self._no_trade(ctx, "No candles")

        price = ctx.candles[-1].close
        atr = atr_res.get("atr") if atr_res else None
        rsi = rsi_res.get("rsi") if rsi_res else None

        # --- Entry logic ---
        bullish = ema_fast > ema_slow and price > ema_fast
        bearish = ema_fast < ema_slow and price < ema_fast

        if ctx.open_position_side is not None:
            # Simple exit: opposite cross
            if ctx.open_position_side.value == "BUY" and bearish:
                return StrategySignal(
                    symbol=ctx.symbol,
                    side=SignalSide.EXIT,
                    timeframe=ctx.timeframe,
                    strategy_name=self.name,
                    entry=price,
                    confidence=70.0,
                    reasons=["EMA bearish cross – exit long"],
                    market_regime=ctx.regime,
                )
            if ctx.open_position_side.value == "SELL" and bullish:
                return StrategySignal(
                    symbol=ctx.symbol,
                    side=SignalSide.EXIT,
                    timeframe=ctx.timeframe,
                    strategy_name=self.name,
                    entry=price,
                    confidence=70.0,
                    reasons=["EMA bullish cross – exit short"],
                    market_regime=ctx.regime,
                )
            return self._hold(ctx, "Position open – waiting for exit signal")

        reasons: list[str] = []
        confidence = 50.0

        if bullish:
            reasons.append(f"EMA{self.fast_period} > EMA{self.slow_period}")
            reasons.append("Price above fast EMA")
            confidence += 15
            if rsi is not None and 40 <= rsi <= 70:
                reasons.append(f"RSI supportive ({rsi:.1f})")
                confidence += 10
            if atr is not None and atr > 0:
                sl = price - self.atr_sl_mult * atr
                tp = price + self.rr * (price - sl)
                confidence = min(confidence, 95.0)
                if confidence < self.min_confidence:
                    return self._no_trade(ctx, f"Confidence {confidence:.0f} < threshold")
                return StrategySignal(
                    symbol=ctx.symbol,
                    side=SignalSide.BUY,
                    timeframe=ctx.timeframe,
                    strategy_name=self.name,
                    entry=price,
                    stop_loss=round(sl, 6),
                    take_profit=round(tp, 6),
                    confidence=confidence,
                    score=confidence,
                    reasons=reasons,
                    market_regime=ctx.regime,
                    risk_reward=self.rr,
                )

        if bearish:
            reasons.append(f"EMA{self.fast_period} < EMA{self.slow_period}")
            reasons.append("Price below fast EMA")
            confidence += 15
            if rsi is not None and 30 <= rsi <= 60:
                reasons.append(f"RSI supportive ({rsi:.1f})")
                confidence += 10
            if atr is not None and atr > 0:
                sl = price + self.atr_sl_mult * atr
                tp = price - self.rr * (sl - price)
                confidence = min(confidence, 95.0)
                if confidence < self.min_confidence:
                    return self._no_trade(ctx, f"Confidence {confidence:.0f} < threshold")
                return StrategySignal(
                    symbol=ctx.symbol,
                    side=SignalSide.SELL,
                    timeframe=ctx.timeframe,
                    strategy_name=self.name,
                    entry=price,
                    stop_loss=round(sl, 6),
                    take_profit=round(tp, 6),
                    confidence=confidence,
                    score=confidence,
                    reasons=reasons,
                    market_regime=ctx.regime,
                    risk_reward=self.rr,
                )

        return self._hold(ctx, "No trend alignment")
