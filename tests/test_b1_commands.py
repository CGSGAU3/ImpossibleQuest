from b_support import b_kit, position


async def test_start_continues_and_unknown_command_preserves_state(b_kit):
    app, sessions, *_ = b_kit
    first = await app.command(1, "/start")
    assert first.buttons and (await sessions.get(1)).scene == 1
    await position(b_kit, 9)
    await app.command(1, "/start")
    assert (await sessions.get(1)).scene == 9
    before = (await sessions.get(1)).model_dump()
    assert (await app.command(1, "/bad")).text == "Неизвестная команда"
    assert (await sessions.get(1)).model_dump() == before
    assert "/save" in (await app.command(1, "/help")).text


async def test_restart_asks_before_resetting(b_kit):
    app, sessions, *_ = b_kit
    await position(b_kit, 9)
    view = await app.command(1, "/restart")
    state = await sessions.get(1)
    assert state.scene == 9 and state.restart_pending
    assert [label for label, _ in view.buttons] == ["Да", "Нет"]
    assert all(data.startswith(state.token + ":restart:") for _, data in view.buttons)


async def test_checkpoint_commands_and_missing_checkpoint(b_kit):
    app, sessions, *_ = b_kit
    await position(b_kit, 9)
    assert (await app.command(1, "/save")).text == "Чекпоинт сохранен"
    await position(b_kit, 7)
    await app.command(1, "/load")
    assert (await sessions.get(1)).scene == 9
    await app.command(2, "/load")
    assert (await sessions.get(2)).scene == 1
    assert (await app.command(1, "/endings")).text.startswith("Открыто 0 из 38")


async def test_endings_warns_when_session_read_fails(b_kit, monkeypatch):
    app, sessions, _, _, store = b_kit

    async def fail_read(uid):
        raise OSError("offline")

    monkeypatch.setattr(store, "read", fail_read)
    view = await app.command(1, "/endings")

    assert 1 in sessions.degraded
    assert view.text.startswith("Хранилище недоступно.")
    assert "Открыто 0 из 38" in view.text


async def test_restart_warns_when_confirmation_write_fails(b_kit, monkeypatch):
    app, sessions, _, _, store = b_kit
    await position(b_kit, 9)

    async def fail_write(*args):
        raise OSError("offline")

    monkeypatch.setattr(store, "write", fail_write)
    view = await app.command(1, "/restart")

    assert 1 in sessions.degraded
    assert view.text.startswith("Хранилище недоступно.")
    assert [label for label, _ in view.buttons] == ["Да", "Нет"]
    state = await sessions.get(1)
    assert state.scene == 9 and state.restart_pending
