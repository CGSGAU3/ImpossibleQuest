import logging

from aiogram.exceptions import TelegramBadRequest
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
