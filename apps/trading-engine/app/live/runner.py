"""
LIVE trading runner.

Automatic: universe picker + AUTO timeframe, TrendFollowing only by default.
No manual pair picking. Heartbeat each cycle. Three numeric brains via pipeline.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
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
from molido_guards import SessionCalendar, NewsBlackoutGuard, TradingHoursGuard, default_calendar_path
from molido_strategies.engine import parse_strategy_names
from molido_brain import (
    DecisionBrain,
    h1_side_from_bars,
    UniversePicker,
    CheapCandidate,
    resolve_universe,
    resolve_trade_timeframe,
    is_auto_timeframe,
    cheap_score,
    overnight_swap_r,
)
from app.orchestration.pipeline import TradingPipeline
from app.data.market_data import MarketDataEngine
from app.live.alerts import notify as telegram_notify
from app.live.decision_log import record_decision
from app.live.status_snapshot import write_status
from app.live.accounts import AccountConfig, load_accounts, enabled_accounts

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


def _overlap_only(rt: dict) -> bool:
    """New entries restricted to the London/NY overlap only?

    Defaults to False: entries are allowed during any active session
    (Tokyo/London/NY), roughly 17h/day instead of the 4h overlap window.
    Overlap-only is the more conservative setting (tightest spreads, deepest
    liquidity) and can be re-enabled per-deployment without a rebuild via
    the session_overlap_only runtime setting or SESSION_OVERLAP_ONLY env.
    """
    val = rt.get("session_overlap_only")
    if val is None:
        return _env_bool("SESSION_OVERLAP_ONLY", False)
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


# If the ops API can't be reached for this many consecutive cycles, we can no
# longer confirm the operator's intent — fail closed (force master OFF)
# rather than keep trading blind on a possibly-stale in-memory value.
OPS_POLL_FAIL_LIMIT = 4


def _poll_ops(default_master: bool, fail_count: int) -> tuple[bool, int, int]:
    url = os.getenv("OPS_STATE_URL", "http://api:8000/api/v1/ops/state")
    token = os.getenv("ENGINE_INTERNAL_TOKEN", "")
    try:
        req = urllib.request.Request(url, headers={"X-Engine-Token": token})
        with urllib.request.urlopen(req, timeout=2) as resp:
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


DATA_DIR = os.path.dirname(os.getenv("RUNTIME_SETTINGS_PATH", "/app/data/runtime-settings.json")) or "/app/data"


class LiveRunner:
    """Trades exactly one broker account.

    Everything that carries per-account state -- broker connection, risk
    engine (circuit breaker, daily-loss stop), positions, journal, dashboard
    snapshot -- is owned by the instance, so running several of these
    concurrently keeps the accounts fully isolated from each other.
    """

    def __init__(
        self,
        account: AccountConfig | None = None,
        symbols: list[str] | None = None,
        timeframe: TimeFrame = TimeFrame.M15,
        cycle_seconds: float = 15.0,
    ):
        rt = _load_runtime()
        if account is None:
            # No account passed: behave exactly as the single-account engine
            # did, by taking the first configured (or synthesised) account.
            account = load_accounts(rt)[0]
        self.account = account
        self.log_tag = account.id
        acc_settings = account.settings or rt
        self.tf_override = account.timeframe
        self.symbols = resolve_universe(account.symbols)
        self.timeframe = TimeFrame.M15
        self.picker = UniversePicker()
        self.cycle_seconds = cycle_seconds
        self.account_mode = account.account_mode
        self.master_bot_on = _env_bool("MASTER_BOT_ENABLED", False)
        if "master_bot_enabled" in acc_settings:
            self.master_bot_on = bool(acc_settings.get("master_bot_enabled"))
        self._ops_poll_fail_count = 0
        # Seconds to add to real UTC to get the broker's clock. MT5 stamps
        # candles in broker-local time but the Candle carries no zone, so
        # comparing them against datetime.now(utc) silently treats them as UTC.
        # On MetaQuotes-Demo (UTC+3) that made closed_bars() discard every bar
        # of the last three hours as "not yet closed": measured live, it kept
        # 13 fewer bars than it should and handed the strategies a candle from
        # 10:00 while the market was at 13:15. Every signal -- including the
        # only six orders this bot has ever placed -- was computed on
        # three-hour-old prices, and the resulting entry was then rejected by
        # the drift guard, which is 30% of all decisions in the journal.
        # Learned from tick timestamps rather than assumed, so it follows the
        # broker across DST and works for any server.
        self._broker_clock_offset = 0.0
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
        self.calendar = SessionCalendar(overlap_only=_overlap_only(acc_settings))
        self.news = NewsBlackoutGuard(calendar_path=default_calendar_path())
        self.news.load_from_disk()
        self.journal = TradeJournal(path=account.journal_path(DATA_DIR))
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
        self.strategies.configure_live(parse_strategy_names(account.strategy_names))

        self.signals = SignalEngine(accept_threshold=55.0)
        self.risk = RiskEngine(self._limits_from(acc_settings))

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
        def whole(key: str, default: int) -> int:
            try:
                return int(rt.get(key, default))
            except (TypeError, ValueError):
                return default
        base = RiskLimits()
        return RiskLimits(
            risk_per_trade=num("default_risk_per_trade", 0.0025),
            max_daily_loss=num("max_daily_loss", 0.02),
            # These three were settable in the dashboard and persisted to
            # runtime-settings.json, but never read here -- the engine kept
            # RiskLimits' own defaults, so changing the daily entry cap or the
            # weekly loss limit in settings silently did nothing.
            max_weekly_loss=num("max_weekly_loss", base.max_weekly_loss),
            max_entries_per_day=max(1, whole("max_entries_per_day", base.max_entries_per_day)),
            max_drawdown=num("max_drawdown", 0.04),
            max_open_positions=max(1, max_pos),
            # Prop-challenge backstop; 0 (the default) leaves it off.
            prop_initial_balance=num("prop_initial_balance", 0.0),
            prop_max_loss_pct=num("prop_max_loss_pct", base.prop_max_loss_pct),
        )

    def _resolve_account(self, rt: dict) -> AccountConfig:
        """This account's latest config. If it disappears from the settings
        file mid-run we keep the last known copy rather than crashing or,
        worse, silently adopting another account's credentials."""
        for acc in load_accounts(rt):
            if acc.id == self.account.id:
                return acc
        logger.warning("[%s] account no longer in settings; keeping last known config", self.log_tag)
        return self.account

    def _apply_runtime(self, rt: dict) -> None:
        acc = self._resolve_account(rt)
        self.account = acc
        settings = acc.settings or rt
        self.account_mode = acc.account_mode
        self.tf_override = acc.timeframe
        self.symbols = resolve_universe(acc.symbols)
        self.timeframe = TimeFrame.M15
        if "master_bot_enabled" in settings:
            self.master_bot_on = bool(settings.get("master_bot_enabled"))
        overlap_only = _overlap_only(settings)
        self.calendar.overlap_only = overlap_only
        # The pipeline runs its own trading-hours check; keep it on the same
        # session config rather than letting it default to overlap-only.
        if self.pipeline is not None and TradingHoursGuard is not None:
            self.pipeline.hours_guard = TradingHoursGuard(overlap_only=overlap_only)
        self.risk.limits = self._limits_from(settings)
        # Keep the universe picker in step with the configured position cap,
        # and let it propose one extra candidate per cycle -- the brains and
        # risk engine remain the actual gatekeepers.
        self.picker.max_open = self.risk.limits.max_open_positions
        self.picker.max_new = 3
        if self.pipeline is not None:
            self.pipeline.account_mode = self.account_mode
        if self.portfolio is not None:
            self.portfolio.account_mode = self.account_mode
        if self.market_data is not None:
            self.market_data.symbols = self.symbols
        self.strategies.configure_live(parse_strategy_names(acc.strategy_names))

    def _mt5_creds(self, rt: dict) -> tuple[int | None, str, str, str | None]:
        acc = self._resolve_account(rt)
        return acc.login, acc.password, acc.server, acc.path

    def _bind_broker(self, login: int, password: str, server: str, path: str | None) -> None:
        self.broker = create_broker(
            BrokerType.MT5, login=login, password=password, server=server, path=path,
            rpc_host=self.account.rpc_host, rpc_port=self.account.rpc_port,
        )
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
        logger.info("[%s] waiting for MT5 credentials (dashboard Settings or env)", self.log_tag)
        while True:
            rt = _load_runtime()
            self._apply_runtime(rt)
            login, password, server, path = self._mt5_creds(rt)
            if login and password and server:
                self._bind_broker(login, password, server, path)
                break
            logger.warning("[%s] MT5 login/password/server not set yet; retrying in 10s", self.log_tag)
            await asyncio.sleep(10)
        logger.info("[%s] LIVE runner starting | mode=%s | master=%s | rpc=%s:%s | symbols=%s", self.log_tag, self.account_mode, "ON" if self.master_bot_on else "OFF", self.account.rpc_host, self.account.rpc_port, self.symbols)
        ok = await self.broker.connect()
        if not ok:
            raise RuntimeError(f"[{self.log_tag}] MT5 connect failed. Need a running MT5 terminal (Windows or Wine) on {self.account.rpc_host}:{self.account.rpc_port} plus valid credentials.")
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
        logger.info("[%s] LIVE runner stopped", self.log_tag)

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
            telegram_notify("🔻 درخواست بستن همه پوزیشن‌ها")
        flat_ok, flat_why = self.calendar.should_flatten()
        if flat_ok and self.trade_manager is not None and self.positions and self.positions.count() > 0:
            acts = await self.trade_manager.flatten_all(flat_why)
            for a in acts:
                self.journal.append("flatten", reason=flat_why, detail=a)
            telegram_notify(f"🔻 بستن پوزیشن‌ها: {flat_why}")
        open_syms = []
        if self.positions is not None:
            # Ask the broker what we actually hold before deciding whether to
            # open more. Previously sync_from_broker() only ran inside
            # _manage_open(), i.e. only for symbols already known to be open,
            # and reconcile() ran once at startup -- so a fill the local
            # manager missed stayed invisible for the rest of the run. The
            # picker excludes open symbols, saw none, and re-entered the same
            # setup every cycle: six GBPUSD SELLs in ten minutes on
            # 2026-08-31, one signal turned into six positions. The broker is
            # the authority on what is open; consult it before sizing up.
            try:
                await self.positions.sync_from_broker()
            except Exception:
                logger.exception("[%s] position sync failed; skipping new entries this cycle", self.log_tag)
                return
            open_syms = list({p.symbol for p in self.positions.get_all()})
        for symbol in open_syms:
            try:
                await self._manage_open(symbol)
            except Exception:
                logger.exception("manage error on %s", symbol)
        sess_ok, sess_why = self.calendar.allow_new_entries()
        # Status snapshot every cycle -- session-closed ones included -- so
        # the dashboard's equity/positions view stays live around the clock.
        try:
            snap = await self.portfolio.snapshot()
            write_status(
                path=self.account.status_path(DATA_DIR),
                account_id=self.account.id,
                account_name=self.account.name,
                snapshot=snap,
                positions=self.positions.get_all() if self.positions else [],
                master_on=self.master_bot_on,
                account_mode=self.account_mode,
                session_note=sess_why,
                active_sessions=self.calendar.active_sessions(),
            )
        except Exception:
            logger.exception("portfolio status snapshot failed")
            snap = None
        if not sess_ok:
            logger.info("[%s] session skip: %s", self.log_tag, sess_why)
            return
        if snap is None:
            snap = await self.portfolio.snapshot()
        logger.info("[%s] equity=%.2f | positions=%d | DD=%.2f%% | master=%s | sessions=%s", self.log_tag, snap.equity, snap.open_positions, snap.drawdown_pct, "ON" if self.master_bot_on else "OFF", ",".join(self.calendar.active_sessions()) or "-")
        stats = self.journal.journal_stats(20)
        if stats and stats["n"] >= 20 and stats["mean_r"] < 0 and self.brain.pause_on_negative_journal:
            logger.info("LIVE pause new entries: journal mean R=%.3f n=%s", stats["mean_r"], stats["n"])
            return
        overlap = "London_NY_Overlap" in self.calendar.active_sessions()
        picks = await self._pick_symbols(open_syms, overlap=overlap, session_ok=True)
        logger.info("[%s] picker %s", self.log_tag, ",".join(f"{c.symbol}:{c.score:.2f}" for c in picks) or "(none)")
        for cand in picks:
            # Evaluate on both M15 and M5 rather than a single resolved
            # timeframe: several times the decision opportunities per cycle.
            # M5 only when the spread supports it (its tighter stops are more
            # spread-sensitive); the dead-ATR gate is timeframe-scaled so M5
            # is judged by an M5-appropriate threshold. If the first
            # timeframe opens a position, the no-average-down rule blocks a
            # second entry on the same symbol, so this cannot double up.
            # "auto" (the default) sweeps both bar sizes, which is what gives
            # the brains several decision points per candidate. An explicit
            # timeframe in settings pins entries to just that one -- it used to
            # be ignored entirely: tf_override was hardcoded to "AUTO",
            # self.timeframe to M15, and resolve_trade_timeframe was imported
            # and never called, so the dashboard's timeframe control did
            # nothing whatever it was set to.
            if is_auto_timeframe(self.tf_override):
                tfs = [TimeFrame.M15] + ([TimeFrame.M5] if cand.spread_ok else [])
            else:
                tfs = [resolve_trade_timeframe(self.tf_override, overlap=overlap, spread_ok=cand.spread_ok)]
            for tf in tfs:
                try:
                    await self._evaluate_symbol(
                        cand.symbol,
                        tf,
                        h1_side=cand.h1_side,
                        overlap=overlap,
                        tick_spread=cand.spread,
                        universe_score=cand.score,
                    )
                except Exception:
                    logger.exception("LIVE cycle error on %s %s", cand.symbol, tf.value)

    def _broker_now(self) -> datetime:
        """Now, on the broker's clock -- the frame candle stamps are in."""
        return datetime.now(timezone.utc) + timedelta(seconds=self._broker_clock_offset)

    def _learn_clock_offset(self, tick) -> None:
        """Track broker-vs-UTC drift from tick timestamps."""
        t = getattr(tick, "time", None)
        if t is None:
            return
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        delta = (t - datetime.now(timezone.utc)).total_seconds()
        # Ticks can be a little stale on a quiet symbol; only whole-hour-ish
        # gaps are a real timezone difference, and never trust a wild value.
        if abs(delta) < 120 or abs(delta) > 60 * 60 * 26:
            return
        if abs(delta - self._broker_clock_offset) > 60:
            logger.info("[%s] broker clock offset %+.2fh vs UTC", self.log_tag, delta / 3600.0)
        self._broker_clock_offset = delta

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
                self._learn_clock_offset(tick)
                rel = tick.spread / tick.mid if tick.mid else 9
                spread_order.append((rel, symbol))
        spread_order.sort()
        h1_targets = self.picker.h1_budget([s for _, s in spread_order])
        h1_map: dict[str, str | None] = {}
        for symbol in h1_targets:
            try:
                h1_raw = await self.market_data.get_candles(symbol, TimeFrame.H1, count=80, use_cache=True)
                h1_bars = closed_bars(h1_raw, as_of=self._broker_now(), min_bars=30)
                h1_map[symbol] = h1_side_from_bars(h1_bars)
            except (InsufficientDataError, Exception):
                h1_map[symbol] = None
        rows: list[CheapCandidate] = []
        for idx, symbol in enumerate(self.symbols):
            tick = ticks.get(symbol)
            spread = tick.spread if tick is not None else None
            mid = tick.mid if tick is not None else None
            # self.symbols keeps the order the account configured, so a
            # symbol's index in it is its priority. Only the first two get a
            # bonus, and it is small enough to settle near-equals without
            # overriding a genuinely better candidate.
            score, reasons, spread_ok = cheap_score(
                session_ok=session_ok,
                overlap=overlap,
                spread=spread,
                mid=mid,
                h1_side=h1_map.get(symbol),
                priority_rank=idx,
            )
            rows.append(CheapCandidate(symbol=symbol, score=score, spread=spread, mid=mid, h1_side=h1_map.get(symbol), spread_ok=spread_ok, reasons=reasons))
        ranked = self.brain.rank_universe(self.picker.rank(rows))
        return self.picker.select(ranked, open_syms)

    async def _evaluate_symbol(self, symbol: str, trade_tf: TimeFrame, *, h1_side: str | None, overlap: bool, tick_spread: float | None, universe_score: float | None = None) -> None:
        raw = await self.market_data.get_candles(symbol, trade_tf, count=160, use_cache=False)
        if not raw:
            return
        try:
            candles = closed_bars(raw, as_of=self._broker_now(), min_bars=30)
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
                    path=self.account.decisions_path(DATA_DIR),
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
            telegram_notify(
                "✅ <b>معامله باز شد</b>\n"
                f"نماد: {symbol}\n"
                f"جهت: {side}\n"
                f"حجم: {result.lot_size} لات\n"
                f"قیمت: {result.exec_result.fill_price}\n"
                f"تایم‌فریم: {trade_tf.value} | رژیم بازار: {regime}"
            )
        elif result.exec_result and not result.exec_result.success:
            logger.warning("%s exec failed: %s", symbol, result.exec_result.message)

    async def _manage_open(self, symbol: str) -> None:
        if self.trade_manager is None or self.positions is None:
            return
        if self.positions.by_symbol(symbol) == []:
            return
        raw = await self.market_data.get_candles(symbol, self.timeframe, count=40)
        try:
            candles = closed_bars(raw, as_of=self._broker_now(), min_bars=8) if raw else []
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


