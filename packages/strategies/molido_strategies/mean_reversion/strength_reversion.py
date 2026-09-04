"""Fade the most stretched currency pair in the cross-section.

Version two. The first attempt used the cross-pair signal as a time-series
indicator -- "is this pair's own divergence unusual against its own history" --
and scored PF 0.99 where it was built and 0.73 on symbols it had not seen. That
is not a small miss to be tuned away; it is the wrong use of the signal.

The study that motivated this measured a *cross-sectional* relationship: the
rank correlation between euro-minus-dollar strength and the return that
follows, IC about -0.03 against a +-0.01 noise band at every horizon from 4 to
32 bars, with the same sign each time. A signal of that shape says which
instrument is stretched *relative to the others available right now*. Judging
each pair against its own past throws that away and keeps only the weakest part.

So three things changed, each tied to something the measurement actually said:

**Ranked across pairs, not against history.** Every tracked pair's divergence
is computed at the same instant and this one is traded only if it sits at an
extreme of that ranking. "The euro is stretched" is worth little; "of eight
pairs, this is the most stretched" is the claim the IC supports.

**Held for the measured horizon.** The edge was measured 4 to 32 bars ahead and
was strongest at 32. Version one held until a stop or target, which could be
days -- long after the effect that justified entering had decayed. The
backtester now takes `max_hold_bars`, and the live runner closes on the same
rule.

**Both sides, always.** A stretched pair is faded whichever way it is
stretched, so the book does not accumulate one-way currency exposure.

The effect remains small: |IC| near 0.03 explains well under a percent of what
happens next. This is not expected to be large, and if it does not clear PF 1
out of sample on symbols it was not built on, it fails like the others did.
`entry_rank` is fixed at 2 -- trade only the two most stretched pairs -- chosen
before the first run rather than after several.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from molido_strategies.base import Strategy, StrategyContext, StrategySignal, SignalSide

# Which currencies each symbol is made of. Only symbols listed here can be
# ranked; anything else returns no trade rather than guessing at a split.
SYMBOL_CURRENCIES = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"), "NZDUSD": ("NZD", "USD"),
    "USDJPY": ("USD", "JPY"), "USDCAD": ("USD", "CAD"),
    "USDCHF": ("USD", "CHF"), "EURGBP": ("EUR", "GBP"),
    "EURJPY": ("EUR", "JPY"), "GBPJPY": ("GBP", "JPY"),
}


class StrengthReversion(Strategy):
    name = "StrengthReversion"
    strategy_type = "mean_reversion"
    allowed_regimes = ["Bull", "Bear", "Strong Bull", "Strong Bear",
                       "Sideways", "Low Volatility", "High Volatility"]

    _cache: dict[str, dict] = {}

    def __init__(
        self,
        entry_rank: int = 2,
        min_divergence: float = 0.0015,
        atr_sl_mult: float = 2.0,
        rr: float = 1.0,
        max_hold_bars: int = 32,
        series_path: str | None = None,
        **kwargs,
    ):
        super().__init__(entry_rank=entry_rank, min_divergence=min_divergence,
                         atr_sl_mult=atr_sl_mult, rr=rr, **kwargs)
        # How many of the most stretched pairs are tradeable at any instant.
        self.entry_rank = entry_rank
        # A rank is meaningless when nothing is actually stretched: on a quiet
        # bar something is still "most extreme" by a hair. This floor keeps the
        # ranking from manufacturing a signal out of noise.
        self.min_divergence = min_divergence
        self.atr_sl_mult = atr_sl_mult
        self.rr = rr
        self.max_hold_bars = max_hold_bars
        self.series_path = series_path or os.getenv(
            "STRENGTH_SERIES", "/app/data/strength_series.json")
        self._series = self._load(self.series_path)

    @classmethod
    def _load(cls, path: str) -> dict:
        if path in cls._cache:
            return cls._cache[path]
        data: dict = {}
        try:
            with open(path) as fh:
                blob = json.load(fh)
            if blob.get("kind") != "per_currency":
                # An older single-number file cannot be ranked. Refusing is the
                # point: silently falling back to the time-series reading would
                # reproduce the version that failed while looking like this one.
                data = {}
            else:
                data = blob.get("strength", {}) or {}
        except Exception:
            data = {}
        cls._cache[path] = data
        return data

    def _no(self, ctx, why: str) -> StrategySignal:
        return StrategySignal(
            symbol=ctx.symbol, side=SignalSide.NO_TRADE, timeframe=ctx.timeframe,
            strategy_name=self.name, reasons=[why], market_regime=ctx.regime,
        )

    def _divergences(self, when: datetime) -> dict[str, float]:
        """Every tradeable pair's divergence at one instant, for ranking."""
        strengths = self._series.get(when.isoformat())
        if not strengths:
            return {}
        out = {}
        for sym, (base, quote) in SYMBOL_CURRENCIES.items():
            b, q = strengths.get(base), strengths.get(quote)
            if b is None or q is None:
                continue
            out[sym] = b - q
        return out

    def evaluate(self, ctx: StrategyContext) -> StrategySignal:
        candles = ctx.candles
        if not self._series:
            return self._no(ctx, "per-currency strength series unavailable")
        if not candles:
            return self._no(ctx, "no candles")
        if ctx.open_position_side is not None:
            return self._no(ctx, "position already open")
        if ctx.symbol not in SYMBOL_CURRENCIES:
            return self._no(ctx, f"{ctx.symbol} is not in the ranked universe")

        atr_res = ctx.indicators.get("ATR") or ctx.indicators.get("atr14")
        atr = atr_res.get("atr") if atr_res else None
        if not atr or atr <= 0:
            return self._no(ctx, "ATR unavailable")

        divs = self._divergences(candles[-1].open_time)
        if len(divs) < 4:
            return self._no(ctx, "not enough pairs priced at this bar to rank")

        mine = divs.get(ctx.symbol)
        if mine is None:
            return self._no(ctx, "no strength reading for this symbol")
        if abs(mine) < self.min_divergence:
            return self._no(ctx, f"divergence {mine:+.5f} below the floor")

        # Rank by how stretched, regardless of direction: the trade is to fade
        # whichever way the pair has run.
        order = sorted(divs.items(), key=lambda kv: -abs(kv[1]))
        rank = next(i for i, (sym, _) in enumerate(order) if sym == ctx.symbol)
        if rank >= self.entry_rank:
            return self._no(ctx, f"rank {rank + 1} of {len(order)}, not extreme enough")

        price = candles[-1].close
        # Positive divergence means the base has run up against the quote, so
        # the pair has risen and the measured relationship says it unwinds.
        if mine > 0:
            side = SignalSide.SELL
            sl = price + self.atr_sl_mult * atr
            tp = price - self.rr * (sl - price)
        else:
            side = SignalSide.BUY
            sl = price - self.atr_sl_mult * atr
            tp = price + self.rr * (price - sl)

        score = min(95.0, 55.0 + 10.0 * (self.entry_rank - rank))
        return StrategySignal(
            symbol=ctx.symbol, side=side, timeframe=ctx.timeframe,
            strategy_name=self.name, entry=price,
            stop_loss=round(sl, 6), take_profit=round(tp, 6),
            confidence=score, score=score,
            reasons=[f"most stretched #{rank + 1} of {len(order)}, "
                     f"divergence {mine:+.5f}, faded"],
            market_regime=ctx.regime,
        )
