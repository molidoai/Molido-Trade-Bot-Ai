"""
Core trading pipeline (Master Prompt §52):

  Strategy → Signal → Risk → Execution → Broker

This module wires all engines together. Used by Paper, Demo and (later) Live loops.
Nothing here bypasses RiskEngine.
"""

from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass
from typing import Sequence

from molido_shared.types import Candle, TimeFrame, Side
from molido_indicators.engine import IndicatorEngine
from molido_strategies.engine import StrategyEngine
from molido_strategies.base import SignalSide
from molido_signals.engine import SignalEngine, FinalSignal
from molido_risk import RiskEngine, RiskContext, RiskLimits, AccountState, RiskDecision
from molido_execution import ExecutionEngine, ExecRequest, ExecResult
from molido_portfolio import PositionManager, PortfolioManager, Reconciler

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    signal: FinalSignal | None = None
    risk_allowed: bool = False
    lot_size: float = 0.0
    exec_result: ExecResult | None = None
    skipped_reason: str | None = None


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
        self.risk_limits = risk_limits or RiskLimits()

    async def on_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        candles: Sequence[Candle],
        regime: str | None = None,
        master_bot_on: bool = True,
    ) -> PipelineResult:
        """
        One evaluation cycle for a symbol.
        """
        # Gate: master switch + reconciliation
        if not master_bot_on:
            return PipelineResult(skipped_reason="Master bot is OFF")

        can, reason = self.reconciler.can_accept_new_entries()
        if not can:
            return PipelineResult(skipped_reason=reason)

        if len(candles) < 30:
            return PipelineResult(skipped_reason="Not enough candles")

        # 1. Indicators
        ind_latest = self.indicators.compute_latest(candles)

        # 2. Strategies → raw signals
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

        # 3. Signal Engine (score + threshold)
        finals = self.signals.process(raw_signals, indicators=ind_latest, pick_best=True)
        if not finals:
            return PipelineResult(skipped_reason="No signals")

        final = finals[0]

        # Handle EXIT
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
            return PipelineResult(
                signal=final,
                risk_allowed=True,
                exec_result=exec_res,
            )

        if not final.accepted or final.side not in (SignalSide.BUY, SignalSide.SELL):
            return PipelineResult(
                signal=final,
                skipped_reason=final.reject_reason or final.side.value,
            )

        # 4. Risk Engine
        snap = await self.portfolio.snapshot()
        account_state = self.portfolio.to_account_state(snap)

        # Spread from last candle if available
        spread_pts = None
        if candles and candles[-1].spread is not None:
            spread_pts = float(candles[-1].spread)

        atr_val = None
        atr_res = ind_latest.get("ATR") or ind_latest.get("atr14")
        if atr_res:
            atr_val = atr_res.get("atr")

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
            limits=self.risk_limits,
        )
        risk_result = self.risk.evaluate(risk_ctx)

        if not risk_result.allowed:
            logger.info("Risk DENY %s: %s", symbol, risk_result.reasons)
            return PipelineResult(
                signal=final,
                risk_allowed=False,
                skipped_reason="; ".join(risk_result.reasons),
            )

        # 5. Execution
        req = ExecRequest(
            symbol=symbol,
            side=final.side.value,
            volume=risk_result.lot_size,
            order_type="MARKET",
            stop_loss=final.stop_loss,
            take_profit=final.take_profit,
            client_order_id=str(uuid.uuid4()),
            strategy=final.strategy,
            signal_score=final.score,
            risk_amount=risk_result.risk_amount,
            comment=f"{final.strategy}|sc={final.score:.0f}",
        )
        exec_res = await self.execution.execute(req)
        await self.positions.sync_from_broker()

        return PipelineResult(
            signal=final,
            risk_allowed=True,
            lot_size=risk_result.lot_size,
            exec_result=exec_res,
        )