class MultiAccountRunner:
    """Supervises one LiveRunner per enabled account.

    Accounts are independent: each has its own broker connection, risk
    engine and journal, so one account hitting its circuit breaker, losing
    its MT5 bridge, or crashing outright leaves the others trading. A
    crashed account is restarted with capped backoff rather than taking the
    process down, because a single bad account should not stop the rest.
    """

    def __init__(self, cycle_seconds: float = 15.0, restart_backoff_max: float = 120.0):
        self.cycle_seconds = cycle_seconds
        self.restart_backoff_max = restart_backoff_max
        self._runners: dict[str, LiveRunner] = {}
        self._running = False

    async def _supervise(self, account: AccountConfig) -> None:
        backoff = 5.0
        while self._running:
            runner = LiveRunner(account=account, cycle_seconds=self.cycle_seconds)
            self._runners[account.id] = runner
            try:
                await runner.start()
                # start() only returns when the runner stops on its own.
                backoff = 5.0
            except asyncio.CancelledError:
                await runner.stop()
                raise
            except Exception:
                logger.exception("[%s] runner crashed; restarting in %.0fs", account.id, backoff)
                try:
                    await runner.stop()
                except Exception:
                    logger.exception("[%s] error while stopping crashed runner", account.id)
                if not self._running:
                    return
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.restart_backoff_max)

    async def start(self) -> None:
        rt = _load_runtime()
        accounts = enabled_accounts(rt)
        if not accounts:
            logger.error("no enabled accounts configured; nothing to run")
            return
        all_accounts = load_accounts(rt)
        logger.info(
            "starting %d of %d account(s): %s",
            len(accounts), len(all_accounts), ", ".join(f"{a.id}({a.account_mode})" for a in accounts),
        )
        for a in all_accounts:
            if not a.enabled:
                logger.info("[%s] disabled in settings; not started", a.id)
        self._running = True
        try:
            await asyncio.gather(*(self._supervise(a) for a in accounts))
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._running = False
        for acc_id, runner in list(self._runners.items()):
            try:
                await runner.stop()
            except Exception:
                logger.exception("[%s] error stopping runner", acc_id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    runner = MultiAccountRunner()
    try:
        await runner.start()
    except KeyboardInterrupt:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
