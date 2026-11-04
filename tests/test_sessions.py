import asyncio
from types import SimpleNamespace

import pytest

from quest_bot.content import load_content
from quest_bot.models import State
from quest_bot.sessions import SessionManager
from quest_bot.storage import Store


def make_story():
    content = load_content()
    return SimpleNamespace(content=content, new=lambda: State(scene=content.start),
                           arrive=lambda state: None)


@pytest.fixture
async def sessions():
    store = Store("sqlite+aiosqlite:///:memory:")
    await store.init()
    value = SessionManager(store, make_story())
    yield value
    await store.close()


async def test_one_session_per_user_and_separate_locks(sessions):
    first = await sessions.get(1)
    assert first is await sessions.get(1)
    assert first is not await sessions.get(2)
    assert sessions.locks[1] is not sessions.locks[2]


async def test_each_accepted_state_gets_new_token(sessions):
    state = await sessions.get(1)
    first = await sessions.put(1, state)
    token = first.token
    second = await sessions.put(1, first.model_copy(deep=True))
    assert token and second.token and token != second.token
    assert second.revision == 2


async def test_disk_resume_preserves_special_mode_and_deadline(sessions):
    state = await sessions.get(1)
    state.game = {"kind": "lost", "deadline": 100, "entered": [4, 8]}
    await sessions.put(1, state)
    restored = SessionManager(sessions.store, make_story())
    loaded = await restored.get(1)
    assert loaded.game == state.game
    assert loaded.token == state.token
    assert loaded.revision == 1


async def test_endings_survive_new_playthrough_without_duplicates(sessions):
    state = await sessions.get(1)
    ending_scene = next(sid for sid, scene in sessions.story.content.scenes.items()
                        if scene.type == "ending")
    state.scene = ending_scene
    await sessions.put(1, state)
    await sessions.put(1, state)
    ending_id = sessions.story.content.scenes[ending_scene].ending_id
    await sessions.put(1, sessions.story.new())
    assert sessions.endings[1] == {ending_id}
    restored = SessionManager(sessions.store, make_story())
    assert (await restored.get(1)).scene == sessions.story.content.start
    assert restored.endings[1] == {ending_id}


async def test_actions_can_be_serialized_per_user(sessions):
    async def accept():
        async with sessions.locks[1]:
            state = (await sessions.get(1)).model_copy(deep=True)
            await asyncio.sleep(0)
            await sessions.put(1, state)

    await asyncio.gather(*(accept() for _ in range(12)))
    assert (await sessions.get(1)).revision == 12
