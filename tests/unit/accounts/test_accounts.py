"""Multi-account config: isolation guarantees and backwards compatibility."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "trading-engine"))

from app.live.accounts import load_accounts, enabled_accounts, DEFAULT_ACCOUNT_ID

LEGACY = {
    "trading_account_mode": "DEMO",
    "mt5_login": "10012435772",
    "mt5_password": "secret",
    "mt5_server": "MetaQuotes-Demo",
    "max_daily_loss": 0.02,
    "max_open_positions": 3,
}


def test_legacy_settings_yield_one_default_account():
    """An install with no `accounts` list must behave exactly as before."""
    accounts = load_accounts(LEGACY)
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc.id == DEFAULT_ACCOUNT_ID
    assert acc.enabled is True
    assert acc.login == 10012435772
    assert acc.server == "MetaQuotes-Demo"
    assert acc.has_credentials is True


def test_masked_secret_is_not_treated_as_a_password():
    """The settings API returns '••••' for stored secrets; that placeholder
    must never be sent to the broker as a real password."""
    acc = load_accounts({**LEGACY, "mt5_password": "••••"})[0]
    assert acc.password == ""
    assert acc.has_credentials is False


def test_accounts_get_separate_state_files():
    """Two accounts sharing a journal would corrupt each other's history and
    each other's brain-3 expectancy veto."""
    cfg = {"accounts": [{"name": "A"}, {"name": "B"}]}
    a, b = load_accounts(cfg)
    for attr in ("journal_path", "decisions_path", "status_path"):
        assert getattr(a, attr)("/app/data") != getattr(b, attr)("/app/data")


def test_duplicate_names_do_not_collide():
    ids = [a.id for a in load_accounts({"accounts": [{"name": "Same"}, {"name": "Same"}]})]
    assert len(set(ids)) == 2


def test_per_account_risk_overrides_top_level():
    cfg = {
        "max_daily_loss": 0.02,
        "max_open_positions": 3,
        "accounts": [
            {"name": "Inherits"},
            {"name": "Stricter", "max_daily_loss": 0.05, "max_open_positions": 1},
        ],
    }
    inherits, stricter = load_accounts(cfg)
    assert inherits.settings["max_daily_loss"] == 0.02
    assert inherits.settings["max_open_positions"] == 3
    assert stricter.settings["max_daily_loss"] == 0.05
    assert stricter.settings["max_open_positions"] == 1


def test_disabled_accounts_are_listed_but_not_run():
    cfg = {"accounts": [{"name": "On"}, {"name": "Off", "enabled": False}]}
    assert len(load_accounts(cfg)) == 2
    assert [a.id for a in enabled_accounts(cfg)] == ["on"]


def test_each_account_keeps_its_own_bridge_port():
    """One MT5 terminal serves one account; sharing a port would route an
    account's orders to another account's terminal."""
    cfg = {"accounts": [
        {"name": "A", "rpc_port": 8001},
        {"name": "B", "rpc_port": 8002},
    ]}
    a, b = load_accounts(cfg)
    assert (a.rpc_port, b.rpc_port) == (8001, 8002)


def test_account_mode_is_per_account():
    cfg = {"trading_account_mode": "DEMO", "accounts": [
        {"name": "Demo"},
        {"name": "Prop", "trading_account_mode": "PROP"},
    ]}
    demo, prop = load_accounts(cfg)
    assert demo.account_mode == "DEMO"
    assert prop.account_mode == "PROP"


def test_empty_or_malformed_accounts_falls_back_to_legacy():
    for bad in ([], "not-a-list", None, [123, "x"]):
        accounts = load_accounts({**LEGACY, "accounts": bad})
        assert len(accounts) == 1
        assert accounts[0].id == DEFAULT_ACCOUNT_ID
