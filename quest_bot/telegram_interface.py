import asyncio
import logging

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

    def remember(self, uid, message):
        self.pending.pop(uid, None)
        state = self.app.sessions.states.get(uid)
        if not state or not state.game:
            self.messages.pop(uid, None)
            return
        self.messages[uid] = message
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
