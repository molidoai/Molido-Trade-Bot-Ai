"""
Core trading pipeline (Master Prompt section 52):

  Strategy -> Signal -> Brain -> Risk -> Execution -> Broker

This module wires all engines together. Used by Paper, Demo and Live loops.
Nothing here bypasses RiskEngine. The brain may only veto, never enlarge size.
"""

from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from molido_shared.types import Candle, TimeFrame, Side
from molido_indicators.engine import IndicatorEngine
from molido_strategies.engine import StrategyEngine
from molido_strategies.base import SignalSide
from molido_signals.engine import SignalEngine, FinalSignal
from molido_risk import RiskEngine, RiskContext, RiskLimits, AccountState, RiskDecision
from molido_execution import ExecutionEngine, ExecRequest, ExecResult
from molido_portfolio import PositionManager, PortfolioManager, Reconciler
try:
    from molido_guards import TradingHoursGuard, NewsBlackoutGuard, correlated_block
    from molido_regime import MarketRegimeEngine
except ImportError:
    TradingHoursGuard = NewsBlackoutGuard = MarketRegimeEngine = None  # type: ignore
    correlated_block = None  # type: ignore
try:
    from molido_brain import DecisionBrain
except ImportError:
    DecisionBrain = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    signal: FinalSignal | None = None
    risk_allowed: bool = False
    lot_size: float = 0.0
    exec_result: ExecResult | None = None
    skipped_reason: str | None = None
    p_win: float | None = None
    expected_r: float | None = None
    size_mult: float | None = None


