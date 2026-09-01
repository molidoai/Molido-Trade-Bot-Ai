"""
Advanced Risk Engine (Master Prompt section 11).

HARD RULE: No path may bypass this engine.
If any check fails -> NO TRADE.
Position sizing is based on Stop Distance x Risk Budget (not fixed lots).
"""

from __future__ import annotations
import math
from datetime import datetime, timezone

from molido_shared.volatility import scale_atr_threshold


def _today():
    return datetime.now(timezone.utc).date()
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
        # Daily limits must clear when the day does. Anything account-level --
        # max drawdown, a prop floor breach -- stays latched until a human
        # looks at it.
        self._circuit_scope: str = "account"
        self._circuit_day = None

    def evaluate(self, ctx: RiskContext) -> RiskResult:
        """
        Main entry. Returns ALLOW / REDUCE / DENY with lot size when allowed.
        """
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        if self._circuit_open:
            # A daily-loss stop is meant to end the day, not the bot. Nothing
            # in the codebase ever called reset_circuit(), so the first trip
            # was permanent: the engine kept running, kept logging, and denied
            # every trade until someone recreated the container. For an
            # unattended bot that is indistinguishable from being broken.
            if self._circuit_scope == "daily" and self._circuit_day != _today():
                self.reset_circuit()
            else:
                return self._deny(f"Circuit breaker open: {self._circuit_reason}", checks)

        if ctx.is_exit or ctx.side == "EXIT":
            return RiskResult(
                decision=RiskDecision.ALLOW,
                lot_size=0.0,
                reasons=["EXIT order - risk reduction"],
                checks={"exit": True},
            )

        limits = ctx.limits or self.limits
        account = ctx.account

        checks["stop_loss"] = not (limits.require_stop_loss and ctx.stop_loss is None)
        if not checks["stop_loss"]:
            return self._deny("Stop-Loss is mandatory", checks)

        if ctx.entry is None or ctx.stop_loss is None or ctx.entry <= 0:
            return self._deny("Invalid entry or stop-loss", checks)
        stop_distance = abs(ctx.entry - ctx.stop_loss)
        if stop_distance <= 0:
            return self._deny("Stop distance is zero", checks)
        checks["stop_distance"] = True

        # No average-down: deny add-on same symbol / same side
        if getattr(limits, "deny_average_down", True):
            open_syms = [s.upper() for s in (account.open_symbols or [])]
            side_map = {k.upper(): v.upper() for k, v in (account.open_side_by_symbol or {}).items()}
            sym = (ctx.symbol or "").upper()
            if sym in open_syms or account.symbol_exposure.get(ctx.symbol, 0.0) > 0:
                open_side = side_map.get(sym)
                if open_side is None or open_side == (ctx.side or "").upper():
                    return self._deny("no average down: already open on symbol", checks)
            checks["no_average_down"] = True

        # Margin gate
        ml = account.margin_level
        min_ml = getattr(limits, "min_margin_level", 300.0)
        if ml is not None and ml > 0 and ml < min_ml:
            return self._deny(f"margin_level {ml:.1f} < {min_ml}", checks)
        fm = account.free_margin
        min_ratio = getattr(limits, "min_free_margin_ratio", 0.3)
        if fm is not None and account.equity > 0 and (fm / account.equity) < min_ratio:
            return self._deny(
                f"free_margin/equity {fm / account.equity:.2f} < {min_ratio}",
                checks,
            )
        checks["margin"] = True

        # ATR gate
        if ctx.atr is not None and ctx.entry:
            dead = scale_atr_threshold(
                getattr(limits, "dead_atr_ratio", 0.0003), ctx.timeframe
            )
            if ctx.entry > 0 and ctx.atr / ctx.entry < dead:
                return self._deny(
                    f"ATR/close {ctx.atr / ctx.entry:.6f} < {dead:.6f} (dead market, tf={ctx.timeframe or 'n/a'})",
                    checks,
                )
            cap = getattr(limits, "atr_vs_stop_max", 1.2)
            if ctx.atr > cap * stop_distance:
                return self._deny(
                    f"ATR {ctx.atr:.5f} > {cap} x stop {stop_distance:.5f}",
                    checks,
                )
        checks["atr"] = True

        rr = ctx.risk_reward
        if rr is None and ctx.take_profit is not None:
            reward = abs(ctx.take_profit - ctx.entry)
            rr = reward / stop_distance if stop_distance else 0
        checks["min_rr"] = rr is None or rr >= limits.min_risk_reward
        if not checks["min_rr"]:
            return self._deny(f"R:R {rr:.2f} < minimum {limits.min_risk_reward}", checks)

        if ctx.spread_points is not None:
            checks["spread"] = ctx.spread_points <= limits.max_spread_points
            if not checks["spread"]:
                return self._deny(
                    f"Spread {ctx.spread_points:.1f} > max {limits.max_spread_points}",
                    checks,
                )
        else:
            checks["spread"] = True

        if account.equity > 0:
            daily_loss_pct = -account.daily_pnl / account.equity if account.daily_pnl < 0 else 0.0
            checks["daily_loss"] = daily_loss_pct < limits.max_daily_loss
            if not checks["daily_loss"]:
                self.trip_circuit(f"Daily loss limit hit ({daily_loss_pct:.2%})", scope="daily")
                return self._deny(
                    f"Daily loss {daily_loss_pct:.2%} >= limit {limits.max_daily_loss:.2%}",
                    checks,
                )
        else:
            checks["daily_loss"] = False
            return self._deny("Equity is zero or negative", checks)

        # Daily entry cap. max_entries_per_day has always been in RiskLimits and
        # the autopilot now computes it from the daily budget -- but nothing
        # enforced it and nothing populated account.entries_today, so it was
        # another number that got logged and ignored. It is the direct control
        # on overtrading: budget / risk-per-trade is exactly how many losing
        # trades the day can absorb, and taking more than that is spending
        # money the plan does not have.
        if limits.max_entries_per_day > 0:
            checks["entries_today"] = account.entries_today < limits.max_entries_per_day
            if not checks["entries_today"]:
                return self._deny(
                    f"{account.entries_today} entries today >= daily cap {limits.max_entries_per_day}",
                    checks,
                )

        # Consecutive-loss brake. max_consecutive_losses and
        # consecutive_loss_pause_seconds have been in RiskLimits from the
        # start and no code ever read them, so a losing streak did nothing at
        # all -- the bot kept taking full-size trades straight through it.
        # This is the "get more careful after losses" behaviour the limits
        # always promised.
        if limits.max_consecutive_losses > 0 and account.consecutive_losses >= limits.max_consecutive_losses:
            paused = True
            if account.last_loss_at is not None and limits.consecutive_loss_pause_seconds > 0:
                last = account.last_loss_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                paused = elapsed < limits.consecutive_loss_pause_seconds
                remaining = limits.consecutive_loss_pause_seconds - elapsed
            else:
                remaining = limits.consecutive_loss_pause_seconds
            checks["loss_streak"] = not paused
            if paused:
                return self._deny(
                    f"{account.consecutive_losses} consecutive losses; pausing new entries "
                    f"for another {max(0, remaining) / 60:.0f} min",
                    checks,
                )
        else:
            checks["loss_streak"] = True

        # Prop hard floor, checked before the trailing drawdown rule because
        # it is the one that ends the challenge. Measured from the starting
        # balance the firm set, so it does not move with peak_equity.
        floor = limits.prop_initial_balance * (1.0 - limits.prop_max_loss_pct)
        if limits.prop_initial_balance > 0:
            checks["prop_floor"] = account.equity > floor
            if not checks["prop_floor"]:
                self.trip_circuit(f"Prop max-loss floor hit (equity {account.equity:.2f} <= {floor:.2f})")
                return self._deny(
                    f"Equity {account.equity:.2f} at or below prop floor {floor:.2f}",
                    checks,
                )

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

        checks["max_positions"] = account.open_positions < limits.max_open_positions
        if not checks["max_positions"]:
            return self._deny(
                f"Open positions {account.open_positions} >= max {limits.max_open_positions}",
                checks,
            )

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

        risk_mult = 1.0
        ml_high_vol = (
            ctx.ml_high_vol_prob is not None and ctx.ml_high_vol_prob >= limits.ml_high_vol_threshold
        )
        if ctx.regime in ("High Volatility", "Extreme Volatility"):
            if ctx.regime == "Extreme Volatility" and limits.extreme_vol_block:
                return self._deny("Extreme volatility - new entries blocked", checks)
            risk_mult = limits.high_vol_risk_mult
            reasons.append(f"Risk reduced x{risk_mult} due to {ctx.regime}")
        elif ml_high_vol:
            # Same reduction the rule-based regime gets -- validated
            # (scripts/train_regime_model.py, walk-forward) to have real
            # skill at *this* specific call, unlike direction, which this
            # signal is never used for. Only fires when the rule-based
            # regime hasn't already caught it, so it never stacks.
            risk_mult = limits.high_vol_risk_mult
            reasons.append(f"Risk reduced x{risk_mult} due to ML high-vol signal (p={ctx.ml_high_vol_prob:.2f})")

        risk_pct = limits.risk_per_trade * risk_mult
        risk_amount = account.equity * risk_pct

        pip_size = self._estimate_pip_size(ctx.symbol, ctx.entry)
        stop_pips = stop_distance / pip_size if pip_size > 0 else 0
        if stop_pips <= 0:
            return self._deny("Invalid stop pips", checks)

        risk_per_lot = self._risk_per_lot(ctx.symbol, ctx.entry, stop_pips)
        if risk_per_lot <= 0:
            return self._deny("Risk per lot is zero", checks)

        raw_lots = risk_amount / risk_per_lot
        lot_size = self._normalize_lot(raw_lots, limits)

        if lot_size < limits.min_lot_size:
            return self._deny(
                f"Calculated lot {lot_size:.4f} below minimum {limits.min_lot_size}",
                checks,
            )

        symbol_risk = risk_amount
        current_symbol = account.symbol_exposure.get(ctx.symbol, 0.0)
        max_symbol = account.equity * limits.max_symbol_exposure
        checks["symbol_exposure"] = (current_symbol + symbol_risk) <= max_symbol
        if not checks["symbol_exposure"]:
            remaining = max(0.0, max_symbol - current_symbol)
            if remaining >= account.equity * limits.risk_per_trade * 0.25:
                lot_size = self._normalize_lot((remaining / risk_per_lot), limits)
                risk_amount = remaining
                reasons.append("Lot reduced to fit symbol exposure limit")
                decision = RiskDecision.REDUCE
            else:
                return self._deny("Symbol exposure limit reached", checks)
        else:
            decision = RiskDecision.ALLOW

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

        if lot_size > limits.max_lot_size:
            lot_size = limits.max_lot_size
            reasons.append(f"Lot capped at max_lot_size={limits.max_lot_size}")
            decision = RiskDecision.REDUCE

        checks["position_sizing"] = lot_size >= limits.min_lot_size

        if not reasons:
            reasons.append(
                f"Risk {risk_pct:.2%} of equity (${risk_amount:.2f}) -> {lot_size:.2f} lots"
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
                "pip_size": pip_size,
                "risk_per_lot": round(risk_per_lot, 4),
            },
        )

    def trip_circuit(self, reason: str, scope: str = "account") -> None:
        """Open the breaker. scope="daily" clears itself on the next day."""
        self._circuit_open = True
        self._circuit_reason = reason
        self._circuit_scope = scope
        self._circuit_day = _today()

    def reset_circuit(self) -> None:
        self._circuit_open = False
        self._circuit_reason = None
        self._circuit_scope = "account"
        self._circuit_day = None

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    def _deny(self, reason: str, checks: dict[str, bool]) -> RiskResult:
        return RiskResult(
            decision=RiskDecision.DENY,
            lot_size=0.0,
            risk_amount=0.0,
            reasons=[reason],
            checks=checks,
        )

    @staticmethod
    def _estimate_pip_size(symbol: str | None, price: float | None = None) -> float:
        """JPY pairs 0.01, gold 0.01, standard FX 0.0001."""
        s = (symbol or "").replace("/", "").replace(".", "").upper()
        if "JPY" in s:
            return 0.01
        if s.startswith("XAU") or s.startswith("XAG") or s.startswith("GOLD"):
            return 0.01
        if price is not None and price > 20:
            return 0.01
        return 0.0001

    @staticmethod
    def _risk_per_lot(symbol: str | None, price: float, stop_pips: float) -> float:
        """$ risk per lot for this stop. Not always $10/pip."""
        s = (symbol or "").replace("/", "").replace(".", "").upper()
        pip = RiskEngine._estimate_pip_size(symbol, price)
        if s.startswith("XAU") or "GOLD" in s:
            pip_value = 100.0 * pip  # 100 oz
        elif s.startswith("XAG"):
            pip_value = 5000.0 * pip
        elif len(s) >= 6 and s[3:6] == "USD":
            pip_value = 100_000.0 * pip
        elif len(s) >= 6 and s[:3] == "USD" and price:
            pip_value = (100_000.0 * pip) / price
        else:
            pip_value = 10.0
        return stop_pips * pip_value

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
