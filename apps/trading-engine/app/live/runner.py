"""
LIVE trading runner.

Reads dashboard runtime settings from RUNTIME_SETTINGS_PATH when present,
then falls back to env. RiskEngine is still mandatory. Session calendar,
point-in-time bars, quality gate and regime are applied before any order.
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
from molido_indicators import IndicatorEngine
from molido_strategies import StrategyEngine
from molido_signals import SignalEngine
from molido_risk import RiskEngine, RiskLimits
from molido_execution import ExecutionEngine
from molido_portfolio import PositionManager, PortfolioManager, Reconciler
from molido_regime import MarketRegimeEngine
from molido_guards import SessionCalendar
from app.orchestration.pipeline import TradingPipeline
from app.data.market_data import MarketDataEngine
from app.live.alerts import notify as telegram_notify

logger = logging.getLogger(__name__)

_TF = {
    "M1": TimeFrame.M1,
    "1M": TimeFrame.M1,
    "1m": TimeFrame.M1,
    "M5": TimeFrame.M5,
    "5M": TimeFrame.M5,
    "5m": TimeFrame.M5,
    "M15": TimeFrame.M15,
    "15M": TimeFrame.M15,
    "15m": TimeFrame.M15,
    "H1": TimeFrame.H1,
    "1H": TimeFrame.H1,
    "1h": TimeFrame.H1,
    "H4": TimeFrame.H4,
    "4H": TimeFrame.H4,
    "4h": TimeFrame.H4,
    "D1": TimeFrame.D1,
    "1D": TimeFrame.D1,
    "1d": TimeFrame.D1,
}


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


def _poll_ops_master(default: bool) -> bool:
    url = os.getenv("OPS_STATE_URL", "http://api:8000/api/v1/ops/state")
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return bool(data.get("master_on", default))
    except Exception:
        logger.debug("ops state poll failed; keeping master=%s", default)
        return default


def _parse_symbols(raw: str) -> list[str]:
    parts = raw.replace(";", ",").split(",")
    out = [p.strip().upper() for p in parts if p.strip()]
    return out or ["EURUSD", "GBPUSD", "XAUUSD"]


class LiveRunner:
    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframe: TimeFrame = TimeFrame.M15,
        cycle_seconds: float = 15.0,
    ):
        rt = _load_runtime()
        self.symbols = symbols or _parse_symbols(_pick(rt, "symbols") or "EURUSD,GBPUSD,XAUUSD")
        tf_raw = _pick(rt, "timeframe") or "M15"
        self.timeframe = timeframe if symbols else _TF.get(tf_raw, _TF.get(tf_raw.upper(), TimeFrame.M15))
        self.cycle_seconds = cycle_seconds
        self.account_mode = (_pick(rt, "trading_account_mode", env="TRADING_ACCOUNT_MODE") or "REAL").upper()
        self.master_bot_on = _env_bool("MASTER_BOT_ENABLED", True)
        if "master_bot_enabled" in rt:
            self.master_bot_on = bool(rt.get("master_bot_enabled"))
        self._running = False
        self.broker = None
        self.execution = None
        self.positions = None
        self.portfolio = None
        self.reconciler = None
        self.pipeline = None
        self.market_data = None
        self.regime = MarketRegimeEngine()
        self.calendar = SessionCalendar()

        self.indicators = IndicatorEngine()
        self.indicators.add_from_registry("MultiEMA")
        self.indicators.add_from_registry("RSI", period=14)
        self.indicators.add_from_registry("ATR", period=14)
        self.indicators.add_from_registry("MACD")
        self.indicators.add_from_registry("BollingerBands", period=20)
        self.indicators.add_from_registry("DonchianChannel", period=20)
        self.indicators.add_from_registry("Supertrend", period=10, multiplier=3.0)

        self.strategies = StrategyEngine()
        self.strategies.add_from_registry("TrendFollowing")
        self.strategies.add_from_registry("DonchianBreakout")
        self.strategies.add_from_registry("RSIMeanReversion")

        self.signals = SignalEngine(accept_threshold=55.0)
        self.risk = RiskEngine(self._limits_from(rt))

    def _limits_from(self, rt: dict) -> RiskLimits:
        def num(key: str, default: float) -> float:
            try:
                return float(rt.get(key, default))
            except (TypeError, ValueError):
                return default

        try:
            max_pos = int(rt.get("max_open_positions", 5))
        except (TypeError, ValueError):
            max_pos = 5
        return RiskLimits(
            risk_per_trade=num("default_risk_per_trade", 0.005),
            max_daily_loss=num("max_daily_loss", 0.02),
            max_drawdown=num("max_drawdown", 0.05),
            max_open_positions=max(1, max_pos),
        )

    def _apply_runtime(self, rt: dict) -> None:
        mode = (_pick(rt, "trading_account_mode", env="TRADING_ACCOUNT_MODE") or self.account_mode).upper()
        self.account_mode = mode
        self.symbols = _parse_symbols(_pick(rt, "symbols") or ",".join(self.symbols))
        tf_raw = _pick(rt, "timeframe") or "M15"
        self.timeframe = _TF.get(tf_raw, _TF.get(tf_raw.upper(), self.timeframe))
        if "master_bot_enabled" in rt:
            self.master_bot_on = bool(rt.get("master_bot_enabled"))
        self.risk.limits = self._limits_from(rt)
        if self.pipeline is not None:
            self.pipeline.account_mode = mode
        if self.portfolio is not None:
            self.portfolio.account_mode = mode
        if self.market_data is not None:
            self.market_data.symbols = self.symbols

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
        self.broker = create_broker(
            BrokerType.MT5,
            login=login,
            password=password,
            server=server,
            path=path,
        )
        self.execution = ExecutionEngine(self.broker)
        self.positions = PositionManager(self.broker)
        self.portfolio = PortfolioManager(self.broker, self.positions, account_mode=self.account_mode)
        self.reconciler = Reconciler(self.broker, self.positions)
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
        )
        self.market_data = MarketDataEngine(
            broker=self.broker,
            symbols=self.symbols,
            stale_threshold_seconds=60.0,
        )

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

        logger.info(
            "LIVE runner starting | mode=%s | master=%s | symbols=%s",
            self.account_mode,
            "ON" if self.master_bot_on else "OFF",
            self.symbols,
        )
        ok = await self.broker.connect()
        if not ok:
            raise RuntimeError(
                "LIVE MT5 connect failed. Need a running MT5 terminal (Windows or Wine) plus valid credentials."
            )
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
        rt = _load_runtime()
        self._apply_runtime(rt)
        self.master_bot_on = _poll_ops_master(self.master_bot_on)
        sess_ok, sess_why = self.calendar.allow_new_entries()
        if not sess_ok:
            logger.info("LIVE session skip: %s", sess_why)
            return
        snap = await self.portfolio.snapshot()
        logger.info(
            "LIVE equity=%.2f | positions=%d | DD=%.2f%% | master=%s | sessions=%s",
            snap.equity,
            snap.open_positions,
            snap.drawdown_pct,
            "ON" if self.master_bot_on else "OFF",
            ",".join(self.calendar.active_sessions()) or "-",
        )
        for symbol in self.symbols:
            try:
                raw = await self.market_data.get_candles(symbol, self.timeframe, count=160)
                if not raw:
                    continue
                try:
                    candles = closed_bars(raw, min_bars=30)
                except InsufficientDataError as exc:
                    logger.debug("%s PIT: %s", symbol, exc)
                    continue
                quality = score_candles(candles)
                if not quality.tradeable:
                    logger.warning("%s quality block score=%.2f %s", symbol, quality.score, quality.findings[:3])
                    continue
                ind = self.indicators.compute_latest(candles)
                regime = self.regime.classify(candles, ind)
                result = await self.pipeline.on_candles(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    candles=candles,
                    regime=regime,
                    master_bot_on=self.master_bot_on,
                )
                if result.skipped_reason:
                    logger.debug("%s skipped: %s", symbol, result.skipped_reason)
                    continue
                if result.exec_result and result.exec_result.success:
                    side = result.signal.side.value if result.signal else "?"
                    logger.info(
                        "%s LIVE FILL %s %.2f lots @ %s | regime=%s",
                        symbol,
                        side,
                        result.lot_size,
                        result.exec_result.fill_price,
                        regime,
                    )
                    telegram_notify(
                        f"Molido FILL {symbol} {side} {result.lot_size} @ {result.exec_result.fill_price} regime={regime}"
                    )
                elif result.exec_result and not result.exec_result.success:
                    logger.warning("%s exec failed: %s", symbol, result.exec_result.message)
            except Exception:
                logger.exception("LIVE cycle error on %s", symbol)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    runner = LiveRunner()
    try:
        await runner.start()
    except KeyboardInterrupt:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
