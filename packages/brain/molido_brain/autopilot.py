"""Derive the trading limits from evidence instead of asking for them.

Every number here used to be hand-entered: risk per trade, entries per day,
open positions, how many losses before pausing. Most of them are not opinions
-- they follow arithmetically from one another, and getting them inconsistent
is what produced a configuration where risk per trade equalled the daily cap
and a single losing trade ended the day.

So: one human input, everything else computed.

The one input is `max_daily_loss` -- the most you are willing to lose in a day.
That is deliberately NOT automated. Risk appetite is not a fact the bot can
measure; it is a decision about your money. A bot that picks its own maximum
loss does not have a maximum loss. Everything below is derived from it.

Risk per trade starts at the floor and only rises on measured expectancy, via
Experience, which shrinks toward neutral on thin data and abstains below its
sample threshold. Growth is deliberately slow and capped: an unproven edge is
treated as no edge, and even a strong record cannot push risk past
MAX_RISK_PER_TRADE. The asymmetry is intentional -- being wrong about having an
edge costs real money, being slow to size up costs only opportunity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Starting risk, and the floor the bot never goes below while it has no
# evidence. Small enough that a run of losses is survivable while the record
# is being built.
BASE_RISK_PER_TRADE = 0.005

# Hard ceiling, regardless of how good the history looks. Records this short
# are dominated by luck, and the cost of overestimating an edge is asymmetric.
MAX_RISK_PER_TRADE = 0.02

# Expectancy (in R, after shrinkage) at which risk reaches the ceiling.
# Above a genuine +0.5R average the bot is allowed full size.
EXPECTANCY_FOR_MAX = 0.5

# Losing streaks must bite before the day is spent, so the streak brake is the
# thing that fires and it clears itself after a pause. Keep the worst-case
# streak under this fraction of the daily budget.
STREAK_BUDGET = 0.75

# Never leave the day's budget on a single trade, whatever the arithmetic says.
MIN_ENTRIES_PER_DAY = 3


@dataclass(frozen=True)
class Plan:
    risk_per_trade: float
    max_entries_per_day: int
    max_consecutive_losses: int
    max_open_positions: int
    reasons: list[str]

    def as_settings(self) -> dict[str, Any]:
        return {
            "default_risk_per_trade": self.risk_per_trade,
            "max_entries_per_day": self.max_entries_per_day,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_open_positions": self.max_open_positions,
        }


def risk_from_evidence(experience: Any | None) -> tuple[float, str]:
    """Risk per trade, scaled by measured expectancy.

    No evidence means the floor -- never an assumption of skill.
    """
    if experience is None:
        return BASE_RISK_PER_TRADE, "no journal yet -- starting at the floor"

    overall = None
    try:
        overall = experience.overall()
    except Exception:
        overall = None

    if overall is None:
        return BASE_RISK_PER_TRADE, "not enough closed trades to judge -- holding the floor"

    if overall.shrunk_r <= 0:
        return (
            BASE_RISK_PER_TRADE,
            f"{overall.n} trades, adjusted {overall.shrunk_r:+.2f}R -- no proven edge, holding the floor",
        )

    # Linear from floor to ceiling as adjusted expectancy runs 0 -> +0.5R.
    # Shrinkage already penalises small samples, so this needs no separate
    # sample-size term.
    frac = min(1.0, overall.shrunk_r / EXPECTANCY_FOR_MAX)
    risk = BASE_RISK_PER_TRADE + (MAX_RISK_PER_TRADE - BASE_RISK_PER_TRADE) * frac
    risk = round(min(MAX_RISK_PER_TRADE, max(BASE_RISK_PER_TRADE, risk)), 5)
    return risk, (
        f"{overall.n} trades, adjusted {overall.shrunk_r:+.2f}R "
        f"(win {overall.win_rate:.0%}) -- risk {risk * 100:.2f}%"
    )


def plan(
    *,
    max_daily_loss: float,
    experience: Any | None = None,
    correlation_groups: int = 5,
) -> Plan:
    """Work the whole configuration out from the daily loss budget.

    correlation_groups caps concurrent positions: holding two pairs from one
    cluster is one bet wearing two tickets, so open slots are bounded by how
    many genuinely independent groups the universe covers.
    """
    reasons: list[str] = []

    risk, why = risk_from_evidence(experience)
    reasons.append(why)

    if max_daily_loss <= 0:
        max_daily_loss = 0.02
        reasons.append("daily loss budget missing -- defaulted to 2%")

    # A trade can never be allowed to consume the whole day on its own.
    ceiling = max_daily_loss / MIN_ENTRIES_PER_DAY
    if risk > ceiling:
        risk = round(ceiling, 5)
        reasons.append(
            f"risk trimmed to {risk * 100:.2f}% so at least {MIN_ENTRIES_PER_DAY} trades fit in the daily budget"
        )

    entries = max(MIN_ENTRIES_PER_DAY, int(math.floor(max_daily_loss / risk)))
    reasons.append(f"{entries} entries/day = {max_daily_loss * 100:.1f}% budget / {risk * 100:.2f}% per trade")

    streak = max(2, int(math.floor((max_daily_loss * STREAK_BUDGET) / risk)))
    streak = min(streak, entries)
    reasons.append(
        f"pause after {streak} losses ({streak * risk * 100:.1f}% of equity), "
        f"before the {max_daily_loss * 100:.1f}% daily stop"
    )

    open_positions = max(1, min(correlation_groups, entries))
    reasons.append(f"{open_positions} open at once = {correlation_groups} independent groups in the universe")

    return Plan(
        risk_per_trade=risk,
        max_entries_per_day=entries,
        max_consecutive_losses=streak,
        max_open_positions=open_positions,
        reasons=reasons,
    )


# Mirrors molido_guards.correlation.CLUSTERS. Duplicated rather than imported
# so molido_brain does not depend on molido_guards; if a cluster is added
# there, add it here too -- an unknown symbol simply counts as its own group,
# which is the safe direction (it never inflates the open-position cap for
# pairs that are actually correlated).
_CLUSTERS: tuple[frozenset[str], ...] = (
    frozenset({"EURUSD", "GBPUSD", "EURGBP", "EURJPY", "GBPJPY"}),
    frozenset({"USDJPY", "EURJPY", "GBPJPY", "AUDJPY"}),
    frozenset({"AUDUSD", "NZDUSD", "AUDNZD"}),
    frozenset({"XAUUSD", "XAGUSD"}),
)


def independent_groups(symbols) -> int:
    """How many genuinely uncorrelated bets this universe can hold at once.

    Two pairs from one cluster are one bet wearing two tickets, so this is the
    real ceiling on concurrent positions -- not the length of the symbol list.
    """
    seen_clusters: set[int] = set()
    loose = 0
    for raw in symbols or ():
        sym = str(raw).replace("/", "").strip().upper()
        if not sym:
            continue
        idx = next((i for i, c in enumerate(_CLUSTERS) if sym in c), None)
        if idx is None:
            loose += 1          # in no cluster: independent by itself
        else:
            seen_clusters.add(idx)
    return max(1, len(seen_clusters) + loose)
