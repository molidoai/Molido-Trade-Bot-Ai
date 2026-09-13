"""Basic tests for configuration loading."""

import importlib.util
import os
from pathlib import Path

import pytest

API_CONFIG = Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "core" / "config.py"


def _load_api_settings():
    """Import apps/api/app/core/config.py without going through `app`."""
    spec = importlib.util.spec_from_file_location("molido_api_config_undertest", API_CONFIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Settings


def test_settings_defaults(monkeypatch):
    """Ensure critical safety defaults are correct."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-32chars")
    monkeypatch.setenv("POSTGRES_PASSWORD", "testpassword123")
    monkeypatch.setenv("ENGINE_INTERNAL_TOKEN", "test-engine-token-16chars-min")

    # Loaded by file path, not by package name.
    #
    # Two services in this repo both own a top-level package called `app`:
    # apps/api/app is a regular package and apps/trading-engine/app is a
    # namespace package, so whichever appears first on sys.path decides what
    # `app.core` and `app.data` mean for the whole process. With the engine
    # first, `from app.core.config import Settings` silently resolved to an
    # editable install of a different project entirely
    # (MolidoTrade AI/backend), whose Settings has no trading_account_mode --
    # so this test failed with an AttributeError that looked like a defect in
    # the settings model and was nothing of the kind.
    #
    # It matters more than tidiness: this test is the guard on the safety
    # defaults -- DEMO, bot off -- and a guard that fails for an unrelated
    # reason gets waved through as "known broken", which is exactly what
    # happened to it.
    Settings = _load_api_settings()

    settings = Settings()
    assert settings.trading_account_mode == "DEMO"
    assert settings.master_bot_enabled is False
    assert settings.default_risk_per_trade == 0.005
    assert settings.max_drawdown == 0.05
