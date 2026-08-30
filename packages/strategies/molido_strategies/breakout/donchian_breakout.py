"""
Donchian Channel Breakout strategy.
"""

from __future__ import annotations
from molido_shared.types import TimeFrame
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide


class DonchianBreakoutStrategy(Strategy):
    name = "DonchianBreakout"
    strategy_type = "breakout"
    default_timeframe = TimeFrame.H1
    allowed_regimes = ["Bull", "Bear", "High Volatility", "Strong Bull", "Strong Bear"]
    risk_profile = "normal"

    def __init__(
        self,
        period: int = 20,
        atr_sl_mult: float = 1.2,
        rr: float = 2.0,
        min_confidence: float = 60.0,
        **kwargs,
    ):
        super().__init__(period=period, atr_sl_mult=atr_sl_mult, rr=rr, min_confidence=min_confidence, **kwargs)
        self.period = period
        self.atr_sl_mult = atr_sl_mult
        self.rr = rr
        self.min_confidence = min_confidence

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        if not self.is_regime_allowed(ctx.regime):
            return self._no_trade(ctx, f"Regime {ctx.regime} not allowed")

        don = ctx.indicators.get("DonchianChannel") or ctx.indicators.get("donchian")
        atr_res = ctx.indicators.get("ATR") or ctx.indicators.get("atr14")

        if don is None or not ctx.candles:
            return self._no_trade(ctx, "Donchian or candles missing")

        upper = don.get("upper")
        lower = don.get("lower")
        if upper is None or lower is None:
            return self._no_trade(ctx, "Donchian bands not ready")

        price = ctx.candles[-1].close
        atr = atr_res.get("atr") if atr_res else None
        if atr is None or atr <= 0:
            return self._no_trade(ctx, "ATR missing")

        if ctx.open_position_side is not None:
            return self._hold(ctx, "Position already open")

        # Breakout above upper → BUY
        if price > upper:
            sl = price - self.atr_sl_mult * atr
            tp = price + self.rr * (price - sl)
            return StrategySignal(
                symbol=ctx.symbol,
                side=SignalSide.BUY,
                timeframe=ctx.timeframe,
                strategy_name=self.name,
                entry=price,
                stop_loss=round(sl, 6),
                take_profit=round(tp, 6),
                confidence=72.0,
                score=72.0,
                reasons=[f"Close above Donchian upper ({upper:.5f})", f"ATR SL x{self.atr_sl_mult}"],
                market_regime=ctx.regime,
                risk_reward=self.rr,
            )

        # Breakout below lower → SELL
        if price < lower:
            sl = price + self.atr_sl_mult * atr
            tp = price - self.rr * (sl - price)
            return StrategySignal(
                symbol=ctx.symbol,
                side=SignalSide.SELL,
                timeframe=ctx.timeframe,
                strategy_name=self.name,
                entry=price,
                stop_loss=round(sl, 6),
                take_profit=round(tp, 6),
                confidence=72.0,
                score=72.0,
                reasons=[f"Close below Donchian lower ({lower:.5f})", f"ATR SL x{self.atr_sl_mult}"],
                market_regime=ctx.regime,
                risk_reward=self.rr,
            )

        return self._hold(ctx, "Price inside Donchian channel")
