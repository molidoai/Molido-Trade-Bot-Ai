import logging

from molido_telegram.bot import _RedactToken

TOKEN = "8818287877:AAH-P5ugxuPncMZXZSuu-bk0py-sIw-lKaE"


def _record(msg, args=()):
    return logging.LogRecord("x", logging.INFO, __file__, 1, msg, args, None)


def _run(msg, args=()):
    rec = _record(msg, args)
    assert _RedactToken().filter(rec) is True
    return rec.getMessage()


def test_redacts_token_in_a_url():
    out = _run("HTTP Request: POST https://api.telegram.org/bot%s/sendMessage" % TOKEN)
    assert TOKEN not in out
    assert "AAH-P5ug" not in out
    assert "bot<redacted>" in out


def test_redacts_token_supplied_through_lazy_args():
    # httpx logs with %-args, so the token is not in record.msg at all until
    # the record is formatted -- a filter that only looked at msg would pass
    # it straight through to the handler.
    out = _run("HTTP Request: %s %s", ("GET", "https://api.telegram.org/bot%s/getUpdates" % TOKEN))
    assert TOKEN not in out
    assert "bot<redacted>" in out


def test_redacts_a_token_that_is_not_the_configured_one():
    other = "1234567890:BBFZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZz"
    out = _run("calling https://api.telegram.org/bot%s/getMe" % other)
    assert other not in out


def test_leaves_ordinary_messages_alone():
    assert _run("telegram token/admin chat id not configured yet; waiting") == (
        "telegram token/admin chat id not configured yet; waiting"
    )
    assert _run("equity: 974.16 | positions: 1") == "equity: 974.16 | positions: 1"


def test_never_raises_on_a_non_string_message():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, {"a": 1}, (), None)
    assert _RedactToken().filter(rec) is True
