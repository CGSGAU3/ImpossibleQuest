import pytest

from quest_bot.checkpoints import SaveLoadManager
from quest_bot.models import State
from quest_bot.sessions import SessionManager
from quest_bot.storage import Store

from test_sessions import make_story
from test_storage_recovery import unavailable


@pytest.fixture
async def kit():
    store = Store("sqlite+aiosqlite:///:memory:")
    await store.init()
    sessions = SessionManager(store, make_story())
    await sessions.get(1)
    yield store, sessions, SaveLoadManager(sessions)
    await store.close()


async def test_load_without_checkpoint_starts_from_first_scene(kit):
    _, sessions, manager = kit
    loaded = await manager.load(1, State(scene=2, flags={"old": True}))
    assert loaded.scene == sessions.story.content.start
    assert loaded.flags == {}


async def test_checkpoint_contains_only_scene_and_flags(kit):
    store, sessions, manager = kit
    state = State(scene=2, flags={"key": True}, history="123", revision=8, token="old")
    sessions.endings[1] = {2, 7}
    await manager.save(1, state)
    loaded = await manager.load(1, State(scene=3))
    assert loaded.scene == 2 and loaded.flags == {"key": True}
    assert loaded.history == "" and loaded.token == "" and loaded.revision == 0
    assert sessions.endings[1] == {2, 7}
    assert await store.checkpoint(1) == (2, {"key": True})


@pytest.mark.parametrize("mode", ["battle", "game"])
async def test_save_and_load_are_blocked_in_special_modes(kit, mode):
    _, _, manager = kit
    state = State(scene=2, **{mode: {"active": True}})
    with pytest.raises(ValueError):
        await manager.save(1, state)
    with pytest.raises(ValueError):
        await manager.load(1, state)


async def test_save_is_blocked_at_ending(kit):
    _, sessions, manager = kit
    ending = next(sid for sid, scene in sessions.story.content.scenes.items()
                  if scene.type == "ending")
    with pytest.raises(ValueError, match="обычной сцене"):
        await manager.save(1, State(scene=ending))


async def test_degraded_storage_blocks_both_commands(kit):
    _, sessions, manager = kit
    sessions.degraded.add(1)
    for method in (manager.save, manager.load):
        with pytest.raises(ValueError, match="Хранилище недоступно"):
            await method(1, State(scene=1))


@pytest.mark.parametrize("operation,store_method", [("save", "save_checkpoint"), ("load", "checkpoint")])
async def test_checkpoint_failure_marks_storage_unavailable(kit, monkeypatch, operation, store_method):
    store, sessions, manager = kit
    monkeypatch.setattr(store, store_method, unavailable)
    with pytest.raises(ValueError, match="Хранилище недоступно"):
        await getattr(manager, operation)(1, State(scene=1))
    assert 1 in sessions.degraded
