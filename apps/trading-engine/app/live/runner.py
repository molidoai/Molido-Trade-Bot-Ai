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
from molido_strategies.engine import parse_strategy_names, parse_symbol_strategies
from molido_brain.experience import Experience
from molido_brain.autopilot import plan as autopilot_plan, independent_groups
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


# What the engine has always computed. Kept as the default so nothing changes
# for an account that says nothing about indicators.
DEFAULT_INDICATORS: list[tuple[str, dict]] = [
    ("MultiEMA", {}),
    ("RSI", {"period": 14}),
    ("ATR", {"period": 14}),
    ("MACD", {}),
    ("BollingerBands", {"period": 20}),
    ("DonchianChannel", {"period": 20}),
    ("Supertrend", {"period": 10, "multiplier": 3.0}),
]


def _build_indicators(rt: dict) -> IndicatorEngine:
    """Build the indicator set, letting settings override the default list.

    Strategies were already selectable per account; indicators were not, so
    the one thing a strategy depends on could only be changed by editing this
    file and rebuilding the image. That is how ADX came to be missing: a
    strategy could ask for it, the registry could provide it, and the live
    engine would still never compute it.

    Settings may carry either plain names or {"name": ..., "params": {...}}:

        "indicators": ["MultiEMA", {"name": "ADX", "params": {"period": 14}}]

    A name the registry does not know is skipped with a warning rather than
    killing the engine at startup -- a typo in a settings file should not take
    trading down -- but it is never swallowed silently, because a filter that
    quietly does not exist is worse than one that fails loudly. That exact
    swallowing is what let the walk-forward harness run for weeks reporting
    results "with ADX" that had no ADX in them.
    """
    engine = IndicatorEngine()
    raw = rt.get("indicators")
    specs: list[tuple[str, dict]] = []
    if isinstance(raw, list) and raw:
        for item in raw:
            if isinstance(item, str):
                specs.append((item, {}))
            elif isinstance(item, dict) and item.get("name"):
                params = item.get("params")
                specs.append((str(item["name"]), params if isinstance(params, dict) else {}))
            else:
                logger.warning("ignoring malformed indicator entry: %r", item)
    if not specs:
        specs = DEFAULT_INDICATORS
    for name, params in specs:
        try:
            engine.add_from_registry(name, **params)
        except Exception:
            logger.warning("indicator %s could not be loaded; skipping", name, exc_info=True)
    logger.info("indicators active: %s", ", ".join(n for n, _ in specs))
    return engine


