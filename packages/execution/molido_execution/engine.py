"""
Execution Engine (Master Prompt §15).

New entries: LIMIT at bid (buy) / ask (sell) with mandatory SL.
MARKET only for flatten / close / time-stop / partial (close_position path).
Never bypass Risk – this layer only runs AFTER Risk ALLOW/REDUCE.
"""

from __future__ import annotations
import asyncio
import logging
from molido_shared.types import OrderRequest, OrderResult, OrderType, Side
from molido_broker.base import BrokerAdapter
from molido_execution.models import ExecRequest, ExecResult, ExecStatus
from molido_execution.limit_entry import entry_limit_price, is_exit_side

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(
        self,
        broker: BrokerAdapter,
        max_slippage_points: float = 10.0,
        max_spread_points: float = 30.0,
        order_timeout_sec: float = 30.0,
        max_retries: int = 2,
    ):
        self.broker = broker
        self.max_slippage_points = max_slippage_points
        self.max_spread_points = max_spread_points
        self.order_timeout_sec = order_timeout_sec
        self.max_retries = max_retries
        self._submitted: dict[str, ExecResult] = {}
        self._lock = asyncio.Lock()

    async def execute(self, req: ExecRequest) -> ExecResult:
        async with self._lock:
            if req.client_order_id in self._submitted:
                logger.info("Idempotent hit for %s", req.client_order_id)
                return self._submitted[req.client_order_id]

            if is_exit_side(req.side, req.reduce_only):
                result = await self._close(req)
                self._submitted[req.client_order_id] = result
                return result

            if not req.stop_loss:
                result = ExecResult(
                    success=False, status=ExecStatus.REJECTED,
                    client_order_id=req.client_order_id,
                    message="stop loss is mandatory", requested_volume=req.volume,
                )
                self._submitted[req.client_order_id] = result
                return result

            tick = await self.broker.get_tick(req.symbol)
            if tick is None:
                result = ExecResult(
                    success=False, status=ExecStatus.REJECTED,
                    client_order_id=req.client_order_id,
                    message=f"No tick for {req.symbol}", requested_volume=req.volume,
                )
                self._submitted[req.client_order_id] = result
                return result

            spread = tick.spread
            point = 0.0001 if tick.mid < 50 else 0.01
            spread_points = spread / point if point else 0
            if spread_points > self.max_spread_points:
                result = ExecResult(
                    success=False, status=ExecStatus.REJECTED,
                    client_order_id=req.client_order_id,
                    message=f"Spread {spread_points:.1f} > max {self.max_spread_points}",
                    requested_volume=req.volume,
                )
                self._submitted[req.client_order_id] = result
                return result

            limit_px = entry_limit_price(req.side, tick)
            if limit_px is None:
                result = ExecResult(
                    success=False, status=ExecStatus.REJECTED,
                    client_order_id=req.client_order_id,
                    message="No bid/ask for LIMIT entry", requested_volume=req.volume,
                )
                self._submitted[req.client_order_id] = result
                return result
            req.order_type = "LIMIT"
            req.price = limit_px
            result = await self._place_with_retry(req, limit_px)
            self._submitted[req.client_order_id] = result
            return result

    async def _place_with_retry(self, req: ExecRequest, ref_price: float) -> ExecResult:
        last_err = ""
        for attempt in range(1, self.max_retries + 2):
            try:
                side = Side.BUY if req.side.upper() == "BUY" else Side.SELL
                otype = OrderType.LIMIT
                if str(req.order_type or "").upper() == "STOP":
                    otype = OrderType.STOP
                broker_req = OrderRequest(
                    symbol=req.symbol, side=side, order_type=otype, volume=req.volume,
                    price=req.price, sl=req.stop_loss, tp=req.take_profit,
                    client_order_id=req.client_order_id,
                    comment=req.comment or f"{req.strategy or 'molido'}", magic=req.magic,
                )
                broker_res: OrderResult = await asyncio.wait_for(
                    self.broker.place_order(broker_req), timeout=self.order_timeout_sec,
                )
                if not broker_res.success:
                    last_err = broker_res.message or "Broker rejected"
                    if not self._is_retryable(last_err) or attempt > self.max_retries:
                        return ExecResult(
                            success=False, status=ExecStatus.REJECTED,
                            client_order_id=req.client_order_id,
                            broker_order_id=broker_res.broker_order_id,
                            message=last_err, requested_volume=req.volume, raw=broker_res.raw,
                        )
                    await asyncio.sleep(0.5 * attempt)
                    continue
                fill = broker_res.fill_price
                slippage = None
                if fill is not None and ref_price:
                    slippage = abs(fill - ref_price)
                    point = 0.0001 if ref_price < 50 else 0.01
                    slip_pts = slippage / point if point else 0
                    if slip_pts > self.max_slippage_points:
                        logger.warning("High slippage %.1f points on %s (still filled)", slip_pts, req.client_order_id)
                status = ExecStatus.FILLED
                if broker_res.filled_volume < req.volume * 0.999:
                    status = ExecStatus.PARTIAL
                return ExecResult(
                    success=True, status=status, client_order_id=req.client_order_id,
                    broker_order_id=broker_res.broker_order_id, fill_price=fill,
                    filled_volume=broker_res.filled_volume, requested_volume=req.volume,
                    slippage=slippage, message=broker_res.message or "OK", raw=broker_res.raw,
                )
            except asyncio.TimeoutError:
                return ExecResult(
                    success=False, status=ExecStatus.UNKNOWN,
                    client_order_id=req.client_order_id,
                    message="Timeout – requires reconciliation", requested_volume=req.volume,
                )
            except Exception as e:
                last_err = str(e)
                logger.exception("Execution error")
                if attempt > self.max_retries:
                    break
                await asyncio.sleep(0.5 * attempt)
        return ExecResult(
            success=False, status=ExecStatus.FAILED,
            client_order_id=req.client_order_id,
            message=last_err or "Execution failed", requested_volume=req.volume,
        )

    async def _close(self, req: ExecRequest) -> ExecResult:
        if req.position_ticket is None:
            return ExecResult(
                success=False, status=ExecStatus.REJECTED,
                client_order_id=req.client_order_id,
                message="EXIT requires position_ticket", requested_volume=req.volume,
            )
        try:
            broker_res = await asyncio.wait_for(
                self.broker.close_position(req.position_ticket, volume=req.volume or None),
                timeout=self.order_timeout_sec,
            )
            if not broker_res.success:
                return ExecResult(
                    success=False, status=ExecStatus.REJECTED,
                    client_order_id=req.client_order_id,
                    broker_order_id=broker_res.broker_order_id,
                    message=broker_res.message, requested_volume=req.volume,
                )
            return ExecResult(
                success=True, status=ExecStatus.FILLED,
                client_order_id=req.client_order_id,
                broker_order_id=broker_res.broker_order_id,
                fill_price=broker_res.fill_price, filled_volume=broker_res.filled_volume,
                requested_volume=req.volume, message=broker_res.message or "Closed",
            )
        except asyncio.TimeoutError:
            return ExecResult(
                success=False, status=ExecStatus.UNKNOWN,
                client_order_id=req.client_order_id,
                message="Close timeout – requires reconciliation", requested_volume=req.volume,
            )
        except Exception as e:
            return ExecResult(
                success=False, status=ExecStatus.FAILED,
                client_order_id=req.client_order_id, message=str(e), requested_volume=req.volume,
            )

    async def cancel(self, client_order_id: str, broker_ticket: str | int | None = None) -> bool:
        if broker_ticket is None:
            cached = self._submitted.get(client_order_id)
            if cached and cached.broker_order_id:
                broker_ticket = cached.broker_order_id
        if broker_ticket is None:
            return False
        return await self.broker.cancel_order(broker_ticket)

    def get_result(self, client_order_id: str) -> ExecResult | None:
        return self._submitted.get(client_order_id)

    @staticmethod
    def _is_retryable(message: str) -> bool:
        msg = message.lower()
        retryable = ["timeout", "temporarily", "busy", "connection", "network", "try again"]
        non_retryable = ["invalid", "rejected", "not enough", "margin", "market closed", "trade disabled"]
        if any(x in msg for x in non_retryable):
            return False
        return any(x in msg for x in retryable)
