from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from quest_bot.models import State
from quest_bot.storage import Base, Checkpoint, OpenedEnding, Session, Store


@pytest.fixture
async def store():
    value = Store("sqlite+aiosqlite:///:memory:", clock=lambda: 1000)
    await value.init()
    yield value
    await value.close()


async def test_schema_and_unknown_user(store):
    async with store.engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
        assert set(tables) == {"users", "sessions", "opened_endings", "checkpoints"}
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
    assert await store.read(5) == (None, set())
    assert await store.checkpoint(5) is None


async def test_state_roundtrip_and_users_isolated(store):
    state = State(scene=54, flags={"key": True}, battle={"hp": 8, "ehp": 6},
                  game={"kind": "lost", "deadline": 1060})
    await store.write(1, state, {1, 3})
    await store.write(2, State(scene=1), {2})
    loaded, endings = await store.read(1)
    assert loaded == state
    assert endings == {1, 3}
    assert (await store.read(2))[1] == {2}
    async with store.session() as db:
        row = await db.get(Session, 1)
        assert (row.current_scene_id, row.player_hp, row.enemy_hp) == (54, 8, 6)
        assert row.battle_active is True
        assert row.minigame_state == state.game


async def test_endings_unique_and_first_opening_time_preserved(store):
    await store.write(1, State(scene=1), {4})
    store.clock = lambda: 2000
    await store.write(1, State(scene=2), {4, 5})
    async with store.session() as db:
        rows = (await db.scalars(select(OpenedEnding).order_by(OpenedEnding.ending_id))).all()
        assert len(rows) == 2
        assert rows[0].opened_at == datetime.fromtimestamp(1000, timezone.utc).replace(tzinfo=None)
        assert rows[1].opened_at == datetime.fromtimestamp(2000, timezone.utc).replace(tzinfo=None)
    with pytest.raises(IntegrityError):
        async with store.session.begin() as db:
            db.add(OpenedEnding(user_id=1, ending_id=4, opened_at=datetime.now(timezone.utc)))


async def test_foreign_key_rejects_orphan_checkpoint(store):
    with pytest.raises(IntegrityError):
        async with store.session.begin() as db:
            db.add(Checkpoint(user_id=99, scene_id=1, flags={}))


async def test_checkpoint_replaces_single_row(store):
    await store.save_checkpoint(1, State(scene=2, flags={"a": True}))
    await store.save_checkpoint(1, State(scene=3, flags={"b": False}))
    assert await store.checkpoint(1) == (3, {"b": False})
    async with store.session() as db:
        assert len((await db.scalars(select(Checkpoint))).all()) == 1


async def test_file_store_survives_engine_restart(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'quest.db'}"
    first = Store(url)
    await first.init()
    await first.write(7, State(scene=12, flags={"visited": True}), {2})
    await first.close()
    second = Store(url)
    try:
        loaded, endings = await second.read(7)
        assert loaded.scene == 12 and loaded.flags == {"visited": True}
        assert endings == {2}
    finally:
        await second.close()


async def test_parallel_in_memory_transactions_keep_all_records(store):
    import asyncio

    async def play(uid):
        state = State(scene=2, flags={"visited": True})
        await store.write(uid, state, {1})
        await store.save_checkpoint(uid, state)
        assert await store.read(uid) == (state, {1})

    await asyncio.gather(*(play(uid) for uid in range(1, 21)))
    for uid in range(1, 21):
        assert await store.read(uid) == (State(scene=2, flags={"visited": True}), {1})
        assert await store.checkpoint(uid) == (2, {"visited": True})
