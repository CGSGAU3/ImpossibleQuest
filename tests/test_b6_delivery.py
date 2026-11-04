from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import EditMessageText, SendMessage

from quest_bot.application import View
from quest_bot.telegram_interface import send_view


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=len(self.calls), chat=SimpleNamespace(id=chat_id))


async def test_long_text_splits_with_keyboard_only_on_last_part():
    bot = FakeBot()
    message = await send_view(bot, 1, View("x" * 8001, [("Выбор", "token:choice:0")]))
    assert [len(call[1]) for call in bot.calls] == [4000, 4000, 1]
    assert bot.calls[0][2]["reply_markup"] is None
    assert bot.calls[1][2]["reply_markup"] is None
    assert bot.calls[2][2]["reply_markup"].inline_keyboard[0][0].callback_data == "token:choice:0"
    assert message.message_id == 3


@pytest.mark.parametrize("unchanged", [True, False])
async def test_edit_error_either_keeps_message_or_sends_replacement(unchanged):
    bot = FakeBot()
    async def fail(*args, **kwargs):
        text = "message is not modified" if unchanged else "message can't be edited"
        raise TelegramBadRequest(EditMessageText(chat_id=1, message_id=5, text="old"), text)
    original = SimpleNamespace(edit_text=fail)
    message = await send_view(bot, 1, View("Новая сцена"), edit=original)
    assert (message is original) is unchanged
    assert len(bot.calls) == (0 if unchanged else 1)


async def test_network_failure_is_reported_to_caller():
    async def fail(*args, **kwargs):
        raise TelegramNetworkError(SendMessage(chat_id=1, text="Сцена"), "offline")
    with pytest.raises(TelegramNetworkError):
        await send_view(SimpleNamespace(send_message=fail), 1, View("Сцена"))
