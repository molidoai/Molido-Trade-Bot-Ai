"""The whitelist in accounts.py must not drift from what the runner reads.

_INHERITED_KEYS decides which top-level settings reach a configured account.
The single-account path passes the whole settings dict, so a missing key works
perfectly until an `accounts` list appears -- and then stops working, silently,
with nothing logged. symbol_strategies, indicators, strategies and autopilot
were all missing when this test was written; adding a prop account would have
un-restricted every symbol on both accounts at the moment a challenge began.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "apps" / "trading-engine" / "app" / "live" / "runner.py"
ACCOUNTS = ROOT / "apps" / "trading-engine" / "app" / "live" / "accounts.py"

# Read per cycle but deliberately not inheritable: these identify or address a
# specific account rather than configure how it trades.
NOT_INHERITED = {
    "mt5_login", "mt5_password", "mt5_server", "mt5_path",
    "mt5_real_login", "mt5_real_password", "mt5_real_server", "mt5_real_path",
    "rpc_host", "rpc_port", "trading_account_mode", "account_name",
    "accounts", "id", "name", "enabled", "login", "password", "server", "path",
}


def _inherited() -> set[str]:
    block = re.search(r"_INHERITED_KEYS = \((.*?)\n\)", ACCOUNTS.read_text(encoding="utf-8"), re.S)
    assert block, "_INHERITED_KEYS tuple not found"
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


def _read_by_runner() -> set[str]:
    src = RUNNER.read_text(encoding="utf-8")
    keys = set(re.findall(r'(?:settings|acc_settings|rt)\.get\(\s*"([a-z_]+)"', src))
    return keys - NOT_INHERITED


def test_every_setting_the_runner_reads_is_inherited():
    missing = sorted(_read_by_runner() - _inherited())
    assert not missing, (
        "these settings are read per cycle but would be dropped for any "
        "configured account: %s. Add them to _INHERITED_KEYS in accounts.py." % missing
    )


def test_the_settings_that_caused_this_are_present():
    inherited = _inherited()
    for key in ("symbol_strategies", "indicators", "strategies", "autopilot"):
        assert key in inherited, "%s must be inherited" % key
