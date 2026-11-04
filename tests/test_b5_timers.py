import asyncio
from collections import defaultdict
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage

from b_support import b_kit, position
from quest_bot.telegram_interface import GameTimers


async def test_lost_deadline_works_during_restart_confirmation(b_kit):
    app, sessions, story, clock, _ = b_kit
    state = await position(b_kit, 83)
    await sessions.put(1, story.choose(state, 0))
    confirmation = await app.command(1, "/restart")
    clock.now += 60
    view = await app.tick(1)
    state = await sessions.get(1)
    assert view is not None and state.scene == 86 and state.game is None
    assert not state.restart_pending
    with pytest.raises(ValueError):
        await app.callback(1, confirmation.buttons[0][1])


async def test_drunk_does_not_update_before_shuffle_interval(b_kit):
    app, sessions, story, clock, _ = b_kit
    state = await position(b_kit, 118)
    for index in [0, 1, 2]:
        state = story.choose(state, index)
    await sessions.put(1, state)
    clock.now += 1
    assert await app.tick(1) is None
    clock.now += 1
    assert await app.tick(1) is not None
    assert (await sessions.get(1)).game["shuffled"] == clock.now


async def test_timer_delivers_updates_and_closes_own_tasks_only(b_kit, monkeypatch):
    app, sessions, story, clock, store = b_kit
    state = await position(b_kit, 83)
    await sessions.put(1, story.choose(state, 0))
    delivered = asyncio.Queue()
    async def sender(message, view):
        await delivered.put(view)
        return message
    async def sleep(seconds):
        clock.now += seconds
        await asyncio.sleep(0)
    store_closed = False
    async def unexpected_close():
        nonlocal store_closed
        store_closed = True
    original_close = store.close
    monkeypatch.setattr(store, "close", unexpected_close)
    timers = GameTimers(app, sender, defaultdict(asyncio.Lock), sleep=sleep)
    timers.remember(1, SimpleNamespace(message_id=1))
    view = await asyncio.wait_for(delivered.get(), timeout=1)
    assert "Осталось" in view.text
    await timers.close()
    assert timers.tasks == {} and timers.messages == {} and not store_closed
    monkeypatch.setattr(store, "close", original_close)


async def test_no_background_task_for_normal_scene(b_kit):
    app, *_ = b_kit
    await app.command(1, "/start")
    async def sender(message, view):
        raise AssertionError("Для обычной сцены нет фонового обновления")
    timers = GameTimers(app, sender, defaultdict(asyncio.Lock))
    timers.remember(1, SimpleNamespace(message_id=1))
    assert timers.tasks == {} and timers.messages == {}
    await timers.close()


async def test_final_lost_view_retries_after_transient_delivery_failure(b_kit):
    app, sessions, story, clock, store = b_kit
    state = await position(b_kit, 83)
    await sessions.put(1, story.choose(state, 0))
    attempts = []
    delivered = []
    async def sender(message, view):
        attempts.append(view)
        if len(attempts) == 1:
            raise TelegramNetworkError(SendMessage(chat_id=1, text=view.text), "offline")
        delivered.append(view)
        return message
    async def blocked_sleep(seconds):
        await asyncio.Event().wait()
    timers = GameTimers(app, sender, defaultdict(asyncio.Lock), sleep=blocked_sleep)
    timers.remember(1, SimpleNamespace(message_id=1))
    try:
        clock.now += 60
        await timers.update(1)
        durable, _ = await store.read(1)
        assert durable.scene == 86 and durable.game is None
        assert 1 in timers.messages and 1 in timers.pending
        assert delivered == []
        await timers.update(1)
        assert len(attempts) == 2 and len(delivered) == 1
        assert delivered[0].text == story.content.scenes[86].text
        assert 1 not in timers.messages and 1 not in timers.pending
    finally:
        await timers.close()
