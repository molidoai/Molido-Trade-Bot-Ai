"""
MetaTrader 5 Broker Adapter.

Official MetaTrader5 package needs a running terminal (Windows or Wine).
Trading Engine only talks to BrokerAdapter - never to MT5 directly.
Stop-loss is mandatory on every new order.
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Any

from molido_shared.types import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    Candle,
    OrderRequest,
    OrderResult,
    Side,
    SymbolInfo,
    Tick,
    TimeFrame,
    OrderType,
)
from molido_broker.base import BrokerAdapter

logger = logging.getLogger(__name__)

import os

# One MetaTrader5 terminal serves exactly one logged-in account, so a
# multi-account deployment runs several terminals, each with its own RPyC
# bridge on its own port. Connections are therefore cached per (host, port)
# -- a single module-level connection would silently route every account's
# orders to whichever terminal happened to connect first.
_MT5_CONNECTIONS: dict[tuple[str, int], object] = {}
MT5_BACKEND = "none"


def _load_mt5(host: str | None = None, port: int | None = None):
    """Return the MT5 facade for one bridge, or None if unreachable."""
    global MT5_BACKEND
    host = host or os.getenv("MT5_RPC_HOST", "127.0.0.1")
    port = int(port or os.getenv("MT5_RPC_PORT", "8001"))
    key = (host, port)
    cached = _MT5_CONNECTIONS.get(key)
    if cached is not None:
        return cached
    try:
        import rpyc
        class _RpycMT5:
            def __init__(self, host: str, port: int):
                self._conn = rpyc.classic.connect(host, port)
                self._conn._config["sync_request_timeout"] = 30
                self._conn.execute("import MetaTrader5 as mt5")

            def _unwrap(self, res):
                if res is None:
                    return None
                try:
                    return rpyc.classic.obtain(res)
                except Exception:
                    asdict = getattr(res, "_asdict", None)
                    if asdict:
                        data = dict(asdict())
                        obj = type("MT5Obj", (), {})()
                        for k, v in data.items():
                            setattr(obj, k, v)
                        return obj
                    try:
                        out = []
                        for item in res:
                            ad = getattr(item, "_asdict", None)
                            if ad:
                                o = type("MT5Obj", (), {})()
                                for k, v in dict(ad()).items():
                                    setattr(o, k, v)
                                out.append(o)
                            else:
                                out.append(item)
                        return out
                    except Exception:
                        return res

            # MetaTrader5 request dicts cannot cross RPyC as arguments: the C
            # extension rejects a netref with (-2, "Unnamed arguments not
            # allowed"). Verified against the live bridge 2026-08-31 --
            # rpyc.classic.deliver() does NOT help, and neither does building
            # the dict remotely and passing it back through a locally-held
            # function reference. The whole call has to be evaluated inside the
            # remote interpreter, with the dict reconstructed there from JSON.
            _DICT_ARG_FUNCS = ("order_send", "order_check")

            def _call_with_dict(self, name, request):
                import json as _json
                self._conn.execute("import json as _molido_json")
                expr = "mt5." + name + "(_molido_json.loads(" + repr(_json.dumps(request)) + "))"
                return self._unwrap(self._conn.eval(expr))

            def __getattr__(self, name):
                if name.startswith(("ORDER_", "TRADE_", "TIMEFRAME_", "POSITION_")):
                    return self._conn.eval("int(mt5." + name + ")")
                if name in self._DICT_ARG_FUNCS:
                    def _dict_call(request, *rest, **kw):
                        if isinstance(request, dict) and not rest and not kw:
                            return self._call_with_dict(name, request)
                        fn = self._conn.eval("mt5." + name)
                        return self._unwrap(fn(request, *rest, **kw))
                    return _dict_call
                fn = self._conn.eval("mt5." + name)
                if callable(fn):
                    def _call(*args, **kwargs):
                        return self._unwrap(fn(*args, **kwargs))
                    return _call
                return self._unwrap(fn)
        conn = _RpycMT5(host, port)
        _MT5_CONNECTIONS[key] = conn
        MT5_BACKEND = "rpyc"
        logger.info("MT5 backend rpyc %s:%s", host, port)
        return conn
    except Exception as exc:
        logger.error("MT5 backend unavailable at %s:%s: %s", host, port, exc)
        return None

_TF_MAP = {
    TimeFrame.M1: 1,
    TimeFrame.M5: 5,
    TimeFrame.M15: 15,
    TimeFrame.H1: 16385,
    TimeFrame.H4: 16388,
    TimeFrame.D1: 16408,
}

MAGIC = 908029


def _filling(mt5, info: Any) -> int:
    """Broker/symbol filling policy. filling_mode is a bitmask: bit0=FOK,
    bit1=IOC. Picking an unsupported mode makes order_send fail with
    retcode 10030 ("Unsupported filling mode")."""
    if mt5 is None:
        return 1
    mode = int(getattr(info, "filling_mode", 0) or 0)
    if mode & 1:
        return mt5.ORDER_FILLING_FOK
    if mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


class MT5BrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        path: str | None = None,
        timeout: int = 10_000,
        rpc_host: str | None = None,
        rpc_port: int | None = None,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.timeout = timeout
        # Each account talks to its own MT5 terminal bridge; defaults keep
        # single-account deployments on the existing env vars.
        self.rpc_host = rpc_host or os.getenv("MT5_RPC_HOST", "127.0.0.1")
        self.rpc_port = int(rpc_port or os.getenv("MT5_RPC_PORT", "8001"))
        self._mt5 = None
        self._connected = False

    async def connect(self) -> bool:
        self._mt5 = _load_mt5(self.rpc_host, self.rpc_port)
        if self._mt5 is None:
            logger.error("MetaTrader5 backend not available at %s:%s", self.rpc_host, self.rpc_port)
            return False

        def _init() -> bool:
            kwargs: dict[str, Any] = {"timeout": self.timeout}
            if self.path:
                kwargs["path"] = self.path
            if not self._mt5.initialize(**kwargs):
                logger.error("MT5 initialize failed: %s", self._mt5.last_error())
                return False
            if self.login and self.password and self.server:
                authorized = self._mt5.login(self.login, password=self.password, server=self.server)
                if not authorized:
                    logger.error("MT5 login failed: %s", self._mt5.last_error())
                    self._mt5.shutdown()
                    return False
            return True

        self._connected = await asyncio.to_thread(_init)
        return self._connected

    async def disconnect(self) -> None:
        if self._mt5 is not None and self._connected:
            await asyncio.to_thread(self._mt5.shutdown)
        self._connected = False

    async def is_connected(self) -> bool:
        if self._mt5 is None or not self._connected:
            return False
        info = await asyncio.to_thread(self._mt5.terminal_info)
        return info is not None

    async def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        info = await asyncio.to_thread(self._mt5.account_info)
        if info is None:
            raise RuntimeError(f"account_info failed: {self._mt5.last_error()}")
        return AccountInfo(
            login=info.login,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            margin_level=info.margin_level,
            profit=info.profit,
            currency=info.currency,
            leverage=info.leverage,
            trade_allowed=info.trade_allowed,
            account_type="DEMO" if info.trade_mode == 0 else "REAL",
        )

    async def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        self._ensure_connected()
        info = await asyncio.to_thread(self._mt5.symbol_info, symbol)
        if info is None:
            return None
        return SymbolInfo(
            name=info.name,
            description=info.description,
            digits=info.digits,
            point=info.point,
            trade_contract_size=info.trade_contract_size,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
            stop_level=info.trade_stops_level,
            freeze_level=info.trade_freeze_level,
            spread=float(info.spread),
            currency_base=info.currency_base,
            currency_profit=info.currency_profit,
            currency_margin=info.currency_margin,
        )

    async def get_symbols(self) -> list[str]:
        self._ensure_connected()
        symbols = await asyncio.to_thread(self._mt5.symbols_get)
        if symbols is None:
            return []
        return [s.name for s in symbols if s.visible]

    async def get_tick(self, symbol: str) -> Tick | None:
        self._ensure_connected()
        tick = await asyncio.to_thread(self._mt5.symbol_info_tick, symbol)
        if tick is None:
            return None
        return Tick(
            symbol=symbol,
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=float(tick.volume),
            time=datetime.fromtimestamp(tick.time, tz=timezone.utc),
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        count: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        self._ensure_connected()
        tf = _TF_MAP.get(timeframe, 15)
        rates = await asyncio.to_thread(self._mt5.copy_rates_from_pos, symbol, tf, 0, count)
        if rates is None:
            return []
        candles: list[Candle] = []
        for r in rates:
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["tick_volume"]),
                    spread=float(r["spread"]) if "spread" in r.dtype.names else None,
                    is_closed=True,
                )
            )
        return candles

    async def stream_ticks(self, symbols: list[str]) -> AsyncIterator[Tick]:
        self._ensure_connected()
        while await self.is_connected():
            for symbol in symbols:
                tick = await self.get_tick(symbol)
                if tick:
                    yield tick
            await asyncio.sleep(0.3)

    async def get_positions(self) -> list[BrokerPosition]:
        self._ensure_connected()
        positions = await asyncio.to_thread(self._mt5.positions_get)
        if positions is None:
            return []
        result: list[BrokerPosition] = []
        for p in positions:
            result.append(
                BrokerPosition(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    side=Side.BUY if p.type == 0 else Side.SELL,
                    volume=p.volume,
                    price_open=p.price_open,
                    price_current=p.price_current,
                    sl=p.sl or None,
                    tp=p.tp or None,
                    profit=p.profit,
                    swap=p.swap,
                    commission=getattr(p, "commission", 0.0),
                    time_open=datetime.fromtimestamp(p.time, tz=timezone.utc),
                    magic=p.magic,
                    comment=p.comment,
                )
            )
        return result

    async def get_orders(self) -> list[BrokerOrder]:
        self._ensure_connected()
        orders = await asyncio.to_thread(self._mt5.orders_get)
        if orders is None:
            return []
        out: list[BrokerOrder] = []
        for o in orders:
            out.append(
                BrokerOrder(
                    ticket=o.ticket,
                    symbol=o.symbol,
                    side=Side.BUY if o.type in (0, 2, 4) else Side.SELL,
                    order_type=OrderType.LIMIT,
                    volume=o.volume_current,
                    price_open=o.price_open,
                    sl=o.sl or None,
                    tp=o.tp or None,
                    status="PENDING",
                )
            )
        return out

    def _send(self, request: dict[str, Any]) -> OrderResult:
        result = self._mt5.order_send(request)
        if result is None:
            err = self._mt5.last_error()
            logger.error(
                "MT5 order_send None last_error=%s comment=%s symbol=%s action=%s",
                err,
                request.get("comment"),
                request.get("symbol"),
                request.get("action"),
            )
            return OrderResult(success=False, message=str(err), raw={"last_error": err})
        comment = result.comment or ""
        logger.info(
            "MT5 order_send retcode=%s comment=%s order=%s deal=%s volume=%s price=%s symbol=%s req_comment=%s",
            result.retcode,
            comment,
            result.order,
            result.deal,
            result.volume,
            result.price,
            request.get("symbol"),
            request.get("comment"),
        )
        ok = result.retcode == self._mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=ok,
            broker_order_id=str(result.order or result.deal or ""),
            fill_price=float(result.price or 0) or None,
            filled_volume=float(result.volume or 0),
            message=f"retcode={result.retcode} comment={comment}",
            raw={"retcode": result.retcode, "deal": result.deal, "order": result.order, "comment": comment},
        )

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self._ensure_connected()
        if self._mt5 is None:
            return OrderResult(success=False, client_order_id=request.client_order_id, message="MetaTrader5 backend not connected")
        if not request.sl:
            return OrderResult(
                success=False,
                client_order_id=request.client_order_id,
                message="stop loss is mandatory",
            )

        def _place() -> OrderResult:
            info = self._mt5.symbol_info(request.symbol)
            if info is None:
                return OrderResult(success=False, message=f"unknown symbol {request.symbol}")
            if not info.visible:
                self._mt5.symbol_select(request.symbol, True)
                info = self._mt5.symbol_info(request.symbol)
            tick = self._mt5.symbol_info_tick(request.symbol)
            if tick is None:
                return OrderResult(success=False, message="no tick")
            is_buy = request.side == Side.BUY or str(request.side).upper() == "BUY"
            if request.order_type == OrderType.MARKET or request.order_type is None:
                action = self._mt5.TRADE_ACTION_DEAL
                order_type = self._mt5.ORDER_TYPE_BUY if is_buy else self._mt5.ORDER_TYPE_SELL
                price = tick.ask if is_buy else tick.bid
            elif request.order_type == OrderType.LIMIT:
                action = self._mt5.TRADE_ACTION_PENDING
                order_type = self._mt5.ORDER_TYPE_BUY_LIMIT if is_buy else self._mt5.ORDER_TYPE_SELL_LIMIT
                price = float(request.price or 0)
            else:
                action = self._mt5.TRADE_ACTION_PENDING
                order_type = self._mt5.ORDER_TYPE_BUY_STOP if is_buy else self._mt5.ORDER_TYPE_SELL_STOP
                price = float(request.price or 0)
            payload = {
                "action": action,
                "symbol": request.symbol,
                "volume": float(request.volume),
                "type": order_type,
                "price": float(price),
                "sl": float(request.sl),
                "tp": float(request.tp or 0),
                "deviation": 30,
                "magic": int(request.magic or MAGIC),
                "comment": (request.comment or "molido")[:31],
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": _filling(self._mt5, info),
            }
            logger.info("MT5 place_order payload comment=%s type=%s %s", payload["comment"], request.order_type, request.symbol)
            res = self._send(payload)
            logger.info("MT5 place_order result %s", res.message)
            return res

        return await asyncio.to_thread(_place)

    async def cancel_order(self, ticket: str | int) -> bool:
        self._ensure_connected()

        def _cancel() -> bool:
            res = self._mt5.order_send({"action": self._mt5.TRADE_ACTION_REMOVE, "order": int(ticket)})
            if res is None:
                logger.error("MT5 cancel None last_error=%s ticket=%s", self._mt5.last_error(), ticket)
                return False
            logger.info("MT5 cancel retcode=%s comment=%s ticket=%s", res.retcode, res.comment, ticket)
            return bool(res and res.retcode == self._mt5.TRADE_RETCODE_DONE)

        return await asyncio.to_thread(_cancel)

    async def modify_position(
        self,
        ticket: str | int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> bool:
        self._ensure_connected()

        def _mod() -> bool:
            positions = self._mt5.positions_get(ticket=int(ticket))
            if not positions:
                return False
            p = positions[0]
            payload = {
                "action": self._mt5.TRADE_ACTION_SLTP,
                "position": int(ticket),
                "symbol": p.symbol,
                "sl": float(sl if sl is not None else p.sl),
                "tp": float(tp if tp is not None else p.tp),
            }
            res = self._mt5.order_send(payload)
            if res is None:
                logger.error("MT5 modify None last_error=%s ticket=%s", self._mt5.last_error(), ticket)
                return False
            logger.info("MT5 modify retcode=%s comment=%s ticket=%s sl=%s tp=%s", res.retcode, res.comment, ticket, payload["sl"], payload["tp"])
            return bool(res and res.retcode == self._mt5.TRADE_RETCODE_DONE)

        return await asyncio.to_thread(_mod)

    async def close_position(
        self,
        ticket: str | int,
        volume: float | None = None,
    ) -> OrderResult:
        self._ensure_connected()

        def _close() -> OrderResult:
            positions = self._mt5.positions_get(ticket=int(ticket))
            if not positions:
                return OrderResult(success=False, message="position not found")
            p = positions[0]
            tick = self._mt5.symbol_info_tick(p.symbol)
            if tick is None:
                return OrderResult(success=False, message="no tick")
            info = self._mt5.symbol_info(p.symbol)
            is_buy = p.type == 0
            payload = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": float(volume or p.volume),
                "type": self._mt5.ORDER_TYPE_SELL if is_buy else self._mt5.ORDER_TYPE_BUY,
                "position": int(p.ticket),
                "price": tick.bid if is_buy else tick.ask,
                "deviation": 30,
                "magic": int(p.magic or MAGIC),
                "comment": "molido-close",
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": _filling(self._mt5, info),
            }
            logger.info("MT5 close_position ticket=%s vol=%s comment=%s", ticket, payload["volume"], payload["comment"])
            res = self._send(payload)
            logger.info("MT5 close_position result %s", res.message)
            return res

        return await asyncio.to_thread(_close)

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("MT5BrokerAdapter is not connected")