class TradingPipeline:
    def __init__(
        self,
        indicator_engine: IndicatorEngine,
        strategy_engine: StrategyEngine,
        signal_engine: SignalEngine,
        risk_engine: RiskEngine,
        execution_engine: ExecutionEngine,
        position_manager: PositionManager,
        portfolio_manager: PortfolioManager,
        reconciler: Reconciler,
        account_mode: str = "DEMO",
        risk_limits: RiskLimits | None = None,
        brain: object | None = None,
        journal: object | None = None,
    ):
        self.indicators = indicator_engine
        self.strategies = strategy_engine
        self.signals = signal_engine
        self.risk = risk_engine
        self.execution = execution_engine
        self.positions = position_manager
        self.portfolio = portfolio_manager
        self.reconciler = reconciler
        self.account_mode = account_mode
        # Stale copy kept only for callers that still pass risk_limits;
        # evaluate() uses self.risk.limits.
        self.risk_limits = risk_limits or self.risk.limits
        self.journal = journal
        if brain is not None:
            self.brain = brain
        elif DecisionBrain is not None:
            self.brain = DecisionBrain()
        else:
            self.brain = None

    def _journal(self, event: str, **fields: Any) -> None:
        if self.journal is None:
            return
        try:
            self.journal.append(event, **fields)
        except Exception:
            logger.exception("journal append failed")

    async def on_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        candles: Sequence[Candle],
        regime: str | None = None,
        master_bot_on: bool = True,
        h1_side: str | None = None,
        spread: float | None = None,
        tick: Any | None = None,
        swap_r: float | None = None,
        overlap: bool | None = None,
    ) -> PipelineResult:
        """
        One evaluation cycle for a symbol.
        """
        if not master_bot_on:
            self._journal("skip", symbol=symbol, reason="Master bot is OFF")
            return PipelineResult(skipped_reason="Master bot is OFF")

        if TradingHoursGuard is not None:
            ok_h, why_h = TradingHoursGuard().allow_new_entries()
            if not ok_h:
                self._journal("skip", symbol=symbol, reason=f"TradingHours: {why_h}")
                return PipelineResult(skipped_reason=f"TradingHours: {why_h}")

        if NewsBlackoutGuard is not None:
            ok_n, why_n = NewsBlackoutGuard().allow_new_entries(symbol=symbol)
            if not ok_n:
                self._journal("skip", symbol=symbol, reason=f"NewsBlackout: {why_n}")
                return PipelineResult(skipped_reason=f"NewsBlackout: {why_n}")

        can, reason = self.reconciler.can_accept_new_entries()
        if not can:
            self._journal("skip", symbol=symbol, reason=reason)
            return PipelineResult(skipped_reason=reason)

        if len(candles) < 30:
            return PipelineResult(skipped_reason="Not enough candles")

        ind_latest = self.indicators.compute_latest(candles)

        open_side = None
        open_positions = self.positions.by_symbol(symbol)
        if open_positions:
            open_side = Side.BUY if open_positions[0].side.upper() == "BUY" else Side.SELL

        raw_signals = self.strategies.evaluate_all(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            indicators=ind_latest,
            regime=regime,
            account_mode=self.account_mode,
            open_position_side=open_side,
        )

        finals = self.signals.process(raw_signals, indicators=ind_latest, pick_best=True)
        if not finals:
            self._journal("skip", symbol=symbol, reason="No signals")
            return PipelineResult(skipped_reason="No signals")

        final = finals[0]

        if final.side == SignalSide.EXIT and open_positions:
            pos = open_positions[0]
            req = ExecRequest(
                symbol=symbol,
                side="EXIT",
                volume=pos.volume,
                reduce_only=True,
                position_ticket=pos.ticket,
                client_order_id=str(uuid.uuid4()),
                strategy=final.strategy,
            )
            exec_res = await self.execution.execute(req)
            await self.positions.sync_from_broker()
            self._journal(
                "exit",
                symbol=symbol,
                ticket=str(pos.ticket),
                fill_price=getattr(exec_res, "fill_price", None),
            )
            return PipelineResult(
                signal=final,
                risk_allowed=True,
                exec_result=exec_res,
            )

        if not final.accepted or final.side not in (SignalSide.BUY, SignalSide.SELL):
            self._journal("skip", symbol=symbol, reason=final.reject_reason or final.side.value)
            return PipelineResult(
                signal=final,
                skipped_reason=final.reject_reason or final.side.value,
            )

        spread_pts = spread
        if spread_pts is None and candles and candles[-1].spread is not None:
            spread_pts = float(candles[-1].spread)
        spread_price = None
        if tick is not None:
            spread_price = getattr(tick, "spread", None)

        atr_val = None
        atr_res = ind_latest.get("ATR") or ind_latest.get("atr14")
        if atr_res:
            atr_val = atr_res.get("atr")

        journal_stats = None
        if self.journal is not None and hasattr(self.journal, "journal_stats"):
            try:
                journal_stats = self.journal.journal_stats(20)
            except Exception:
                journal_stats = None

        p_win = None
        expected_r = None
        size_mult = 1.0
        if self.brain is not None:
            side_val = final.side.value if hasattr(final.side, "value") else str(final.side)
            agreeing = sum(
                1
                for s in raw_signals
                if (s.side.value if hasattr(s.side, "value") else str(s.side)) == side_val
            ) or 1
            verdict = self.brain.decide(
                final,
                indicators=ind_latest,
                regime=regime,
                agreeing=agreeing,
                h1_side=h1_side,
                spread=spread_price if spread_price is not None else spread_pts,
                journal_stats=journal_stats,
                swap_r=swap_r,
                candles=candles,
                overlap=overlap,
            )
            p_win = verdict.p_win
            expected_r = verdict.expected_r
            size_mult = min(1.0, float(getattr(verdict, "size_mult", 1.0) or 0.0))
            if size_mult > 1.0:
                size_mult = 1.0
            final.reasons.extend(verdict.reasons)
            final.meta = {
                **(final.meta or {}),
                "p_win": p_win,
                "ev_r": expected_r,
                "size_mult": size_mult,
            }
            if not verdict.allow or size_mult <= 0:
                logger.info("Brain VETO %s: %s", symbol, "; ".join(verdict.reasons))
                self._journal(
                    "veto",
                    symbol=symbol,
                    side=side_val,
                    p_win=p_win,
                    expected_r=expected_r,
                    spread=spread_price or spread_pts,
                    reason="; ".join(verdict.reasons),
                )
                return PipelineResult(
                    signal=final,
                    skipped_reason="; ".join(verdict.reasons),
                    p_win=p_win,
                    expected_r=expected_r,
                    size_mult=0.0,
                )

        snap = await self.portfolio.snapshot()
        account_state = self.portfolio.to_account_state(snap)

        if correlated_block is not None:
            ok_c, why_c = correlated_block(symbol, account_state.open_symbols)
            if not ok_c:
                self._journal("skip", symbol=symbol, reason=why_c, p_win=p_win, spread=spread_pts)
                return PipelineResult(
                    signal=final,
                    skipped_reason=f"correlation: {why_c}",
                    p_win=p_win,
                    expected_r=expected_r,
                    size_mult=size_mult,
                )

        limits = self.risk.limits
        risk_ctx = RiskContext(
            symbol=symbol,
            side=final.side.value,
            entry=final.entry,
            stop_loss=final.stop_loss,
            take_profit=final.take_profit,
            signal_score=final.score,
            risk_reward=final.risk_reward,
            spread_points=spread_pts,
            atr=atr_val,
            regime=regime,
            account=account_state,
            limits=limits,
        )
        risk_result = self.risk.evaluate(risk_ctx)

        if not risk_result.allowed:
            logger.info("Risk DENY %s: %s", symbol, risk_result.reasons)
            self._journal(
                "veto",
                symbol=symbol,
                side=final.side.value,
                p_win=p_win,
                spread=spread_pts,
                reason="; ".join(risk_result.reasons),
            )
            return PipelineResult(
                signal=final,
                risk_allowed=False,
                skipped_reason="; ".join(risk_result.reasons),
                p_win=p_win,
                expected_r=expected_r,
                size_mult=size_mult,
            )

        lot = risk_result.lot_size * min(1.0, size_mult)
        if lot < limits.min_lot_size:
            self._journal("skip", symbol=symbol, reason="size_mult reduced lot below min", p_win=p_win)
            return PipelineResult(
                signal=final,
                skipped_reason="size_mult reduced lot below min",
                p_win=p_win,
                expected_r=expected_r,
                size_mult=size_mult,
            )

        self._journal(
            "accept",
            symbol=symbol,
            side=final.side.value,
            p_win=p_win,
            expected_r=expected_r,
            spread=spread_price or spread_pts,
            lot=lot,
            size_mult=size_mult,
        )

        comment = f"{final.strategy}|sc={final.score:.0f}"
        if p_win is not None:
            comment += f"|p={p_win:.2f}"

        order_type = "LIMIT"
        price = None
        if tick is not None:
            if final.side == SignalSide.BUY:
                price = getattr(tick, "ask", None)
            else:
                price = getattr(tick, "bid", None)
        if price is None:
            price = final.entry
        if price is None:
            order_type = "MARKET"

        req = ExecRequest(
            symbol=symbol,
            side=final.side.value,
            volume=lot,
            order_type=order_type,
            price=price,
            stop_loss=final.stop_loss,
            take_profit=final.take_profit,
            client_order_id=str(uuid.uuid4()),
            strategy=final.strategy,
            signal_score=final.score,
            risk_amount=risk_result.risk_amount * min(1.0, size_mult),
            comment=comment,
        )
        exec_res = await self.execution.execute(req)
        await self.positions.sync_from_broker()

        if exec_res and exec_res.success:
            self._journal(
                "fill",
                symbol=symbol,
                side=final.side.value,
                p_win=p_win,
                spread=spread_price or spread_pts,
                fill_price=exec_res.fill_price,
                lot=lot,
                ticket=exec_res.broker_order_id,
                mae=0.0,
                mfe=0.0,
            )
        else:
            self._journal(
                "skip",
                symbol=symbol,
                reason=getattr(exec_res, "message", "exec failed"),
                p_win=p_win,
            )

        return PipelineResult(
            signal=final,
            risk_allowed=True,
            lot_size=lot,
            exec_result=exec_res,
            p_win=p_win,
            expected_r=expected_r,
            size_mult=size_mult,
        )
