"""
Advanced Risk Engine (Master Prompt §11).

HARD RULE: No path may bypass this engine.
If any check fails → NO TRADE.
Position sizing is based on Stop Distance × Risk Budget (not fixed lots).
"""

from __future__ import annotations
import math
from datetime import datetime, timezone

from molido_risk.models import (
    AccountState,
    RiskContext,
    RiskDecision,
    RiskLimits,
    RiskResult,
)


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self._circuit_open: bool = False
        self._circuit_reason: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, ctx: RiskContext) -> RiskResult:
        """
        Main entry. Returns ALLOW / REDUCE / DENY with lot size when allowed.
        """
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        # 0. Circuit breaker
        if self._circuit_open:
            return self._deny(f"Circuit breaker open: {self._circuit_reason}", checks)

        # EXIT orders are always allowed (closing risk is reducing risk)
        if ctx.is_exit or ctx.side == "EXIT":
            return RiskResult(
                decision=RiskDecision.ALLOW,
                lot_size=0.0,
                reasons=["EXIT order – risk reduction"],
                checks={"exit": True},
            )

        limits = ctx.limits or self.limits
        account = ctx.account

        # 1. Mandatory Stop-Loss
        checks["stop_loss"] = not (limits.require_stop_loss and ctx.stop_loss is None)
        if not checks["stop_loss"]:
            return self._deny("Stop-Loss is mandatory", checks)

        # 2. Entry / SL sanity
        if ctx.entry is None or ctx.stop_loss is None or ctx.entry <= 0:
            return self._deny("Invalid entry or stop-loss", checks)
        stop_distance = abs(ctx.entry - ctx.stop_loss)
        if stop_distance <= 0:
            return self._deny("Stop distance is zero", checks)
        checks["stop_distance"] = True

        # 3. Minimum R:R
        rr = ctx.risk_reward
        if rr is None and ctx.take_profit is not None:
            reward = abs(ctx.take_profit - ctx.entry)
            rr = reward / stop_distance if stop_distance else 0
        checks["min_rr"] = rr is None or rr >= limits.min_risk_reward
        if not checks["min_rr"]:
            return self._deny(f"R:R {rr:.2f} < minimum {limits.min_risk_reward}", checks)

        # 4. Spread limit
        if ctx.spread_points is not None:
            checks["spread"] = ctx.spread_points <= limits.max_spread_points
            if not checks["spread"]:
                return self._deny(
                    f"Spread {ctx.spread_points:.1f} > max {limits.max_spread_points}",
                    checks,
                )
        else:
            checks["spread"] = True

        # 5. Daily loss limit
        if account.equity > 0:
            daily_loss_pct = -account.daily_pnl / account.equity if account.daily_pnl < 0 else 0.0
            checks["daily_loss"] = daily_loss_pct < limits.max_daily_loss
            if not checks["daily_loss"]:
                self.trip_circuit(f"Daily loss limit hit ({daily_loss_pct:.2%})")
                return self._deny(
                    f"Daily loss {daily_loss_pct:.2%} >= limit {limits.max_daily_loss:.2%}",
                    checks,
                )
        else:
            checks["daily_loss"] = False
            return self._deny("Equity is zero or negative", checks)

        # 6. Max drawdown
        peak = account.peak_equity or account.equity
        if peak > 0:
            dd = (peak - account.equity) / peak
            checks["drawdown"] = dd < limits.max_drawdown
            if not checks["drawdown"]:
                self.trip_circuit(f"Max drawdown hit ({dd:.2%})")
                return self._deny(
                    f"Drawdown {dd:.2%} >= limit {limits.max_drawdown:.2%}",
                    checks,
                )
        else:
            checks["drawdown"] = True

        # 7. Weekly loss
        if account.equity > 0 and account.weekly_pnl < 0:
            weekly_loss_pct = -account.weekly_pnl / account.equity
            checks["weekly_loss"] = weekly_loss_pct < limits.max_weekly_loss
            if not checks["weekly_loss"]:
                return self._deny(
                    f"Weekly loss {weekly_loss_pct:.2%} >= limit {limits.max_weekly_loss:.2%}",
                    checks,
                )
        else:
            checks["weekly_loss"] = True

        # 8. Max open positions
        checks["max_positions"] = account.open_positions < limits.max_open_positions
        if not checks["max_positions"]:
            return self._deny(
                f"Open positions {account.open_positions} >= max {limits.max_open_positions}",
                checks,
            )

        # 9. Cooldown
        if account.last_trade_at and limits.cooldown_seconds > 0:
            elapsed = (datetime.now(timezone.utc) - account.last_trade_at).total_seconds()
            checks["cooldown"] = elapsed >= limits.cooldown_seconds
            if not checks["cooldown"]:
                return self._deny(
                    f"Cooldown {elapsed:.0f}s < {limits.cooldown_seconds}s",
                    checks,
                )
        else:
            checks["cooldown"] = True

        # 10. Volatility regime adjustment
        risk_mult = 1.0
        if ctx.regime in ("High Volatility", "Extreme Volatility"):
            if ctx.regime == "Extreme Volatility" and limits.extreme_vol_block:
                return self._deny("Extreme volatility – new entries blocked", checks)
            risk_mult = limits.high_vol_risk_mult
            reasons.append(f"Risk reduced x{risk_mult} due to {ctx.regime}")

        # 11. Position sizing from risk budget + stop distance
        risk_pct = limits.risk_per_trade * risk_mult
        risk_amount = account.equity * risk_pct

        # Approximate pip value: for most FX pairs 1 lot ≈ $10 per pip when quote is USD
        # stop_distance is in price units; convert roughly to lots
        # lot_size = risk_amount / (stop_distance * contract_size * pip_value_factor)
        # Simplified model used here (can be refined per symbol in broker adapter):
        pip_size = self._estimate_pip_size(ctx.entry)
        stop_pips = stop_distance / pip_size if pip_size > 0 else 0
        if stop_pips <= 0:
            return self._deny("Invalid stop pips", checks)

        # $ risk per lot ≈ stop_pips * $10 for standard FX (rough)
        risk_per_lot = stop_pips * 10.0
        if risk_per_lot <= 0:
            return self._deny("Risk per lot is zero", checks)

        raw_lots = risk_amount / risk_per_lot
        lot_size = self._normalize_lot(raw_lots, limits)

        if lot_size < limits.min_lot_size:
            return self._deny(
                f"Calculated lot {lot_size:.4f} below minimum {limits.min_lot_size}",
                checks,
            )

        # 12. Symbol exposure
        symbol_risk = risk_amount
        current_symbol = account.symbol_exposure.get(ctx.symbol, 0.0)
        max_symbol = account.equity * limits.max_symbol_exposure
        checks["symbol_exposure"] = (current_symbol + symbol_risk) <= max_symbol
        if not checks["symbol_exposure"]:
            # Try reduce
            remaining = max(0.0, max_symbol - current_symbol)
            if remaining >= account.equity * limits.risk_per_trade * 0.25:
                lot_size = self._normalize_lot(
                    (remaining / risk_per_lot), limits
                )
                risk_amount = remaining
                reasons.append("Lot reduced to fit symbol exposure limit")
                decision = RiskDecision.REDUCE
            else:
                return self._deny("Symbol exposure limit reached", checks)
        else:
            decision = RiskDecision.ALLOW

        # 13. Portfolio exposure
        max_port = account.equity * limits.max_portfolio_exposure
        checks["portfolio_exposure"] = (account.portfolio_risk + risk_amount) <= max_port
        if not checks["portfolio_exposure"]:
            remaining = max(0.0, max_port - account.portfolio_risk)
            if remaining >= account.equity * limits.risk_per_trade * 0.25:
                lot_size = self._normalize_lot(remaining / risk_per_lot, limits)
                risk_amount = remaining
                reasons.append("Lot reduced to fit portfolio exposure limit")
                decision = RiskDecision.REDUCE
            else:
                return self._deny("Portfolio exposure limit reached", checks)

        # 14. Max lot hard cap
        if lot_size > limits.max_lot_size:
            lot_size = limits.max_lot_size
            reasons.append(f"Lot capped at max_lot_size={limits.max_lot_size}")
            decision = RiskDecision.REDUCE

        checks["position_sizing"] = lot_size >= limits.min_lot_size

        if not reasons:
            reasons.append(
                f"Risk {risk_pct:.2%} of equity (${risk_amount:.2f}) → {lot_size:.2f} lots"
            )

        return RiskResult(
            decision=decision,
            lot_size=round(lot_size, 4),
            risk_amount=round(risk_amount, 2),
            reasons=reasons,
            checks=checks,
            meta={
                "stop_pips": round(stop_pips, 1),
                "risk_pct": risk_pct,
                "risk_mult": risk_mult,
            },
        )

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def trip_circuit(self, reason: str) -> None:
        self._circuit_open = True
        self._circuit_reason = reason

    def reset_circuit(self) -> None:
        self._circuit_open = False
        self._circuit_reason = None

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _deny(self, reason: str, checks: dict[str, bool]) -> RiskResult:
        return RiskResult(
            decision=RiskDecision.DENY,
            lot_size=0.0,
            risk_amount=0.0,
            reasons=[reason],
            checks=checks,
        )

    @staticmethod
    def _estimate_pip_size(price: float) -> float:
        """Rough pip size heuristic."""
        if price > 50:          # JPY pairs, gold-ish
            return 0.01
        if price > 5:
            return 0.01
        return 0.0001           # standard 5-digit FX

    @staticmethod
    def _normalize_lot(raw: float, limits: RiskLimits) -> float:
        if raw < limits.min_lot_size:
            return 0.0
        steps = math.floor(raw / limits.lot_step)
        lot = steps * limits.lot_step
        return min(lot, limits.max_lot_size)

    @staticmethod
    def limits_for_prop(
        base: RiskLimits,
        max_daily_loss_pct: float | None,
        max_drawdown_pct: float | None,
    ) -> RiskLimits:
        """Build stricter limits for PROP accounts."""
        lim = RiskLimits(
            risk_per_trade=min(base.risk_per_trade, 0.005),
            max_daily_loss=(max_daily_loss_pct / 100.0) if max_daily_loss_pct else base.max_daily_loss,
            max_weekly_loss=base.max_weekly_loss,
            max_drawdown=(max_drawdown_pct / 100.0) if max_drawdown_pct else base.max_drawdown,
            max_open_positions=base.max_open_positions,
            max_portfolio_exposure=base.max_portfolio_exposure,
            max_symbol_exposure=base.max_symbol_exposure,
            max_lot_size=base.max_lot_size,
            min_lot_size=base.min_lot_size,
            lot_step=base.lot_step,
            max_leverage=base.max_leverage,
            min_risk_reward=base.min_risk_reward,
            max_spread_points=base.max_spread_points,
            require_stop_loss=True,
            cooldown_seconds=base.cooldown_seconds,
            high_vol_risk_mult=base.high_vol_risk_mult,
            extreme_vol_block=True,
        )
        return lim
