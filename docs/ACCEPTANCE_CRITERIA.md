# Acceptance Criteria (Master Prompt §50)

Status legend: ✅ code ready · ⏳ needs runtime/VPS · ❌ not done · 🔒 needs human decision

| Criterion | Status |
|-----------|--------|
| Market data pipeline | ✅ (Mock + MT5 skeleton) |
| Indicators validated (unit tests) | ✅ |
| Strategies tested | ✅ |
| Backtester | ✅ |
| Risk Engine independent & enforceable | ✅ |
| Execution idempotent | ✅ |
| Position reconciliation | ✅ |
| API keys not in git | ✅ (pattern) |
| Paper trading path | ✅ Mock |
| Demo account success | ⏳ needs broker DEMO |
| DEMO/REAL switch + 2-step + audit | ⏳ partial (models + config) |
| Master ON/OFF persistent | ⏳ needs Redis/DB wiring in live loop |
| Trading Hours Guard | ❌ not implemented yet |
| News Blackout Window | ❌ needs calendar provider |
| Multi-account account_id in models | ✅ |
| Observer role model | ✅ (UserRole) |
| Trade Pre-Flight in Risk path | ✅ (Risk checks) |
| Adaptive Threshold versioned | ⏳ structure only |
| Smart Degradation | ⏳ partial (anomaly + circuit) |
| Capital Allocation multi-strategy | ❌ |
| Slippage/Cost model in backtest | ✅ |
| Data quality monitor | ✅ AnomalyDetector |
| Config Drift Detector | ❌ |
| Disaster Recovery Drill | 🔒 operator |
| Kill switch / Circuit breaker | ✅ code |
| DB backup/restore | ⏳ ops |
| Monitoring metrics | ✅ |
| Audit logs model | ✅ |
| Security review | ✅ basic checks |
| E2E on real Demo | ⏳ |

**Honest conclusion:** Codebase is ready for **Paper (Mock)** and development on a VPS.  
**Not ready for Micro-Live** until DEMO broker connection, persistent Master switch, Trading Hours Guard, and operator DR drill are done.
