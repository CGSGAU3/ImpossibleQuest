import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from quest_bot import bootstrap


def polling_env():
    return {"BOT_TOKEN": "123456:FAKE_TOKEN_FOR_TESTS", "TRANSPORT": "polling"}


@pytest.mark.parametrize("changes,message", [
    ({"BOT_TOKEN": ""}, "BOT_TOKEN"),
    ({"BOT_TOKEN": "invalid"}, "BOT_TOKEN"),
    ({"TRANSPORT": "invalid"}, "TRANSPORT"),
    ({"PORT": "abc"}, "PORT"),
    ({"PORT": "0"}, "PORT"),
    ({"PORT": "65536"}, "PORT"),
    ({"DATABASE_URL": "sqlite:///sync.db"}, "DATABASE_URL"),
])
def test_invalid_settings_fail_before_network(changes, message):
    with pytest.raises(ValueError, match=message):
        bootstrap.read_settings(polling_env() | changes)


def test_webhook_requires_https_and_secret():
    env = polling_env() | {"TRANSPORT": "webhook"}
    with pytest.raises(ValueError, match="HTTPS"):
        bootstrap.read_settings(env)
    env["WEBHOOK_BASE_URL"] = "https://example.test/bot/"
    with pytest.raises(ValueError, match="WEBHOOK_SECRET"):
        bootstrap.read_settings(env)
    settings = bootstrap.read_settings(env | {"WEBHOOK_SECRET": "Test_secret-12"})
    assert settings.webhook_base_url == "https://example.test/bot"
    assert settings.bind_host == "127.0.0.1" and settings.port == 8080
    assert settings.bot_token not in repr(settings)
    assert settings.webhook_secret not in repr(settings)


@pytest.mark.parametrize("url", ["http://example.test", "https://user:password@example.test",
                                     "https://example.test?a=1", "https://example.test#fragment"])
def test_ambiguous_webhook_urls_rejected(url):
    env = polling_env() | {"TRANSPORT": "webhook", "WEBHOOK_SECRET": "test",
                           "WEBHOOK_BASE_URL": url}
    with pytest.raises(ValueError):
        bootstrap.read_settings(env)


def test_webhook_wiring_and_secret(monkeypatch):
    from aiogram import Dispatcher

    bot = SimpleNamespace(set_webhook=AsyncMock())
    dispatcher = Dispatcher()
    settings = bootstrap.Settings("fake", webhook_base_url="https://example.test",
                                  webhook_secret="secret")
    app = bootstrap.create_webhook_app(dispatcher, bot, settings)
    routes = list(app.router.routes())
    assert len(routes) == 1 and routes[0].method == "POST"
    assert routes[0].resource.canonical == "/telegram/webhook"
    handler = routes[0].handler.__self__
    assert handler.handle_in_background is False
    assert handler.verify_secret("secret", bot) is True
    assert handler.verify_secret("wrong", bot) is False


async def test_webhook_startup_registers_public_url():
    from aiogram import Dispatcher

    bot = SimpleNamespace(set_webhook=AsyncMock())
    dispatcher = Dispatcher()
    settings = bootstrap.Settings("fake", webhook_base_url="https://example.test/bot",
                                  webhook_secret="secret")
    bootstrap.create_webhook_app(dispatcher, bot, settings)
    await dispatcher.emit_startup(bot=bot)
    bot.set_webhook.assert_awaited_once_with("https://example.test/bot/telegram/webhook",
                                           secret_token="secret")


@pytest.mark.parametrize("failure", [False, True])
async def test_polling_closes_owned_resources(monkeypatch, failure):
    import quest_bot.application
    import quest_bot.telegram_interface

    settings = bootstrap.Settings("fake", transport="polling")
    store = SimpleNamespace(init=AsyncMock(), close=AsyncMock())
    bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))

    class FakeDispatcher(dict):
        async def start_polling(self, value, **kwargs):
            assert value is bot and kwargs["close_bot_session"] is False
            if failure:
                raise RuntimeError("polling failed")

    monkeypatch.setattr(bootstrap, "read_settings", lambda: settings)
    monkeypatch.setattr(bootstrap, "Store", lambda url: store)
    monkeypatch.setattr(bootstrap, "Bot", lambda token: bot)
    monkeypatch.setattr(quest_bot.application, "Application", lambda sessions: object())
    monkeypatch.setattr(quest_bot.telegram_interface, "build_dispatcher", lambda app: FakeDispatcher())
    if failure:
        with pytest.raises(RuntimeError, match="polling failed"):
            await bootstrap.serve()
    else:
        await bootstrap.serve()
    store.init.assert_awaited_once()
    store.close.assert_awaited_once()
    bot.session.close.assert_awaited_once()


@pytest.mark.parametrize("site_fails", [False, True])
async def test_webhook_cleanup_on_error_or_cancellation(monkeypatch, site_fails):
    import quest_bot.application
    import quest_bot.telegram_interface
    from aiogram import Dispatcher

    store = SimpleNamespace(init=AsyncMock(), close=AsyncMock())
    bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()), set_webhook=AsyncMock())
    runner = SimpleNamespace(setup=AsyncMock(), cleanup=AsyncMock())
    site = SimpleNamespace(start=AsyncMock(side_effect=OSError("bind failed") if site_fails else None))

    class Stop:
        async def wait(self):
            raise asyncio.CancelledError

    monkeypatch.setattr(bootstrap, "read_settings", lambda: bootstrap.Settings(
        "fake", webhook_base_url="https://example.test", webhook_secret="secret"))
    monkeypatch.setattr(bootstrap, "Store", lambda url: store)
    monkeypatch.setattr(bootstrap, "Bot", lambda token: bot)
    monkeypatch.setattr(bootstrap.web, "AppRunner", lambda app: runner)
    monkeypatch.setattr(bootstrap.web, "TCPSite", lambda *args: site)
    monkeypatch.setattr(bootstrap, "asyncio", SimpleNamespace(Event=Stop))
    monkeypatch.setattr(quest_bot.application, "Application", lambda sessions: object())
    monkeypatch.setattr(quest_bot.telegram_interface, "build_dispatcher", lambda app: Dispatcher())
    with pytest.raises(OSError if site_fails else asyncio.CancelledError):
        await bootstrap.serve()
    runner.cleanup.assert_awaited_once()
    store.close.assert_awaited_once()
    bot.session.close.assert_awaited_once()
