import asyncio
import logging
from collections import defaultdict

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


log = logging.getLogger(__name__)


async def send_view(bot, chat_id, view, edit=None):
    markup = None
    if view.buttons:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=label[:60], callback_data=data)]
            for label, data in view.buttons
        ])
    chunks = [view.text[index:index + 4000] for index in range(0, len(view.text), 4000)] or [" "]
    if edit is not None and len(chunks) == 1:
        try:
            await edit.edit_text(chunks[0], reply_markup=markup)
            return edit
        except TelegramBadRequest as error:
            if "message is not modified" in str(error):
                return edit
            log.warning("Не удалось обновить сообщение, отправляем новое")
    message = None
    for index, chunk in enumerate(chunks):
        message = await bot.send_message(
            chat_id, chunk, reply_markup=markup if index == len(chunks) - 1 else None,
        )
    return message


class GameTimers:
    def __init__(self, app, sender, locks, sleep=asyncio.sleep):
        self.app = app
        self.sender = sender
        self.locks = locks
        self.sleep = sleep
        self.messages = {}
        self.tasks = {}
        self.pending = {}

    def remember(self, uid, message, pending=None):
        self.pending.pop(uid, None)
        state = self.app.sessions.states.get(uid)
        retry_result = pending is not None and uid in self.messages
        if not state or (not state.game and not retry_result):
            self.messages.pop(uid, None)
            return
        self.messages[uid] = message
        if pending is not None:
            self.pending[uid] = pending
        task = self.tasks.get(uid)
        if task is None or task.done():
            self.tasks[uid] = asyncio.create_task(self._loop(uid))

    async def update(self, uid):
        async with self.locks[uid]:
            message = self.messages.get(uid)
            if message is None:
                return
            updated = await self.app.tick(uid)
            if updated is not None:
                self.pending[uid] = updated
            view = self.pending.get(uid)
            if view is not None:
                try:
                    self.messages[uid] = await self.sender(message, view)
                except TelegramRetryAfter as error:
                    log.warning("Telegram ограничил обновления: %s секунд", error.retry_after)
                except (TelegramBadRequest, TelegramNetworkError):
                    log.warning("Не удалось доставить обновление мини-игры", exc_info=True)
                else:
                    self.pending.pop(uid, None)
            state = self.app.sessions.states.get(uid)
            if (not state or not state.game) and uid not in self.pending:
                self.messages.pop(uid, None)

    async def _loop(self, uid):
        try:
            while uid in self.messages:
                await self.sleep(1)
                await self.update(uid)
        except asyncio.CancelledError:
            pass
        finally:
            self.tasks.pop(uid, None)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.messages.clear()
        self.pending.clear()


def build_dispatcher(app):
    dp = Dispatcher()
    locks = defaultdict(asyncio.Lock)

    async def deliver(target, view):
        if isinstance(target, int):
            return await send_view(dp["bot"], target, view)
        return await send_view(dp["bot"], target.chat.id, view, edit=target)

    timers = GameTimers(app, deliver, locks)
    dp["game_timers"] = timers

    async def acknowledge(callback, text=None):
        try:
            await callback.answer(text)
        except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter):
            log.warning("Не удалось подтвердить нажатие", exc_info=True)

    @dp.message()
    async def on_message(message: Message):
        if message.chat.type != "private":
            await message.answer("Открой личный чат с ботом")
            return
        if message.from_user is None:
            return
        uid = message.from_user.id
        command = (message.text or "").split(maxsplit=1)
        command = command[0].split("@")[0] if command else ""
        async with locks[uid]:
            view = await app.command(uid, command)
            follows_game = bool(view.buttons) or command == "/start"
            try:
                sent = await send_view(dp["bot"], message.chat.id, view)
            except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter):
                log.warning("Не удалось отправить ответ на команду", exc_info=True)
                if follows_game:
                    timers.remember(uid, message.chat.id, pending=view)
                return
            if follows_game:
                timers.remember(uid, sent)

    @dp.callback_query()
    async def on_callback(callback: CallbackQuery):
        uid = callback.from_user.id
        if (not callback.message or callback.message.chat.type != "private"
                or callback.message.chat.id != uid):
            await acknowledge(callback, "Открой личный чат с ботом")
            return
        if not isinstance(callback.message, Message):
            await acknowledge(callback, "Сообщение недоступно. Отправь /start")
            return
        async with locks[uid]:
            try:
                view = await app.callback(uid, callback.data or "")
            except (ValueError, TypeError) as error:
                await acknowledge(callback, str(error)[:180])
                return
            await acknowledge(callback)
            try:
                sent = await deliver(callback.message, view)
            except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter):
                log.warning("Не удалось отправить результат выбора", exc_info=True)
                timers.remember(uid, callback.message, pending=view)
                return
            timers.remember(uid, sent)

    async def shutdown():
        await timers.close()

    dp.shutdown.register(shutdown)
    return dp
