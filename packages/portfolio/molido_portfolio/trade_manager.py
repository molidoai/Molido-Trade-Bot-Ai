"""Open-trade management: break-even, partial, ATR trail, time stop.

Uses broker modify/close. Never invents prices.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from molido_broker.base import BrokerAdapter
from molido_portfolio.position_manager import PositionManager
from molido_shared.types import TimeFrame

logger = logging.getLogger(__name__)


class TradeManager:
    def __init__(self, broker: BrokerAdapter, positions: PositionManager):
        self.broker = broker
        self.positions = positions
        self._state: dict[str, dict[str, Any]] = {}

    def _st(self, pos) -> dict[str, Any]:
        ticket = str(pos.ticket)
        st = self._state.get(ticket)
        if st is None:
            sl = pos.stop_loss
            entry = pos.entry_price
            stop_dist = abs(entry - sl) if sl is not None and entry else 0.0
            st = {
                "be_done": False,
                "partial_done": False,
                "initial_sl": sl,
                "stop_dist": stop_dist,
                "opened_at": pos.opened_at,
            }
            self._state[ticket] = st
        return st

    @staticmethod
    def r_multiple(side: str, entry: float, price: float, stop_dist: float) -> float | None:
        if stop_dist <= 0 or price is None:
            return None
        if str(side).upper() == "BUY":
            return (price - entry) / stop_dist
        return (entry - price) / stop_dist

    def bars_held(self, pos, candles: Sequence[Any] | None) -> int:
        opened = pos.opened_at
        if opened is None or not candles:
            return 0
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        n = 0
        for c in candles:
            t = getattr(c, "open_time", None)
            if t is None:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t >= opened:
                n += 1
        return n

    async def manage_symbol(
        self,
        symbol: str,
        *,
        candles: Sequence[Any] | None,
        atr: float | None,
        timeframe: TimeFrame | str | None,
        price: float | None,
    ) -> list[str]:
        actions: list[str] = []
        if price is None:
            return actions
        tf = timeframe.value if hasattr(timeframe, "value") else str(timeframe or "")
        is_m15 = tf in ("15m", "M15", "m15", TimeFrame.M15.value if hasattr(TimeFrame, "M15") else "15m")

        for pos in list(self.positions.by_symbol(symbol)):
            st = self._st(pos)
            stop_dist = float(st.get("stop_dist") or 0.0)
            if stop_dist <= 0:
                continue
            r = self.r_multiple(pos.side, pos.entry_price, price, stop_dist)
            if r is None:
                continue

            # 1+2. At +1R: break-even SL to entry, partial close 50%
            if r >= 1.0 and not st["be_done"]:
                ok = await self.broker.modify_position(pos.ticket, sl=pos.entry_price, tp=pos.take_profit)
                if ok:
                    st["be_done"] = True
                    actions.append(f"{symbol} BE SL->{pos.entry_price} ticket={pos.ticket}")
                    logger.info("BE modify ticket=%s sl=%s", pos.ticket, pos.entry_price)
                else:
                    logger.warning("BE modify failed ticket=%s", pos.ticket)

            if r >= 1.0 and not st["partial_done"] and pos.volume > 0:
                half = round(pos.volume * 0.5, 2)
                min_lot = 0.01
                if half >= min_lot and pos.volume - half >= min_lot:
                    res = await self.broker.close_position(pos.ticket, volume=half)
                    ok = getattr(res, "success", False)
                    if ok:
                        st["partial_done"] = True
                        actions.append(f"{symbol} partial 50% ticket={pos.ticket} vol={half}")
                        logger.info("Partial close ticket=%s vol=%s", pos.ticket, half)
                    else:
                        logger.warning("Partial close failed ticket=%s %s", pos.ticket, getattr(res, "message", res))

            # Remainder ATR trail after partial: BUY SL = close - 1.5*ATR
            if st["partial_done"] and atr and atr > 0:
                side = pos.side.upper()
                if side == "BUY":
                    new_sl = price - 1.5 * atr
                    cur = pos.stop_loss if pos.stop_loss is not None else new_sl - 1
                    if new_sl > cur and new_sl < price:
                        ok = await self.broker.modify_position(pos.ticket, sl=new_sl, tp=pos.take_profit)
                        if ok:
                            actions.append(f"{symbol} ATR trail SL={new_sl:.5f}")
                else:
                    new_sl = price + 1.5 * atr
                    cur = pos.stop_loss if pos.stop_loss is not None else new_sl + 1
                    if new_sl < cur and new_sl > price:
                        ok = await self.broker.modify_position(pos.ticket, sl=new_sl, tp=pos.take_profit)
                        if ok:
                            actions.append(f"{symbol} ATR trail SL={new_sl:.5f}")

            # 3. Time stop: M15 not at +0.5R after 8 closed bars
            if is_m15:
                held = self.bars_held(pos, candles)
                if held >= 8 and r < 0.5:
                    res = await self.broker.close_position(pos.ticket)
                    ok = getattr(res, "success", False)
                    actions.append(f"{symbol} time-stop ticket={pos.ticket} bars={held} R={r:.2f} ok={ok}")
                    logger.info("Time stop ticket=%s bars=%s R=%.2f", pos.ticket, held, r)

        live = {str(p.ticket) for p in self.positions.get_all()}
        for t in list(self._state):
            if t not in live:
                self._state.pop(t, None)
        return actions

    async def flatten_all(self, reason: str) -> list[str]:
        actions: list[str] = []
        for pos in list(self.positions.get_all()):
            res = await self.broker.close_position(pos.ticket)
            ok = getattr(res, "success", False)
            actions.append(f"flatten {pos.symbol} ticket={pos.ticket} ok={ok} ({reason})")
            logger.info("Flatten %s ticket=%s ok=%s reason=%s", pos.symbol, pos.ticket, ok, reason)
        await self.positions.sync_from_broker()
        return actions
