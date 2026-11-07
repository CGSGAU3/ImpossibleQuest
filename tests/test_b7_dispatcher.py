from datetime import datetime, timezone

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SetMyCommands
from aiogram.types import InaccessibleMessage, Message, Update

from b_support import b_kit, position
from quest_bot.telegram_interface import build_dispatcher


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.last_id = 0
        self.fail_send = False

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (AnswerCallbackQuery, SetMyCommands)):
            return True
        if isinstance(method, (SendMessage, EditMessageText)):
            if self.fail_send:
                raise TelegramNetworkError(method, "offline")
            self.last_id += 1
            return Message(
                message_id=getattr(method, "message_id", None) or self.last_id,
                date=datetime.now(timezone.utc), chat={"id": method.chat_id, "type": "private"},
                text=method.text, reply_markup=method.reply_markup,
            )
        raise AssertionError(type(method))


def message_update(text, chat_type="private"):
    return Update.model_validate({"update_id": 1, "message": {
        "message_id": 1, "date": 1000, "chat": {"id": 1, "type": chat_type},
        "from": {"id": 1, "is_bot": False, "first_name": "Test"}, "text": text,
    }})


def callback_update(payload, uid=1):
    return Update.model_validate({"update_id": 2, "callback_query": {
        "id": "test", "from": {"id": uid, "is_bot": False, "first_name": "Test"},
        "chat_instance": "offline", "data": payload,
        "message": {"message_id": 1, "date": 1000, "chat": {"id": 1, "type": "private"}},
    }})


@pytest.fixture
async def transport(b_kit):
    app = b_kit[0]
    session = FakeSession()
    bot = Bot("123456:offline_test_token_abcdefghijklmnopqrstuvwxyz", session=session)
    dp = build_dispatcher(app)
    dp["bot"] = bot
    yield dp, bot, session
    await dp.emit_shutdown()
    await bot.session.close()


async def test_dispatcher_runs_start_and_choice_without_network(b_kit, transport):
    dp, bot, fake = transport
    await dp.feed_update(bot, message_update("/start@offline_bot"))
    sent = fake.calls[-1]
    assert isinstance(sent, SendMessage) and sent.reply_markup.inline_keyboard
    payload = sent.reply_markup.inline_keyboard[0][0].callback_data
    await dp.feed_update(bot, callback_update(payload))
    assert (await b_kit[1].get(1)).scene == 2
    assert any(isinstance(call, AnswerCallbackQuery) for call in fake.calls)
    assert isinstance(fake.calls[-1], EditMessageText)
    assert dp["game_timers"].tasks == {}


async def test_group_and_foreign_callback_do_not_change_game(b_kit, transport):
    dp, bot, fake = transport
    await dp.feed_update(bot, message_update("/start", "group"))
    assert "личный чат" in fake.calls[-1].text
    assert b_kit[1].states == {}
    await dp.feed_update(bot, message_update("/start"))
    payload = fake.calls[-1].reply_markup.inline_keyboard[0][0].callback_data
    before = (await b_kit[1].get(1)).model_dump()
    await dp.feed_update(bot, callback_update(payload, uid=2))
    assert (await b_kit[1].get(1)).model_dump() == before
    assert isinstance(fake.calls[-1], AnswerCallbackQuery)


async def test_delivery_failure_does_not_rollback_saved_session(b_kit, transport):
    dp, bot, fake = transport
    fake.fail_send = True
    await dp.feed_update(bot, message_update("/start"))
    assert (await b_kit[1].get(1)).scene == 1
    fake.fail_send = False
    await dp.feed_update(bot, message_update("/start"))
    assert fake.calls[-1].reply_markup.inline_keyboard


async def test_inaccessible_callback_does_not_advance_game(b_kit, transport):
    dp, bot, fake = transport
    await dp.feed_update(bot, message_update("/start"))
    payload = fake.calls[-1].reply_markup.inline_keyboard[0][0].callback_data
    before = (await b_kit[1].get(1)).model_dump()
    update_data = callback_update(payload).model_dump(mode="json", exclude_none=True)
    update_data["callback_query"]["message"]["date"] = 0
    update = Update.model_validate(update_data)
    assert isinstance(update.callback_query.message, InaccessibleMessage)
    calls_before = len(fake.calls)

    await dp.feed_update(bot, update)

    assert (await b_kit[1].get(1)).model_dump() == before
    assert len(fake.calls) == calls_before + 1
    answer = fake.calls[-1]
    assert isinstance(answer, AnswerCallbackQuery)
    assert answer.text == "Сообщение недоступно. Отправь /start"


@pytest.mark.parametrize("entry", ["choice", "resume"])
async def test_lost_times_out_after_first_view_delivery_fails(b_kit, transport, entry):
    dp, bot, fake = transport
    app, sessions, story, clock, store = b_kit
    state = await position(b_kit, 83)
    if entry == "choice":
        update = callback_update(app.render(1, state).buttons[0][1])
    else:
        await sessions.put(1, story.choose(state, 0))
        update = message_update("/start")
    fake.fail_send = True
    await dp.feed_update(bot, update)

    saved, _ = await store.read(1)
    timers = dp["game_timers"]
    assert saved.game["kind"] == "lost"
    assert 1 in timers.tasks and 1 in timers.pending

    # Двигаем тестовые часы и выполняем то же обновление, что и фоновая задача.
    clock.now = saved.game["deadline"]
    fake.fail_send = False
    await timers.update(1)

    saved, _ = await store.read(1)
    assert saved.scene == 86 and saved.game is None
    assert fake.calls[-1].text == story.content.scenes[86].text
    assert 1 not in timers.pending and 1 not in timers.messages


async def test_lost_result_is_retried_after_final_button_delivery_fails(b_kit, transport):
    dp, bot, fake = transport
    app, _, story, _, store = b_kit
    state = await position(b_kit, 83)
    await dp.feed_update(bot, callback_update(app.render(1, state).buttons[0][1]))

    for number in ["4", "8", "15", "16", "23", "42"]:
        keyboard = fake.calls[-1].reply_markup.inline_keyboard
        payload = next(row[0].callback_data for row in keyboard if row[0].text == number)
        fake.fail_send = number == "42"
        await dp.feed_update(bot, callback_update(payload))

    saved, _ = await store.read(1)
    assert saved.scene in {85, 98} and saved.game is None
    timers = dp["game_timers"]
    assert 1 in timers.tasks and 1 in timers.pending and 1 in timers.messages

    fake.fail_send = False
    await timers.update(1)

    assert fake.calls[-1].text == story.content.scenes[saved.scene].text
    assert 1 not in timers.pending and 1 not in timers.messages


async def test_dispatcher_startup_registers_slash_commands(transport):
    dp, bot, fake = transport

    await dp.emit_startup(bot=bot)

    assert len(fake.calls) == 1
    request = fake.calls[0]
    assert isinstance(request, SetMyCommands)
    assert [command.command for command in request.commands] == [
        "start", "help", "restart", "endings", "save", "load",
    ]
