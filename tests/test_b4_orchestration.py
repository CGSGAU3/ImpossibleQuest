from sqlalchemy.exc import OperationalError

from b_support import b_kit, position
from quest_bot.sessions import SessionManager


async def test_choice_is_saved_and_view_matches_persisted_scene(b_kit):
    app, sessions, story, _, store = b_kit
    view = await app.command(1, "/start")
    result = await app.callback(1, view.buttons[0][1])
    durable, _ = await store.read(1)
    assert durable.scene == 2
    assert story.content.scenes[durable.scene].text in result.text
    await position(b_kit, 19)
    state = await sessions.get(1)
    state.flags["panic_death"] = True
    await sessions.put(1, state)
    view = await app.command(1, "/start")
    await app.callback(1, view.buttons[0][1])
    durable, _ = await store.read(1)
    assert durable.scene == 28 and durable.flags["panic_death"]


async def test_storage_failure_is_visible_and_progress_recovers(b_kit, monkeypatch):
    app, sessions, _, _, store = b_kit
    original = store.write
    async def fail(*args):
        raise OperationalError("write", {}, Exception("offline"))
    monkeypatch.setattr(store, "write", fail)
    view = await app.command(1, "/start")
    assert "Хранилище недоступно" in view.text
    view = await app.callback(1, view.buttons[0][1])
    assert (await sessions.get(1)).scene == 2
    assert "недоступно" in (await app.command(1, "/save")).text
    monkeypatch.setattr(store, "write", original)
    await app.command(1, "/start")
    assert 1 not in sessions.degraded
    assert (await store.read(1))[0].scene == 2


async def test_ending_survives_restart_and_new_session_manager(b_kit):
    app, sessions, story, _, store = b_kit
    await position(b_kit, 7)
    view = await app.command(1, "/start")
    await app.callback(1, view.buttons[1][1])
    assert sessions.endings[1] == {2}
    confirmation = await app.command(1, "/restart")
    await app.callback(1, confirmation.buttons[0][1])
    fresh = SessionManager(store, story)
    assert (await fresh.get(1)).scene == 1
    assert fresh.endings[1] == {2}
    report = await app.command(1, "/endings")
    assert report.text.startswith("Открыто 1 из 38")
