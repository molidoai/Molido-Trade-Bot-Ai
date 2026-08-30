"""
Mean Reversion using RSI extremes + Bollinger.
"""

from __future__ import annotations
from molido_shared.types import TimeFrame
from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide


class RSIMeanReversionStrategy(Strategy):
    name = "RSIMeanReversion"
    strategy_type = "mean_reversion"
    default_timeframe = TimeFrame.M15
    allowed_regimes = ["Sideways", "Low Volatility"]
    risk_profile = "conservative"

    def __init__(
        self,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        atr_sl_mult: float = 1.0,
        rr: float = 1.5,
        min_confidence: float = 60.0,
        **kwargs,
    ):
        super().__init__(
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
            atr_sl_mult=atr_sl_mult,
            rr=rr,
            min_confidence=min_confidence,
            **kwargs,
        )
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_sl_mult = atr_sl_mult
        self.rr = rr
        self.min_confidence = min_confidence

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        if not self.is_regime_allowed(ctx.regime):
            return self._no_trade(ctx, f"Regime {ctx.regime} not ideal for mean reversion")

        rsi_res = ctx.indicators.get("RSI") or ctx.indicators.get("rsi14")
        bb = ctx.indicators.get("BollingerBands") or ctx.indicators.get("bb")
        atr_res = ctx.indicators.get("ATR") or ctx.indicators.get("atr14")

        if rsi_res is None or not ctx.candles:
            return self._no_trade(ctx, "RSI or candles missing")

        rsi = rsi_res.get("rsi")
        if rsi is None:
            return self._no_trade(ctx, "RSI not ready")

        price = ctx.candles[-1].close
        atr = atr_res.get("atr") if atr_res else None
        lower = bb.get("lower") if bb else None
        upper = bb.get("upper") if bb else None

        if ctx.open_position_side is not None:
            return self._hold(ctx, "Position open")

        # Oversold + near/below lower band → BUY
        if rsi <= self.rsi_oversold:
            reasons = [f"RSI oversold ({rsi:.1f})"]
            conf = 65.0
            if lower is not None and price <= lower * 1.001:
                reasons.append("Price at/below Bollinger lower")
                conf += 10
            if atr and atr > 0:
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
                    confidence=min(conf, 90.0),
                    score=min(conf, 90.0),
                    reasons=reasons,
                    market_regime=ctx.regime,
                    risk_reward=self.rr,
                )

        # Overbought + near/above upper band → SELL
        if rsi >= self.rsi_overbought:
            reasons = [f"RSI overbought ({rsi:.1f})"]
            conf = 65.0
            if upper is not None and price >= upper * 0.999:
                reasons.append("Price at/above Bollinger upper")
                conf += 10
            if atr and atr > 0:
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
                    confidence=min(conf, 90.0),
                    score=min(conf, 90.0),
                    reasons=reasons,
                    market_regime=ctx.regime,
                    risk_reward=self.rr,
                )

        return self._hold(ctx, "RSI in neutral zone")
