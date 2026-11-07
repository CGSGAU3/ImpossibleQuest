import asyncio
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import random
import re
import time
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.utils.token import TokenValidationError, validate_token
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from .content import load_content
from .models import Rules
from .sessions import SessionManager, STORAGE_ERRORS
from .storage import Store


log = logging.getLogger(__name__)
WEBHOOK_PATH = "/telegram/webhook"


@dataclass
class Settings:
    bot_token: str = field(repr=False)
    transport: str = "webhook"
    webhook_base_url: str = ""
    webhook_secret: str = field(default="", repr=False)
    database_url: str = "sqlite+aiosqlite:///quest.db"
    bind_host: str = "127.0.0.1"
    port: int = 8080
    quest_path: str | None = None
    rules_path: str | None = None


def read_settings(environ=None):
    env = os.environ if environ is None else environ
    token = env.get("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("Для запуска бота нужна переменная BOT_TOKEN")
    try:
        validate_token(token)
    except TokenValidationError as error:
        raise ValueError("BOT_TOKEN имеет неверный формат") from error
    transport = env.get("TRANSPORT", "webhook")
    if transport not in {"webhook", "polling"}:
        raise ValueError("TRANSPORT должен быть webhook или polling")
    try:
        port = int(env.get("PORT", "8080"))
    except ValueError as error:
        raise ValueError("PORT должен быть целым числом") from error
    if not 1 <= port <= 65535:
        raise ValueError("PORT должен быть от 1 до 65535")
    database_url = env.get("DATABASE_URL", "sqlite+aiosqlite:///quest.db")
    if not database_url.startswith("sqlite+aiosqlite:///"):
        raise ValueError("DATABASE_URL должен использовать sqlite+aiosqlite:///")
    public = env.get("WEBHOOK_BASE_URL", "").rstrip("/")
    secret = env.get("WEBHOOK_SECRET", "")
    if transport == "webhook":
        parts = urlsplit(public)
        if (parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment
                or parts.username or parts.password):
            raise ValueError("WEBHOOK_BASE_URL должен быть HTTPS-адресом без параметров и пароля")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret):
            raise ValueError("WEBHOOK_SECRET: нужны 1–256 латинских букв, цифр, _ или -")
    return Settings(
        bot_token=token, transport=transport, webhook_base_url=public,
        webhook_secret=secret, database_url=database_url,
        bind_host=env.get("BIND_HOST", "127.0.0.1"), port=port,
        quest_path=env.get("QUEST_PATH"), rules_path=env.get("RULES_PATH"),
    )


def create_webhook_app(dispatcher, bot, settings):
    server = web.Application()
    handler = SimpleRequestHandler(dispatcher, bot, secret_token=settings.webhook_secret,
                                   handle_in_background=False)
    # Сессию Bot закрывает serve после остановки обработчиков.
    server.router.add_post(WEBHOOK_PATH, handler.handle)
    setup_application(server, dispatcher, bot=bot)
    return server


async def serve(quest_path=None):
    from .application import Application
    from .story import StoryEngine
    from .telegram_interface import build_dispatcher

    settings = read_settings()
    log.info("Запуск приложения, версия 0.1.0")
    content = load_content(quest_path or settings.quest_path)
    log.info("Карта загружена: сцен %s, концовок %s", len(content.scenes), len(content.endings))
    rules = (Rules.model_validate_json(Path(settings.rules_path).read_text(encoding="utf-8"))
             if settings.rules_path else Rules())
    store = Store(settings.database_url)
    bot = None
    runner = None
    try:
        try:
            await store.init()
        except STORAGE_ERRORS:
            log.error("Хранилище недоступно при запуске, сессии будут храниться в памяти", exc_info=True)
        sessions = SessionManager(store, StoryEngine(content, random.Random(), time.time, rules))
        app = Application(sessions)
        bot = Bot(settings.bot_token)
        dispatcher = build_dispatcher(app)
        dispatcher["bot"] = bot
        if settings.transport == "polling":
            await bot.delete_webhook(drop_pending_updates=False)
            await dispatcher.start_polling(bot, close_bot_session=False)
            return
        server = create_webhook_app(dispatcher, bot, settings)
        runner = web.AppRunner(server)
        await runner.setup()
        await web.TCPSite(runner, settings.bind_host, settings.port).start()
        await bot.set_webhook(settings.webhook_base_url + WEBHOOK_PATH,
                              secret_token=settings.webhook_secret)
        await asyncio.Event().wait()
    finally:
        try:
            if runner is not None:
                await runner.cleanup()
        finally:
            try:
                await store.close()
            finally:
                if bot is not None:
                    await bot.session.close()
                log.info("Остановка приложения")
