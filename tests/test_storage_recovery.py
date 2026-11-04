import pytest
from sqlalchemy.exc import OperationalError

from quest_bot.models import State
from quest_bot.sessions import SessionManager
from quest_bot.storage import Store

from test_sessions import make_story


async def unavailable(*args, **kwargs):
    raise OperationalError("operation", {}, OSError("offline"))


@pytest.fixture
async def kit():
    store = Store("sqlite+aiosqlite:///:memory:")
    await store.init()
    sessions = SessionManager(store, make_story())
    yield store, sessions
    await store.close()


async def test_write_outage_keeps_game_in_memory_and_recovers(kit, monkeypatch):
    store, sessions = kit
    state = await sessions.get(1)
    await sessions.put(1, state)
    write = store.write
    monkeypatch.setattr(store, "write", unavailable)
    state = state.model_copy(deep=True)
    state.scene = 2
    await sessions.put(1, state)
    assert (await sessions.get(1)).scene == 2
    assert 1 in sessions.degraded
    assert (await store.read(1))[0].scene == 1
    monkeypatch.setattr(store, "write", write)
    await sessions.put(1, state)
    assert 1 not in sessions.degraded
    assert (await store.read(1))[0].scene == 2


async def test_initial_read_outage_merges_previously_opened_endings(kit, monkeypatch):
    store, sessions = kit
    await store.write(1, State(scene=2), {3, 7})
    read = store.read
    monkeypatch.setattr(store, "read", unavailable)
    state = await sessions.get(1)
    assert state.scene == 1 and sessions.endings[1] == set()
    assert 1 in sessions.degraded
    state.scene = 2
    await sessions.put(1, state)
    assert 1 in sessions.degraded
    monkeypatch.setattr(store, "read", read)
    sessions.endings[1].add(9)
    await sessions.put(1, state)
    assert sessions.endings[1] == {3, 7, 9}
    assert (await store.read(1))[1] == {3, 7, 9}
    assert 1 not in sessions.degraded


async def test_failure_is_scoped_to_affected_user(kit, monkeypatch):
    store, sessions = kit
    read = store.read

    async def selective(uid):
        return await unavailable() if uid == 1 else await read(uid)

    monkeypatch.setattr(store, "read", selective)
    await sessions.get(1)
    await sessions.get(2)
    assert sessions.degraded == {1}


async def test_recovery_creates_schema_after_initial_directory_failure(tmp_path):
    folder = tmp_path / "temporarily_unavailable"
    store = Store(f"sqlite+aiosqlite:///{folder / 'quest.db'}")
    sessions = SessionManager(store, make_story())
    try:
        state = await sessions.get(1)
        assert 1 in sessions.degraded
        folder.mkdir()
        state.flags["continued"] = True
        await sessions.put(1, state)
        assert 1 not in sessions.degraded
        loaded, _ = await store.read(1)
        assert loaded.flags == {"continued": True}
    finally:
        await store.close()
