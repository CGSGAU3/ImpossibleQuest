import logging
from logging.handlers import RotatingFileHandler

import pytest

from quest_bot.logging_config import configure_logging


@pytest.fixture
def reset_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    logger = logging.getLogger("quest_bot")
    logger_level = logger.level
    root.handlers = []
    yield
    for handler in root.handlers:
        handler.close()
    root.handlers = handlers
    root.setLevel(level)
    logger.setLevel(logger_level)


@pytest.fixture
def configured(tmp_path, monkeypatch, reset_logging):
    path = tmp_path / "quest.log"
    monkeypatch.setenv("LOG_PATH", str(path))
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    return path


def test_rotation_utf8_and_default_level(configured):
    root = logging.getLogger()
    files = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(files) == 1
    assert files[0].maxBytes == 2_000_000 and files[0].backupCount == 3
    logger = logging.getLogger("quest_bot.test")
    logger.info("Проверка журнала")
    logger.debug("Подробное состояние")
    text = configured.read_text(encoding="utf-8")
    assert "Проверка журнала" in text
    assert "Подробное состояние" not in text


async def test_ending_event_written_once(configured):
    from quest_bot.models import State
    from quest_bot.sessions import SessionManager
    from quest_bot.storage import Store
    from test_sessions import make_story

    store = Store("sqlite+aiosqlite:///:memory:")
    await store.init()
    try:
        sessions = SessionManager(store, make_story())
        state = await sessions.get(1)
        state.scene = next(sid for sid, scene in sessions.story.content.scenes.items()
                           if scene.type == "ending")
        await sessions.put(1, state)
        await sessions.put(1, state)
    finally:
        await store.close()
    assert configured.read_text(encoding="utf-8").count("Открыта концовка") == 1


async def test_bootstrap_logs_lifecycle_without_credentials(configured, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from quest_bot import bootstrap
    import quest_bot.application
    import quest_bot.telegram_interface

    token, secret = "do_not_log_this_token", "do_not_log_this_secret"
    settings = bootstrap.Settings(token, transport="polling", webhook_secret=secret)
    store = SimpleNamespace(init=AsyncMock(), close=AsyncMock())
    bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()), delete_webhook=AsyncMock())

    class Dispatcher(dict):
        async def start_polling(self, *args, **kwargs):
            return

    monkeypatch.setattr(bootstrap, "read_settings", lambda: settings)
    monkeypatch.setattr(bootstrap, "Store", lambda url: store)
    monkeypatch.setattr(bootstrap, "Bot", lambda value: bot)
    monkeypatch.setattr(quest_bot.application, "Application", lambda sessions: object())
    monkeypatch.setattr(quest_bot.telegram_interface, "build_dispatcher", lambda app: Dispatcher())
    await bootstrap.serve()
    text = configured.read_text(encoding="utf-8")
    assert "Запуск приложения" in text and "Остановка приложения" in text
    assert "Карта загружена: сцен 151, концовок 38" in text
    assert token not in text and secret not in text


def test_debug_level_does_not_enable_dependency_debug_logs(tmp_path, monkeypatch, reset_logging):
    path = tmp_path / "quest.log"
    monkeypatch.setenv("LOG_PATH", str(path))
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging()
    logging.getLogger("quest_bot.test").debug("Диагностика квеста")
    logging.getLogger("aiogram.test").debug("Диагностика библиотеки")
    text = path.read_text(encoding="utf-8")
    assert "Диагностика квеста" in text
    assert "Диагностика библиотеки" not in text


def test_unavailable_log_file_keeps_stderr(tmp_path, monkeypatch, reset_logging, capsys):
    monkeypatch.setenv("LOG_PATH", str(tmp_path / "missing" / "quest.log"))
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    logging.getLogger("quest_bot.test").info("Бот работает")
    stderr = capsys.readouterr().err
    assert "Файл журнала недоступен" in stderr
    assert "Бот работает" in stderr