def _deal_price(deals, entry_kind: int) -> float | None:
    """Price of the opening (0) or closing (1) deal of a position.

    MT5 returns every deal on a position, and picking by list position breaks
    on partial closes and on any ordering the terminal chooses. The `entry`
    field says which is which, so ask for that instead. Later deals win for
    the closing side, so a partially closed trade reports the price it finally
    left at.
    """
    found = None
    for d in deals or ():
        try:
            if int(getattr(d, "entry", -1)) != entry_kind:
                continue
            price = float(getattr(d, "price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if price:
            found = price
            if entry_kind == 0:
                break
    return found


def _int_or_none(v) -> int | None:
    """An absent setting and a set-to-zero setting mean different things."""
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


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

        self.indicators = _build_indicators(acc_settings)

        self.strategies = StrategyEngine()
        self.strategies.configure_live(parse_strategy_names(account.strategy_names))

        self._explicit_entry_cap = _int_or_none(acc_settings.get("max_entries_per_day"))
        self._explicit_position_cap = _int_or_none(acc_settings.get("max_open_positions"))

        self.signals = SignalEngine(accept_threshold=55.0)
        self.risk = RiskEngine(self._limits_from(acc_settings))

    def _autopilot(self, rt: dict, limits: RiskLimits) -> RiskLimits:
        """Derive the sizing limits from evidence rather than from settings.

        On by default. Everything except the daily loss budget is arithmetic
        once you know that budget and what the journal says about expectancy --
        and hand-entering them independently is what produced a config where
        risk per trade equalled the daily cap, so one loss ended the day.

        The daily budget itself stays whatever the settings say (2% default);
        risk appetite is not a fact the bot can measure, and a bot that picks
        its own maximum loss has no maximum loss.
        """
        if str(rt.get("autopilot", True)).lower() in ("0", "false", "no", "off"):
            return limits
        try:
            exp = Experience.from_journal(self.account.journal_path(DATA_DIR))
            groups = independent_groups(self.symbols)
            p = autopilot_plan(
                max_daily_loss=limits.max_daily_loss,
                experience=exp,
                correlation_groups=groups,
            )
        except Exception:
            logger.exception("[%s] autopilot failed; keeping configured limits", self.log_tag)
            return limits

        # An explicitly configured throughput limit is the operator's call and
        # autopilot may raise it but not lower it. It used to overwrite both
        # unconditionally, so a dashboard set to 8 entries a day silently ran
        # at 4 and the setting looked broken -- the same "persisted, threaded,
        # then discarded by a default" shape found half a dozen times in this
        # engine already.
        #
        # Letting the operator open the throttle is safe in a way that is
        # worth being explicit about, because it looks reckless and is not:
        # autopilot derives 4/day from the 2% daily budget at 0.5% risk, but
        # that budget is *separately* enforced by the daily-loss stop. Raising
        # the entry count does not raise the amount that can be lost in a day;
        # it only means the day ends when the money runs out rather than when
        # the counter does. What it does raise is the number of correlated
        # bets open at once, which is why max_open_positions stays bounded by
        # the number of independent groups unless deliberately set higher.
        entry_cap = max(p.max_entries_per_day, self._explicit_entry_cap or 0)             if self._explicit_entry_cap else p.max_entries_per_day
        pos_cap = max(p.max_open_positions, self._explicit_position_cap or 0)             if self._explicit_position_cap else p.max_open_positions

        changed = (
            round(limits.risk_per_trade, 5) != round(p.risk_per_trade, 5)
            or limits.max_entries_per_day != entry_cap
            or limits.max_consecutive_losses != p.max_consecutive_losses
            or limits.max_open_positions != pos_cap
        )
        limits.risk_per_trade = p.risk_per_trade
        limits.max_entries_per_day = entry_cap
        limits.max_consecutive_losses = p.max_consecutive_losses
        limits.max_open_positions = pos_cap
        if changed:
            logger.info("[%s] autopilot: %s", self.log_tag, " | ".join(p.reasons))
        return limits

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
            # The streak brake is the primary protection when risk per trade is
            # sized so that max_consecutive_losses * risk lands under the daily
            # cap: the bot pauses for a few hours and comes back, instead of
            # spending the rest of the day denied.
            max_consecutive_losses=max(0, whole("max_consecutive_losses", base.max_consecutive_losses)),
            consecutive_loss_pause_seconds=max(
                0, whole("consecutive_loss_pause_seconds", base.consecutive_loss_pause_seconds)
            ),
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
        # Re-read the operator's caps too: changing them in the dashboard has
        # to take effect without restarting the engine.
        self._explicit_entry_cap = _int_or_none(settings.get("max_entries_per_day"))
        self._explicit_position_cap = _int_or_none(settings.get("max_open_positions"))

        # Strategy selection was read once, at construction. Changing it in
        # the dashboard therefore did nothing until someone restarted the
        # engine -- and nothing said so, which is the same shape as the
        # entries-per-day cap and the indicator list: a setting that persists,
        # reloads, and is then ignored by the thing it configures. Re-applying
        # it here costs one comparison per cycle.
        wanted = parse_strategy_names(settings.get("strategy_names")
                                      or settings.get("strategies"))
        # Compare as sets. enabled_names() returns registry order, the
        # setting returns whatever order it was written in, and comparing the
        # two as lists made every cycle look like a change -- reconfiguring
        # the engine sixty times an hour and filling the log with a rename
        # that never happened.
        current = self.strategies.enabled_names()
        if set(wanted) != set(current):
            logger.info("[%s] strategy set changed: %s -> %s",
                        self.log_tag, sorted(current), sorted(wanted))
            self.strategies.configure_live(wanted)
        # Which of the enabled strategies may trade which symbol. Optional;
        # an absent or empty map keeps every symbol open to every enabled
        # strategy. Re-read per cycle like the rest of the settings.
        sym_map = parse_symbol_strategies(settings.get("symbol_strategies"))
        if sym_map != self.strategies.symbol_map():
            logger.info("[%s] symbol/strategy map: %s", self.log_tag,
                        {k: sorted(v) for k, v in sorted(sym_map.items())} or "(none)")
            self.strategies.configure_symbol_map(sym_map)

        self.risk.limits = self._autopilot(settings, self._limits_from(settings))
        # Keep the universe picker in step with the configured position cap,
        # and let it propose one extra candidate per cycle -- the brains and
        # risk engine remain the actual gatekeepers.
        self.picker.max_open = self.risk.limits.max_open_positions
        self.picker.max_new = 3
        if self.pipeline is not None:
            self.pipeline.account_mode = self.account_mode
            # The trade-power layer reads its gate settings from here. Without
            # this line `require_proven_edge` was unreachable: the pipeline had
            # no runtime_settings attribute at all, so the lookup fell through
            # to its default on every cycle and the setting did nothing while
            # appearing to be honoured. That is the same shape as the entry
            # cap, the indicator list, the strategy selection and the master
            # switch before them -- a value that persists, reloads, and is then
            # ignored by the code it configures. Refreshed per cycle so a
            # change takes effect without a restart.
            self.pipeline.runtime_settings = settings
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
        self.trade_manager = TradeManager(
            self.broker, self.positions,
            journal=self.journal,
            # The engine itself, so the horizon is read off the strategy that
            # declared it at the moment it is needed.
            strategies=self.strategies,
        )
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

    async def _recover_broker(self, exc: BaseException | None = None) -> bool:
        """Rebuild the MT5 bridge connection and the tick stream after a drop.

        broker.connect() goes through _load_mt5, which pings the cached RPyC
        connection and evicts it when the socket is dead, so calling it again
        is the whole reconnect. The tick stream task ends itself on the same
        error, and nothing restarted it either, so candles kept coming from
        the cache while the "latest tick" quietly aged. Restart both, then
        reconcile, because positions may have changed while we were blind.

        Returns True when the bridge answers again. Failure is logged and
        left for the next cycle; the bridge coming back is not ours to hurry.
        """
        logger.warning("[%s] broker connection lost (%s); reconnecting to %s:%s",
                       self.log_tag, type(exc).__name__ if exc else "unknown",
                       self.account.rpc_host, self.account.rpc_port)
        try:
            ok = await self.broker.connect()
        except Exception:
            logger.exception("[%s] broker reconnect raised", self.log_tag)
            return False
        if not ok:
            logger.warning("[%s] broker reconnect failed; will retry next cycle", self.log_tag)
            return False
        if self.market_data is not None and not getattr(self.market_data, "_running", True):
            try:
                await self.market_data.start()
            except Exception:
                logger.exception("[%s] tick stream restart failed", self.log_tag)
        try:
            await self.reconciler.reconcile()
        except Exception:
            logger.exception("[%s] reconcile after reconnect failed", self.log_tag)
        logger.info("[%s] broker reconnected", self.log_tag)
        telegram_notify(f"🔌 اتصال MT5 دوباره برقرار شد ({self.log_tag})")
        return True

    async def _cycle(self) -> None:
        _post_heartbeat()
        rt = _load_runtime()
        self._apply_runtime(rt)
        self.news.load_from_disk()
        # OFF from either authority wins. _apply_runtime has just set
        # master_bot_on from the settings file; _poll_ops then used to
        # overwrite it outright with the ops API's value, and ops.py caches
        # that in memory at import. So setting master_bot_enabled=False in the
        # settings file did nothing at all while the API stayed up holding a
        # stale True: measured on 2026-09-02, the file said False from 22:18
        # and the engine ran master=ON for seven more hours and took four
        # trades. The stop only took effect when a reboot restarted the API.
        #
        # A kill switch that a stale cache can veto is not a kill switch.
        # Either source may stop trading; neither may start it against the
        # other, which is the safe asymmetry.
        file_master = self.master_bot_on
        ops_master, flatten_seq, self._ops_poll_fail_count = _poll_ops(
            self.master_bot_on, self._ops_poll_fail_count
        )
        self.master_bot_on = bool(file_master and ops_master)
        if file_master != ops_master:
            logger.warning(
                "[%s] master disagreement: settings=%s ops=%s -> trading %s",
                self.log_tag, file_master, ops_master,
                "ON" if self.master_bot_on else "OFF",
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
            before = {str(p.ticket): p for p in self.positions.get_all()}
            try:
                await self.positions.sync_from_broker()
            except Exception as exc:
                logger.exception("[%s] position sync failed; skipping new entries this cycle", self.log_tag)
                # The bridge socket dies whenever the MT5 terminal or the
                # RPyC server restarts, and the engine used to stay dead with
                # it: connect() ran once at startup, so every later cycle hit
                # the same closed stream and logged this same line until
                # someone restarted the container by hand. On 2026-09-03 that
                # was twice in one afternoon, 5 and 1 minutes of no trading
                # after the bridge was already back. Rebuild the connection
                # here so the next cycle gets a live one.
                await self._recover_broker(exc)
                return
            after = {str(p.ticket) for p in self.positions.get_all()}
            gone = [t for t in before if t not in after]
            if gone:
                await self._record_closes(gone, before)
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
                    filled = await self._evaluate_symbol(
                        cand.symbol,
                        tf,
                        h1_side=cand.h1_side,
                        overlap=overlap,
                        tick_spread=cand.spread,
                        universe_score=cand.score,
                    )
                except Exception:
                    logger.exception("LIVE cycle error on %s %s", cand.symbol, tf.value)
                    continue
                if filled:
                    # One position per symbol per cycle. The picker excludes
                    # symbols already open, but it reads a snapshot taken at
                    # the top of the cycle, so M15 and M5 both saw XAUUSD as
                    # flat and both opened a SELL seconds apart -- two
                    # positions on one instrument, double the intended risk.
                    # Sweeping both bar sizes is for more chances to find a
                    # trade, not for taking the same one twice.
                    logger.info("[%s] %s filled on %s; skipping its remaining timeframes this cycle", self.log_tag, cand.symbol, tf.value)
                    break

    async def _record_closes(self, tickets: list[str], before: dict) -> None:
        """Write a close record, in R, for each position the broker has shut.

        Nothing ever did this. The journal only held skip/veto/accept/fill, so
        last_closed_r() always returned an empty list -- the loss streak was
        permanently 0, the experience layer had nothing to learn from, and the
        autopilot was pinned to its floor for good. Every outcome-driven
        behaviour in the engine was running on an empty tank.

        A position vanishing between two broker syncs means it closed, by stop,
        target or hand. Realised profit comes from the broker's own deal
        history and the risk it was opened with from the fill record, so R is
        profit / risk -- comparable across symbols and sizes as dollars are not.
        """
        try:
            risk_by_ticket = self.journal.risk_by_ticket()
        except Exception:
            logger.debug("could not read fill risks", exc_info=True)
            risk_by_ticket = {}

        for ticket in tickets:
            pos = before.get(ticket)
            symbol = getattr(pos, "symbol", None)
            profit = None
            deals = None
            try:
                deals = self.broker._mt5.history_deals_get(position=int(ticket))
                if deals:
                    profit = sum(
                        float(getattr(d, "profit", 0) or 0)
                        + float(getattr(d, "swap", 0) or 0)
                        + float(getattr(d, "commission", 0) or 0)
                        for d in deals
                    )
            except Exception:
                logger.debug("deal history unavailable for %s", ticket, exc_info=True)

            risk = risk_by_ticket.get(str(ticket))
            r = round(profit / risk, 3) if (profit is not None and risk) else None

            # Why it ended, so losses can be analysed rather than just counted.
            # "stopped" and "target" are the strategy working as designed;
            # anything else is the bot or the operator intervening, and those
            # want telling apart when the record is reviewed.
            exit_reason = None
            try:
                sl = float(getattr(pos, "stop_loss", 0) or 0)
                tp = float(getattr(pos, "take_profit", 0) or 0)
                entry = float(getattr(pos, "entry_price", 0) or 0)
                last = None
                if deals:
                    last = float(getattr(deals[-1], "price", 0) or 0)
                if last and entry:
                    d_sl = abs(last - sl) if sl else None
                    d_tp = abs(last - tp) if tp else None
                    if d_sl is not None and (d_tp is None or d_sl <= d_tp):
                        exit_reason = "stopped"
                    elif d_tp is not None:
                        exit_reason = "target"
                if exit_reason is None and r is not None:
                    exit_reason = "closed_up" if r > 0 else "closed_down"
            except Exception:
                logger.debug("could not classify exit for %s", ticket, exc_info=True)

            self.journal.append(
                "close",
                ticket=ticket,
                symbol=symbol,
                side=getattr(pos, "side", None),
                profit=None if profit is None else round(profit, 2),
                risk_amount=risk,
                r_multiple=r,
                exit_reason=exit_reason,
                strategy=getattr(pos, "strategy", None),
                # The price it actually left at, from the closing deal. An
                # exit without a price is the same gap the entry had: the
                # trade cannot be reconciled against the broker afterwards.
                exit_price=_deal_price(deals, 1) or (
                    (float(getattr(deals[-1], "price", 0) or 0) or None) if deals else None),
                # Prefer the broker's opening deal over the cached position
                # object. `before` is a snapshot taken before the position
                # vanished, and whether it carries an entry price depends on
                # how it was built -- when it does not, the record loses the
                # one number that makes the exit meaningful. The deal history
                # always has it.
                entry_price=_deal_price(deals, 0) or (
                    float(getattr(pos, "entry_price", 0) or 0) or None),
            )
            if r is None:
                logger.info("[%s] CLOSED %s %s (result unknown)", self.log_tag, symbol, ticket)
                continue
            logger.info("[%s] CLOSED %s %s -> %+.2f (%.2fR)", self.log_tag, symbol, ticket, profit, r)
            telegram_notify(
                ("🟢" if r > 0 else "🔴") + " <b>معامله بسته شد</b>" + '\n'
                + "نماد: " + str(symbol) + '\n'
                + "نتیجه: %+.2f$  (%+.2fR)" % (profit, r)
            )

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
            # A symbol no enabled strategy may trade must not compete for a
            # candidate slot. The picker keeps only its top few by score and
            # knows nothing about the symbol map, so closed symbols were
            # crowding out open ones: with USDCAD, USDCHF and USDJPY shut, the
            # three slots still went to them, and XAUUSD -- the best validated
            # edge on the account -- was not evaluated once in 45 minutes.
            # Filtering here rather than inside UniversePicker keeps the picker
            # a pure ranker and puts the policy next to the settings it reads.
            if self.strategies is not None and not self.strategies.allowed_for(symbol):
                continue
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

    async def _evaluate_symbol(self, symbol: str, trade_tf: TimeFrame, *, h1_side: str | None, overlap: bool, tick_spread: float | None, universe_score: float | None = None) -> bool:
        """Evaluate one symbol on one timeframe. True if an order was filled."""
        raw = await self.market_data.get_candles(symbol, trade_tf, count=160, use_cache=False)
        if not raw:
            return False
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
            return False
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
            return True
        elif result.exec_result and not result.exec_result.success:
            logger.warning("%s exec failed: %s", symbol, result.exec_result.message)
        return False

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
