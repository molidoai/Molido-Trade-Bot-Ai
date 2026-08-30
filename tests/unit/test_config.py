"""Basic tests for configuration loading."""

import os
import pytest


def test_settings_defaults(monkeypatch):
    """Ensure critical safety defaults are correct."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-32chars")
    monkeypatch.setenv("POSTGRES_PASSWORD", "testpassword123")
    monkeypatch.setenv("ENGINE_INTERNAL_TOKEN", "test-engine-token-16chars-min")

    # Re-import after env is set
    from app.core.config import Settings

    settings = Settings()
    assert settings.trading_account_mode == "DEMO"
    assert settings.master_bot_enabled is False
    assert settings.default_risk_per_trade == 0.005
    assert settings.max_drawdown == 0.05
