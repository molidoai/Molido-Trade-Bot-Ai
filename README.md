# Molido Trade Bot AI

Professional Automated Forex Trading Platform.

> **Important Disclaimer**  
> This software does **not** guarantee profits.  
> Trading foreign exchange involves substantial risk of loss.  
> This is **not** financial advice or an investment recommendation.

---

## Current Status

| Phase | Description | Status |
|-------|-------------|--------|
| **PHASE 1** | Foundation + Config + Docker + Database + Auth | ✅ Complete |
| **PHASE 2** | Broker Adapter (MT5 + Mock) + Market Data Engine | ✅ Complete |
| **PHASE 3** | Indicator Engine | ✅ Complete |
| **PHASE 4** | Strategy Engine | ✅ Complete |
| **PHASE 5** | Signal Engine | ✅ Complete |
| **PHASE 6** | Risk Engine (critical) | ✅ Complete |
| **PHASE 7** | Execution Engine | ✅ Complete |
| **PHASE 8** | Position / Portfolio / Reconciliation | ✅ Complete |
| PHASE 9 | Backtester | ⏳ Next |

---

## PHASE 3 – Indicator Engine

### Implemented Indicators

| Category | Indicators |
|----------|------------|
| **Trend** | EMA (any period), MultiEMA (9/21/50/200), SMA, Supertrend |
| **Momentum** | RSI, MACD, Stochastic |
| **Volatility** | ATR, Bollinger Bands, Donchian Channel |
| **Structure** | Swing Highs / Swing Lows |

### Key Properties (per Master Prompt §5)
- Configurable parameters
- Enable / Disable per indicator
- **No look-ahead bias** (verified by unit tests)
- Deterministic (same input → same output)
- Registry pattern – easy to add new indicators later
- Batch compute + latest-value helpers

### Usage Example

```python
from molido_indicators import IndicatorEngine
from molido_shared.types import TimeFrame

engine = IndicatorEngine()
engine.add_from_registry("MultiEMA", periods=[9, 21, 50, 200])
engine.add_from_registry("RSI", period=14)
engine.add_from_registry("ATR", period=14)
engine.add_from_registry("BollingerBands", period=20, std_dev=2.0)
engine.add_from_registry("Supertrend", period=10, multiplier=3.0)

# candles = await market_data.get_candles("EURUSD", TimeFrame.M15, count=200)
latest = engine.compute_latest(candles)
print(latest["RSI"].get("rsi"))
print(latest["MultiEMA"].get("ema_21"))
```

### Run Tests

```bash
pip install -e packages/shared -e packages/broker -e packages/indicators
pytest tests/unit/indicators/ -v
```

---

## Next Phase

**PHASE 4 – Strategy Engine**

Plugin-style strategies:
- Trend Following
- Breakout
- Momentum
- Mean Reversion
- Scalping / Swing (base templates)

Each strategy produces Signals only – never sends orders directly.

---

Built according to the Master Prompt specification.

---

## Account Modes

| Mode | Description | Default Risk Behaviour |
|------|-------------|------------------------|
| **DEMO** | Practice / broker demo account | Standard risk limits |
| **PROP** | Prop Firm (FTMO, FundedNext, …) | Uses firm’s max daily loss & max drawdown |
| **REAL** | Personal live capital | Strictest confirmation (2-step) required |

- Default mode is always **DEMO**.
- Switching to **PROP** or **REAL** requires explicit action and is audited.
- In **PROP** mode the Risk Engine will enforce:
  - `PROP_MAX_DAILY_LOSS_PCT`
  - `PROP_MAX_TOTAL_DRAWDOWN_PCT`
  - Profit target tracking (when set)
  - Phase awareness (Challenge / Verification / Funded)


## PHASE 5 – Signal Engine

- Multi-factor scoring (Trend, Momentum, Volume, Structure, MTF, Volatility, Strategy)
- Configurable weights (default sum 100)
- Acceptance threshold (default 60)
- Mandatory Stop-Loss check
- Minimum R:R filter
- `FinalSignal` with full breakdown for Explainable Trade Card
- Score is **never** a substitute for Risk Engine


## PHASE 6 – Risk Engine (Critical)

**No path may bypass this engine.**

Checks (any failure → NO TRADE):
- Mandatory Stop-Loss
- Min Risk/Reward
- Spread limit
- Daily loss limit → trips Circuit Breaker
- Max drawdown → trips Circuit Breaker
- Weekly loss
- Max open positions
- Cooldown
- Volatility regime scaling / block
- Symbol exposure & Portfolio exposure
- Position sizing from **Risk Budget × Stop Distance** (not fixed lots)
- PROP mode uses firm daily-loss & drawdown limits

Outputs: `ALLOW` | `REDUCE` (smaller lot) | `DENY`


## PHASE 7 – Execution Engine

- Runs **only after** Risk Engine ALLOW / REDUCE
- Idempotency via `client_order_id` (at-most-once)
- Spread check at send time
- Safe retry (no retry after timeout → UNKNOWN + reconcile)
- Partial fills, reject, cancel
- EXIT / close path with `position_ticket`
- Slippage measurement on fill


## PHASE 8 – Position / Portfolio / Reconciliation

- **PositionManager**: broker is source of truth; `sync_from_broker()`
- **PortfolioManager**: equity, exposure, drawdown, currency exposure
- **Reconciler**: on unknown state → pause entries → sync → resume
- `can_accept_new_entries()` gate for Trading Engine
- Converts snapshot → RiskEngine `AccountState`
