"""
LIVE trading runner.

Automatic: universe picker + AUTO timeframe, TrendFollowing only by default.
No manual pair picking. Heartbeat each cycle. Three numeric brains via pipeline.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import urllib.request
from molido_broker import create_broker, BrokerType
from molido_shared.types import TimeFrame
from molido_shared.point_in_time import InsufficientDataError, closed_bars
from molido_shared.data_quality import score_candles
from molido_shared.journal import TradeJournal
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_signals import SignalEngine
from molido_risk import RiskEngine, RiskLimits
from molido_execution import ExecutionEngine
from molido_portfolio import PositionManager, PortfolioManager, Reconciler
from molido_portfolio.trade_manager import TradeManager
from molido_regime import MarketRegimeEngine
from molido_guards import SessionCalendar, NewsBlackoutGuard, default_calendar_path
from molido_strategies.engine import parse_strategy_names
from molido_brain import (
    DecisionBrain,
    h1_side_from_bars,
    UniversePicker,
    CheapCandidate,
    resolve_universe,
    resolve_trade_timeframe,
    cheap_score,
    overnight_swap_r,
)
from app.orchestration.pipeline import TradingPipeline
from app.data.market_data import MarketDataEngine
from app.live.alerts import notify as telegram_notify
from app.live.decision_log import record_decision

logger = logging.getLogger(__name__)


def _load_runtime() -> dict:
    path = os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("runtime settings unreadable: %s", path)
        return {}


def _pick(rt: dict, *keys: str, env: str | None = None) -> str:
    for key in keys:
        val = rt.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text and text != "••••":
            return text
    if env:
        return (os.getenv(env) or "").strip()
    return ""


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


# If the ops API can't be reached for this many consecutive cycles, we can no
# longer confirm the operator's intent — fail closed (force master OFF)
# rather than keep trading blind on a possibly-stale in-memory value.
OPS_POLL_FAIL_LIMIT = 4


def _poll_ops(default_master: bool, fail_count: int) -> tuple[bool, int, int]:
    url = os.getenv("OPS_STATE_URL", "http://api:8000/api/v1/ops/state")
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            master = bool(data.get("master_on", default_master))
            seq = int(data.get("flatten_seq") or 0)
            return master, seq, 0
    except Exception:
        fail_count += 1
        if fail_count >= OPS_POLL_FAIL_LIMIT:
            if default_master:
                logger.warning(
                    "ops state unreachable for %d consecutive cycles; failing closed (master OFF)",
                    fail_count,
                )
            return False, 0, fail_count
        logger.debug("ops state poll failed (%d/%d); keeping master=%s", fail_count, OPS_POLL_FAIL_LIMIT, default_master)
        return default_master, 0, fail_count


def _post_heartbeat() -> None:
    url = os.getenv("OPS_HEARTBEAT_URL") or os.getenv(
        "OPS_STATE_URL", "http://api:8000/api/v1/ops/state"
    ).replace("/state", "/heartbeat")
    token = os.getenv("ENGINE_INTERNAL_TOKEN", "")
    try:
        req = urllib.request.Request(
            url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json", "X-Engine-Token": token},
        )
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        logger.debug("ops heartbeat post failed")


class LiveRunner:
    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframe: TimeFrame = TimeFrame.M15,
        cycle_seconds: float = 15.0,
    ):
        rt = _load_runtime()
        self.tf_override = "AUTO"
        self.symbols = resolve_universe("auto")
        self.timeframe = TimeFrame.M15
        self.picker = UniversePicker()
        self.cycle_seconds = cycle_seconds
        self.account_mode = (_pick(rt, "trading_account_mode", env="TRADING_ACCOUNT_MODE") or "DEMO").upper()
        self.master_bot_on = _env_bool("MASTER_BOT_ENABLED", False)
        if "master_bot_enabled" in rt:
            self.master_bot_on = bool(rt.get("master_bot_enabled"))
        self._ops_poll_fail_count = 0
        self._running = False
        self._flatten_seen = 0
        self.broker = None
        self.execution = None
        self.positions = None
        self.portfolio = None
        self.reconciler = None
        self.pipeline = None
        self.market_data = None
        self.trade_manager = None
        self.regime = MarketRegimeEngine()
        self.calendar = SessionCalendar()
        self.news = NewsBlackoutGuard(calendar_path=default_calendar_path())
        self.news.load_from_disk()
        self.journal = TradeJournal()
        self.brain = DecisionBrain()

        self.indicators = IndicatorEngine()
        self.indicators.add_from_registry("MultiEMA")
        self.indicators.add_from_registry("RSI", period=14)
        self.indicators.add_from_registry("ATR", period=14)
        self.indicators.add_from_registry("MACD")
        self.indicators.add_from_registry("BollingerBands", period=20)
        self.indicators.add_from_registry("DonchianChannel", period=20)
        self.indicators.add_from_registry("Supertrend", period=10, multiplier=3.0)

        self.strategies = StrategyEngine()
        self.strategies.configure_live(parse_strategy_names(rt.get("strategy_names")))

        self.signals = SignalEngine(accept_threshold=55.0)
        self.risk = RiskEngine(self._limits_from(rt))

    def _limits_from(self, rt: dict) -> RiskLimits:
        def num(key: str, default: float) -> float:
            try:
                return float(rt.get(key, default))
            except (TypeError, ValueError):
                return default
        try:
            max_pos = int(rt.get("max_open_positions", 3))
        except (TypeError, ValueError):
            max_pos = 3
        return RiskLimits(
            risk_per_trade=num("default_risk_per_trade", 0.0025),
            max_daily_loss=num("max_daily_loss", 0.02),
            max_drawdown=num("max_drawdown", 0.04),
            max_open_positions=max(1, max_pos),
        )

    def _apply_runtime(self, rt: dict) -> None:
        mode = (_pick(rt, "trading_account_mode", env="TRADING_ACCOUNT_MODE") or self.account_mode).upper()
        self.account_mode = mode
        self.tf_override = "AUTO"
        self.symbols = resolve_universe("auto")
        self.timeframe = TimeFrame.M15
        if "master_bot_enabled" in rt:
            self.master_bot_on = bool(rt.get("master_bot_enabled"))
        self.risk.limits = self._limits_from(rt)
        if self.pipeline is not None:
            self.pipeline.account_mode = mode
        if self.portfolio is not None:
            self.portfolio.account_mode = mode
        if self.market_data is not None:
            self.market_data.symbols = self.symbols
        self.strategies.configure_live(parse_strategy_names(rt.get("strategy_names")))

    def _mt5_creds(self, rt: dict) -> tuple[int | None, str, str, str | None]:
        login_raw = _pick(rt, "mt5_login", "mt5_real_login", env="MT5_REAL_LOGIN")
        password = _pick(rt, "mt5_password", "mt5_real_password", env="MT5_REAL_PASSWORD")
        server = _pick(rt, "mt5_server", "mt5_real_server", env="MT5_REAL_SERVER")
        path = _pick(rt, "mt5_path", "mt5_real_path", env="MT5_REAL_PATH") or None
        login: int | None = None
        if login_raw:
            try:
                login = int(login_raw)
            except ValueError:
                logger.error("MT5 login must be a number")
        return login, password, server, path

    def _bind_broker(self, login: int, password: str, server: str, path: str | None) -> None:
        self.broker = create_broker(BrokerType.MT5, login=login, password=password, server=server, path=path)
        self.execution = ExecutionEngine(self.broker)
        self.positions = PositionManager(self.broker)
        self.portfolio = PortfolioManager(self.broker, self.positions, account_mode=self.account_mode)
        self.reconciler = Reconciler(self.broker, self.positions)
        self.trade_manager = TradeManager(self.broker, self.positions)
        self.pipeline = TradingPipeline(
            indicator_engine=self.indicators,
            strategy_engine=self.strategies,
            signal_engine=self.signals,
            risk_engine=self.risk,
            execution_engine=self.execution,
            position_manager=self.positions,
            portfolio_manager=self.portfolio,
            reconciler=self.reconciler,
            account_mode=self.account_mode,
            brain=self.brain,
            journal=self.journal,
            news_guard=self.news,
        )
        self.market_data = MarketDataEngine(broker=self.broker, symbols=self.symbols, stale_threshold_seconds=60.0)

    async def start(self) -> None:
        logger.info("LIVE runner waiting for MT5 credentials (dashboard Settings or env)")
        while True:
            rt = _load_runtime()
            self._apply_runtime(rt)
            login, password, server, path = self._mt5_creds(rt)
            if login and password and server:
                self._bind_broker(login, password, server, path)
                break
            logger.warning("MT5 login/password/server not set yet; retrying in 10s")
            await asyncio.sleep(10)
        logger.info("LIVE runner starting | mode=%s | master=%s | symbols=%s", self.account_mode, "ON" if self.master_bot_on else "OFF", self.symbols)
        ok = await self.broker.connect()
        if not ok:
            raise RuntimeError("LIVE MT5 connect failed. Need a running MT5 terminal (Windows or Wine) plus valid credentials.")
        await self.reconciler.reconcile()
        await self.market_data.start()
        self._running = True
        try:
            while self._running:
                await self._cycle()
                await asyncio.sleep(self.cycle_seconds)
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._running = False
        if self.market_data is not None:
            await self.market_data.stop()
        if self.broker is not None:
            await self.broker.disconnect()
        logger.info("LIVE runner stopped")

    def set_master(self, on: bool) -> None:
        self.master_bot_on = on
        logger.info("Master bot → %s", "ON" if on else "OFF")

    async def _cycle(self) -> None:
        _post_heartbeat()
        rt = _load_runtime()
        self._apply_runtime(rt)
        self.news.load_from_disk()
        self.master_bot_on, flatten_seq, self._ops_poll_fail_count = _poll_ops(
            self.master_bot_on, self._ops_poll_fail_count
        )
        if flatten_seq > self._flatten_seen and self.trade_manager is not None:
            self._flatten_seen = flatten_seq
            acts = await self.trade_manager.flatten_all("ops flatten")
            for a in acts:
                self.journal.append("flatten", reason="ops flatten", detail=a)
            telegram_notify("Molido flatten-all requested")
        flat_ok, flat_why = self.calendar.should_flatten()
        if flat_ok and self.trade_manager is not None and self.positions and self.positions.count() > 0:
            acts = await self.trade_manager.flatten_all(flat_why)
            for a in acts:
                self.journal.append("flatten", reason=flat_why, detail=a)
            telegram_notify(f"Molido flatten: {flat_why}")
        open_syms = []
        if self.positions is not None:
            open_syms = list({p.symbol for p in self.positions.get_all()})
        for symbol in open_syms:
            try:
                await self._manage_open(symbol)
            except Exception:
                logger.exception("manage error on %s", symbol)
        sess_ok, sess_why = self.calendar.allow_new_entries()
        if not sess_ok:
            logger.info("LIVE session skip: %s", sess_why)
            return
        snap = await self.portfolio.snapshot()
        logger.info("LIVE equity=%.2f | positions=%d | DD=%.2f%% | master=%s | sessions=%s", snap.equity, snap.open_positions, snap.drawdown_pct, "ON" if self.master_bot_on else "OFF", ",".join(self.calendar.active_sessions()) or "-")
        stats = self.journal.journal_stats(20)
        if stats and stats["n"] >= 20 and stats["mean_r"] < 0 and self.brain.pause_on_negative_journal:
            logger.info("LIVE pause new entries: journal mean R=%.3f n=%s", stats["mean_r"], stats["n"])
            return
        overlap = "London_NY_Overlap" in self.calendar.active_sessions()
        picks = await self._pick_symbols(open_syms, overlap=overlap, session_ok=True)
        logger.info("LIVE picker %s", ",".join(f"{c.symbol}:{c.score:.2f}" for c in picks) or "(none)")
        for cand in picks:
            try:
                await self._evaluate_symbol(
                    cand.symbol,
                    resolve_trade_timeframe(self.tf_override, overlap=overlap, spread_ok=cand.spread_ok),
                    h1_side=cand.h1_side,
                    overlap=overlap,
                    tick_spread=cand.spread,
                    universe_score=cand.score,
                )
            except Exception:
                logger.exception("LIVE cycle error on %s", cand.symbol)

    async def _pick_symbols(self, open_syms: list[str], *, overlap: bool, session_ok: bool) -> list:
        ticks = {}
        spread_order = []
        for symbol in self.symbols:
            tick = None
            try:
                tick = await self.market_data.get_latest_tick(symbol)
                if tick is None:
                    tick = await self.broker.get_tick(symbol)
            except Exception:
                tick = None
            ticks[symbol] = tick
            if tick is not None:
                rel = tick.spread / tick.mid if tick.mid else 9
                spread_order.append((rel, symbol))
        spread_order.sort()
        h1_targets = self.picker.h1_budget([s for _, s in spread_order])
        h1_map: dict[str, str | None] = {}
        for symbol in h1_targets:
            try:
                h1_raw = await self.market_data.get_candles(symbol, TimeFrame.H1, count=80, use_cache=True)
                h1_bars = closed_bars(h1_raw, min_bars=30)
                h1_map[symbol] = h1_side_from_bars(h1_bars)
            except (InsufficientDataError, Exception):
                h1_map[symbol] = None
        rows: list[CheapCandidate] = []
        for symbol in self.symbols:
            tick = ticks.get(symbol)
            spread = tick.spread if tick is not None else None
            mid = tick.mid if tick is not None else None
            score, reasons, spread_ok = cheap_score(session_ok=session_ok, overlap=overlap, spread=spread, mid=mid, h1_side=h1_map.get(symbol))
            rows.append(CheapCandidate(symbol=symbol, score=score, spread=spread, mid=mid, h1_side=h1_map.get(symbol), spread_ok=spread_ok, reasons=reasons))
        ranked = self.brain.rank_universe(self.picker.rank(rows))
        return self.picker.select(ranked, open_syms)

    async def _evaluate_symbol(self, symbol: str, trade_tf: TimeFrame, *, h1_side: str | None, overlap: bool, tick_spread: float | None, universe_score: float | None = None) -> None:
        raw = await self.market_data.get_candles(symbol, trade_tf, count=160, use_cache=False)
        if not raw:
            return
        try:
            candles = closed_bars(raw, min_bars=30)
        except InsufficientDataError as exc:
            logger.debug("%s PIT: %s", symbol, exc)
            return
        quality = score_candles(candles)
        if not quality.tradeable:
            logger.warning("%s quality block score=%.2f %s", symbol, quality.score, quality.findings[:3])
            return
        ind = self.indicators.compute_latest(candles)
        regime = self.regime.classify(candles, ind)
        tick = await self.market_data.get_latest_tick(symbol)
        if tick is None:
            tick = await self.broker.get_tick(symbol)
        spread = tick.spread if tick is not None else tick_spread
        result = await self.pipeline.on_candles(
            symbol=symbol, timeframe=trade_tf, candles=candles, regime=regime,
            master_bot_on=self.master_bot_on, h1_side=h1_side, spread=spread, tick=tick,
            overlap=overlap, swap_r=overnight_swap_r(symbol=symbol, now=None),
            session_ok=True, universe_score=universe_score,
        )
        brains = (result.signal.meta or {}).get("brains") if result.signal and result.signal.meta else None
        if brains:
            try:
                record_decision(
                    symbol=symbol,
                    side=result.signal.side.value if result.signal else None,
                    allow=result.risk_allowed and not result.skipped_reason,
                    size_mult=result.size_mult,
                    p_win=result.p_win,
                    expected_r=result.expected_r,
                    skipped_reason=result.skipped_reason,
                    brains=brains,
                )
            except Exception:
                logger.exception("decision log record failed for %s", symbol)
        if result.skipped_reason:
            logger.debug("%s skipped: %s", symbol, result.skipped_reason)
            return
        if result.exec_result and result.exec_result.success:
            side = result.signal.side.value if result.signal else "?"
            logger.info("%s LIVE FILL %s %.2f lots @ %s | tf=%s | regime=%s", symbol, side, result.lot_size, result.exec_result.fill_price, trade_tf.value, regime)
            telegram_notify(f"Molido FILL {symbol} {side} {result.lot_size} @ {result.exec_result.fill_price} tf={trade_tf.value} regime={regime}")
        elif result.exec_result and not result.exec_result.success:
            logger.warning("%s exec failed: %s", symbol, result.exec_result.message)

    async def _manage_open(self, symbol: str) -> None:
        if self.trade_manager is None or self.positions is None:
            return
        if self.positions.by_symbol(symbol) == []:
            return
        raw = await self.market_data.get_candles(symbol, self.timeframe, count=40)
        try:
            candles = closed_bars(raw, min_bars=8) if raw else []
        except InsufficientDataError:
            candles = []
        atr = None
        price = None
        if candles:
            ind = self.indicators.compute_latest(candles)
            atr_res = ind.get("ATR") or ind.get("atr14")
            if atr_res:
                atr = atr_res.get("atr")
            price = candles[-1].close
        tick = await self.market_data.get_latest_tick(symbol)
        if tick is not None:
            price = tick.mid
        for pos in self.positions.by_symbol(symbol):
            st = self.trade_manager._st(pos)
            self.journal.update_mae_mfe(pos.ticket, price=price, entry=pos.entry_price, side=pos.side, stop_distance=st.get("stop_dist"))
        await self.trade_manager.manage_symbol(symbol, candles=candles, atr=atr, timeframe=self.timeframe, price=price)
        await self.positions.sync_from_broker()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    runner = LiveRunner()
    try:
        await runner.start()
    except KeyboardInterrupt:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
