"""A trend strategy whose filters can be switched on and off, so the useful
ones can be identified by measurement instead of by argument.

Every indicator in this codebase was there because someone thought it should
be. None had ever been shown to add anything: the harness loaded four
indicators, silently failed to load ADX at all, and the strategies used
whichever ones they happened to reference. This exists so combinations can be
compared out of sample under identical conditions, and so the answer can be
"fewer indicators" if that is what the data says.

The base signal is deliberately minimal -- a fresh EMA cross with price on the
right side of the fast EMA -- because a filter can only be shown to add value
against something. ATR is not optional: it sets the stop, the target and the
position size, and those are not filters. Everything else is a switch:

    adx_min       trend strength must clear a floor
    htf_ema       price must agree with the 50/200 trend
    rsi_filter    momentum must not be stretched
    macd_confirm  MACD histogram must agree with direction
    bb_filter     entry must not be at the far band
    donchian      price must be near a channel extreme
    sessions      the bar must open inside one of these hour ranges

`sessions` is the only filter here that is not another transformation of the
same price series. ADX, RSI, MACD, Bollinger and Donchian are all functions of
the same OHLC data, so they are correlated views of one thing and combining
them adds less than their number suggests. Hour-of-day is independent
information: liquidity, spread and participation genuinely differ between the
Asian, London and New York sessions, and none of the price-derived indicators
can see that.

Adding switches is cheap and each one narrows the trade set, so a combination
that trades less will often look better on a short sample by luck alone. That
is what the fold count is for: a combination only counts if it holds up across
a majority of independent out-of-sample windows, and ties go to the simpler
one.
"""

from __future__ import annotations

from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide


