"""Multi-account configuration.

runtime-settings.json may define an `accounts` list; each entry is one
broker account the engine trades independently -- its own MT5 connection,
its own risk engine (so one account's circuit breaker or daily-loss stop
never touches another), its own journal, and its own dashboard status.

Backwards compatible on purpose: when no `accounts` list is present, the
flat mt5_* / risk fields that the single-account deployment already uses
are wrapped into exactly one account called "default". An existing install
therefore behaves identically until an `accounts` list is added.

Each account needs its own MT5 terminal instance listening on its own RPC
port -- MetaTrader5 allows one logged-in account per terminal. Point each
entry's rpc_port at that account's bridge.
"""

from __future__ import annotations
import os
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ACCOUNT_ID = "default"


def _slug(value: str, fallback: str) -> str:
    """Filesystem-safe id -- it becomes part of per-account file names."""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-").lower()
    return s or fallback


def _as_bool(val: Any, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _as_int(val: Any) -> int | None:
    try:
        text = str(val).strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _pick(src: dict, *keys: str, env: str | None = None) -> str:
    for key in keys:
        val = src.get(key)
        if val is None:
            continue
        text = str(val).strip()
        # "••••" is the masked placeholder the settings API returns for secrets
        if text and text != "••••":
            return text
    if env:
        return (os.getenv(env) or "").strip()
    return ""


@dataclass
class AccountConfig:
    id: str
    name: str
    enabled: bool = True
    account_mode: str = "DEMO"
    login: int | None = None
    password: str = ""
    server: str = ""
    path: str | None = None
    rpc_host: str = "host.docker.internal"
    rpc_port: int = 8001
    symbols: str = "auto"
    # "auto" lets the engine sweep its own timeframes; an explicit value
    # (M5/M15/H1/H4/D1) pins entries to that one.
    timeframe: str = "auto"
    strategy_names: Any = None
    # Risk/behaviour knobs, already flattened -- LiveRunner reads these the
    # same way it read the top-level runtime settings before.
    settings: dict = field(default_factory=dict)

    @property
    def has_credentials(self) -> bool:
        return bool(self.login and self.password and self.server)

    # posixpath, not os.path: these are always container paths, and joining
    # them on a Windows dev box would emit backslashes the engine can't use.
    def journal_path(self, data_dir: str) -> str:
        return posixpath.join(data_dir, f"journal-{self.id}.jsonl")

    def decisions_path(self, data_dir: str) -> str:
        return posixpath.join(data_dir, f"brain-decisions-{self.id}.json")

    def status_path(self, data_dir: str) -> str:
        return posixpath.join(data_dir, f"portfolio-status-{self.id}.json")


# Keys copied from the top-level runtime settings into every account as
# defaults; an account entry may override any of them.
#
# This is a whitelist, and anything the engine reads per cycle but that is
# missing here is silently dropped the moment a second account exists -- the
# single-account path passes the whole settings dict, so the key works right up
# until an `accounts` list appears and then stops, with nothing logged.
#
# That is not hypothetical: symbol_strategies, indicators, strategies and
# autopilot were all absent. Adding a prop account would have quietly
# un-restricted every symbol on BOTH accounts, putting the strategies that
# lost money back on the symbols they lost it on, at the exact moment a
# challenge started.
#
# If you add a setting the runner reads, add it here in the same change. The
# test in tests/unit/accounts/test_inherited_keys.py fails when the two drift.
_INHERITED_KEYS = (
    "default_risk_per_trade",
    "max_daily_loss",
    "max_weekly_loss",
    "max_drawdown",
    "max_open_positions",
    "max_entries_per_day",
    "max_consecutive_losses",
    "consecutive_loss_pause_seconds",
    "session_overlap_only",
    "master_bot_enabled",
    "strategy_names",
    "strategies",
    "symbol_strategies",
    "indicators",
    "autopilot",
    "require_proven_edge",
    "symbols",
    "timeframe",
)


def _account_from_entry(entry: dict, rt: dict, index: int) -> AccountConfig:
    settings = {k: rt[k] for k in _INHERITED_KEYS if k in rt}
    settings.update({k: v for k, v in entry.items() if k not in ("id", "name", "enabled")})

    acc_id = _slug(entry.get("id") or entry.get("name"), f"account-{index + 1}")
    return AccountConfig(
        id=acc_id,
        name=str(entry.get("name") or acc_id),
        enabled=_as_bool(entry.get("enabled"), True),
        account_mode=str(entry.get("trading_account_mode") or rt.get("trading_account_mode") or "DEMO").upper(),
        login=_as_int(_pick(entry, "mt5_login", "mt5_real_login", "login")),
        password=_pick(entry, "mt5_password", "mt5_real_password", "password"),
        server=_pick(entry, "mt5_server", "mt5_real_server", "server"),
        path=_pick(entry, "mt5_path", "mt5_real_path", "path") or None,
        rpc_host=_pick(entry, "rpc_host", "mt5_rpc_host") or os.getenv("MT5_RPC_HOST", "host.docker.internal"),
        rpc_port=_as_int(_pick(entry, "rpc_port", "mt5_rpc_port")) or int(os.getenv("MT5_RPC_PORT", "8001")),
        symbols=str(entry.get("symbols") or rt.get("symbols") or "auto"),
        timeframe=str(entry.get("timeframe") or rt.get("timeframe") or "auto"),
        strategy_names=entry.get("strategy_names", rt.get("strategy_names")),
        settings=settings,
    )


def _legacy_single_account(rt: dict) -> AccountConfig:
    """Wrap the flat single-account settings so the rest of the engine only
    ever deals with AccountConfig objects."""
    return AccountConfig(
        id=DEFAULT_ACCOUNT_ID,
        name=str(rt.get("account_name") or "Default"),
        enabled=True,
        account_mode=str(rt.get("trading_account_mode") or os.getenv("TRADING_ACCOUNT_MODE") or "DEMO").upper(),
        login=_as_int(_pick(rt, "mt5_login", "mt5_real_login", env="MT5_REAL_LOGIN")),
        password=_pick(rt, "mt5_password", "mt5_real_password", env="MT5_REAL_PASSWORD"),
        server=_pick(rt, "mt5_server", "mt5_real_server", env="MT5_REAL_SERVER"),
        path=_pick(rt, "mt5_path", "mt5_real_path", env="MT5_REAL_PATH") or None,
        rpc_host=os.getenv("MT5_RPC_HOST", "host.docker.internal"),
        rpc_port=int(os.getenv("MT5_RPC_PORT", "8001")),
        symbols=str(rt.get("symbols") or "auto"),
        timeframe=str(rt.get("timeframe") or "auto"),
        strategy_names=rt.get("strategy_names"),
        settings=dict(rt),
    )


def load_accounts(rt: dict) -> list[AccountConfig]:
    """All configured accounts, enabled or not. Callers filter on .enabled
    so the dashboard can still show a disabled account's last known state."""
    entries = rt.get("accounts")
    if not isinstance(entries, list) or not entries:
        return [_legacy_single_account(rt)]

    accounts: list[AccountConfig] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        acc = _account_from_entry(entry, rt, i)
        # Ids become file names and dashboard keys; a duplicate would make two
        # accounts silently share a journal, so disambiguate rather than merge.
        if acc.id in seen:
            acc.id = f"{acc.id}-{i + 1}"
        seen.add(acc.id)
        accounts.append(acc)
    return accounts or [_legacy_single_account(rt)]


def enabled_accounts(rt: dict) -> list[AccountConfig]:
    return [a for a in load_accounts(rt) if a.enabled]
