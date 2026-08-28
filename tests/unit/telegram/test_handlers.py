import pytest
from molido_telegram.handlers import CommandRouter, BotState


@pytest.mark.asyncio
async def test_start_and_status():
    state = BotState(master_bot_on=False, account_mode="DEMO", equity=10000, balance=10000)
    router = CommandRouter(state, auth_is_admin=lambda c: c == "1")
    text = await router.handle("1", "/start")
    assert "Molido" in text
    text = await router.handle("1", "/status")
    assert "DEMO" in text
    assert "OFF" in text


@pytest.mark.asyncio
async def test_pause_admin_only():
    state = BotState(master_bot_on=True)
    router = CommandRouter(state, auth_is_admin=lambda c: c == "admin")
    msg = await router.handle("other", "/pause")
    assert "ادمین" in msg or "⛔" in msg
    assert state.master_bot_on is True
    msg = await router.handle("admin", "/pause")
    assert state.master_bot_on is False


@pytest.mark.asyncio
async def test_resume_needs_confirm():
    state = BotState(master_bot_on=False)
    router = CommandRouter(state, auth_is_admin=lambda c: True)
    msg = await router.handle("1", "/resume")
    assert "/confirm" in msg
    assert state.master_bot_on is False
    msg = await router.handle("1", "/confirm resume")
    assert state.master_bot_on is True