class EnsembleTrend(Strategy):
    name = "EnsembleTrend"
    strategy_type = "trend"
    allowed_regimes = ["Bull", "Bear", "Strong Bull", "Strong Bear"]

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        atr_sl_mult: float = 1.5,
        rr: float = 3.0,
        min_confidence: float = 0.0,
        fresh_bars: int = 8,
        # --- switchable filters; None or False means "not part of this
        # ensemble", so a combination is described entirely by its arguments.
        adx_min: float | None = None,
        htf_ema: bool = False,
        rsi_filter: bool = False,
        macd_confirm: bool = False,
        bb_filter: bool = False,
        donchian: bool = False,
        # Hour ranges (inclusive start, exclusive end) in the data's own clock.
        # e.g. [(7, 16)] for the London session on a UTC feed.
        sessions: list | None = None,
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
        self.adx_min = adx_min
        self.htf_ema = htf_ema
        self.rsi_filter = rsi_filter
        self.macd_confirm = macd_confirm
        self.bb_filter = bb_filter
        self.donchian = donchian
        self.sessions = sessions

    def _no(self, ctx, why: str) -> StrategySignal:
        return StrategySignal(
            symbol=ctx.symbol, side=SignalSide.NO_TRADE, timeframe=ctx.timeframe,
            strategy_name=self.name, reasons=[why], market_regime=ctx.regime,
        )

    def _ema_tail(self, candles, period: int) -> list[float]:
        """EMA over a bounded tail -- the cross has to be locatable in time,
        and recomputing from bar zero on a growing window is quadratic."""
        k = 2.0 / (period + 1.0)
        span = max(period * 6, self.fresh_bars + period + 20)
        tail = candles[-span:] if len(candles) > span else candles
        out: list[float] = []
        ema = tail[0].close
        for c in tail:
            ema = c.close * k + ema * (1 - k)
            out.append(ema)
        return out

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        candles = ctx.candles
        need = self.slow_period + self.fresh_bars + 5
        if not candles or len(candles) < need:
            return self._no(ctx, f"need {need} bars")
        if ctx.open_position_side is not None:
            return self._no(ctx, "position already open")

        # Checked before anything is computed: it is a lookup, and if the bar
        # is out of session none of the indicator work is needed.
        #
        # CAVEAT worth stating plainly: these hours are whatever clock the
        # candle timestamps are in. This feed comes from the broker, which
        # runs UTC+3, and that offset is exactly the bug that had every live
        # signal acting on three-hour-old prices. So a range tuned here is
        # tuned in broker time, and moving to a differently-offset feed would
        # silently shift every boundary.
        if self.sessions:
            hour = candles[-1].open_time.hour
            if not any(lo <= hour < hi for lo, hi in self.sessions):
                return self._no(ctx, f"hour {hour} outside the traded sessions")

        ind = ctx.indicators
        atr_res = ind.get("ATR") or ind.get("atr14")
        atr = atr_res.get("atr") if atr_res else None
        if not atr or atr <= 0:
            return self._no(ctx, "ATR unavailable")

        fast = self._ema_tail(candles, self.fast_period)
        slow = self._ema_tail(candles, self.slow_period)
        price = candles[-1].close
        up = fast[-1] > slow[-1]

        # Base signal: a *fresh* cross, not the standing state.
        bars_since = None
        for back in range(1, self.fresh_bars + 2):
            if len(fast) <= back:
                break
            if (fast[-1 - back] > slow[-1 - back]) != up:
                bars_since = back
                break
        if bars_since is None:
            return self._no(ctx, f"no cross within {self.fresh_bars} bars")
        if up and price < fast[-1]:
            return self._no(ctx, "price below fast EMA on a bullish cross")
        if not up and price > fast[-1]:
            return self._no(ctx, "price above fast EMA on a bearish cross")

        reasons = [f"EMA cross {bars_since} bars ago"]
        if self.sessions:
            reasons.append(f"hour {candles[-1].open_time.hour} in session")

        if self.adx_min is not None:
            adx_res = ind.get("ADX")
            adx = adx_res.get("adx") if adx_res else None
            if adx is None:
                return self._no(ctx, "ADX unavailable")
            if adx < self.adx_min:
                return self._no(ctx, f"ADX {adx:.1f} < {self.adx_min:.0f}")
            reasons.append(f"ADX {adx:.1f}")

        if self.htf_ema:
            e50 = self._ema_tail(candles, 50)
            e200 = self._ema_tail(candles, 200) if len(candles) > 60 else None
            slow_ref = e200[-1] if e200 else e50[-1]
            if up and not (price > e50[-1] and e50[-1] >= slow_ref):
                return self._no(ctx, "against the 50/200 trend")
            if not up and not (price < e50[-1] and e50[-1] <= slow_ref):
                return self._no(ctx, "against the 50/200 trend")
            reasons.append("aligned with 50/200")

        if self.rsi_filter:
            rsi_res = ind.get("RSI") or ind.get("rsi14")
            rsi = rsi_res.get("rsi") if rsi_res else None
            if rsi is None:
                return self._no(ctx, "RSI unavailable")
            if (up and rsi > 75) or (not up and rsi < 25):
                return self._no(ctx, f"RSI {rsi:.0f} overextended")
            reasons.append(f"RSI {rsi:.0f}")

        if self.macd_confirm:
            macd_res = ind.get("MACD")
            hist = macd_res.get("histogram") if macd_res else None
            if hist is None:
                hist = macd_res.get("hist") if macd_res else None
            if hist is None:
                return self._no(ctx, "MACD unavailable")
            if (up and hist <= 0) or (not up and hist >= 0):
                return self._no(ctx, "MACD disagrees")
            reasons.append("MACD agrees")

        if self.bb_filter:
            bb = ind.get("BollingerBands")
            upper = bb.get("upper") if bb else None
            lower = bb.get("lower") if bb else None
            if upper is None or lower is None:
                return self._no(ctx, "Bollinger unavailable")
            # Do not buy into the top band or sell into the bottom one.
            if (up and price >= upper) or (not up and price <= lower):
                return self._no(ctx, "at the far Bollinger band")
            reasons.append("inside the bands")

        if self.donchian:
            don = ind.get("DonchianChannel") or ind.get("donchian")
            d_up = don.get("upper") if don else None
            d_dn = don.get("lower") if don else None
            if d_up is None or d_dn is None:
                return self._no(ctx, "Donchian unavailable")
            width = d_up - d_dn
            if width <= 0:
                return self._no(ctx, "Donchian degenerate")
            pos = (price - d_dn) / width
            if (up and pos < 0.6) or (not up and pos > 0.4):
                return self._no(ctx, f"not near the channel extreme ({pos:.2f})")
            reasons.append(f"channel position {pos:.2f}")

        if up:
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
            confidence=70.0, score=70.0, reasons=reasons,
            market_regime=ctx.regime,
        )


class EnsembleADXTrend(EnsembleTrend):
    """The ADX-25 + 50/200 combination, wired up so it can be selected live.

    `configure_live` instantiates from the registry with no arguments, so a
    combination can only reach the live engine as a class whose defaults are
    already the combination. That is the whole reason this subclass exists.

    What the evidence actually says, recorded here because it will not be in
    anyone's head in three months: on EURUSD and GBPUSD H1 with raw/ECN costs
    this combination produced PF 1.09 and +1.52 per trade -- but on 30 trades,
    with 9 of its 16 walk-forward folds losing, and it was the best of ten
    combinations tried, which is roughly the number of tries at which one
    winner appears by chance alone. Both of its filters lost money on their
    own. It did not meet the acceptance criteria set before the search began.

    It runs because the account owner chose to run it on a demo account after
    being shown those numbers, which is a legitimate thing to decide. It is
    not evidence of an edge, and a profitable week would not make it one.
    """

    name = "EnsembleADXTrend"

    def __init__(self, adx_min: float = 25.0, htf_ema: bool = True, **kwargs):
        kwargs.pop("sessions", None)
        super().__init__(adx_min=adx_min, htf_ema=htf_ema, **kwargs)
