import asyncio

import pytest

from b_support import b_kit, position


async def test_callback_changes_only_owner_and_cannot_be_replayed(b_kit):
    app, sessions, *_ = b_kit
    view = await app.command(1, "/start")
    await app.command(2, "/start")
    payload = view.buttons[0][1]
    with pytest.raises(ValueError):
        await app.callback(2, payload)
    assert (await sessions.get(2)).scene == 1
    await app.callback(1, payload)
    assert (await sessions.get(1)).scene == 2
    with pytest.raises(ValueError):
        await app.callback(1, payload)


async def test_simultaneous_click_is_applied_once(b_kit):
    app, sessions, *_ = b_kit
    view = await app.command(1, "/start")
    result = await asyncio.gather(
        *(app.callback(1, view.buttons[0][1]) for _ in range(6)), return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in result) == 1
    assert (await sessions.get(1)).history == "1"


async def test_restart_cancel_and_confirm_preserve_endings(b_kit):
    app, sessions, *_ = b_kit
    await position(b_kit, 9)
    sessions.endings[1].add(2)
    confirmation = await app.command(1, "/restart")
    await app.callback(1, confirmation.buttons[1][1])
    assert (await sessions.get(1)).scene == 9
    confirmation = await app.command(1, "/restart")
    await app.callback(1, confirmation.buttons[0][1])
    state = await sessions.get(1)
    assert state.scene == 1 and not state.restart_pending
    assert sessions.endings[1] == {2}


@pytest.mark.parametrize("suffix", ["choice:-1", "choice:no", "other:0"])
async def test_invalid_action_does_not_change_state(b_kit, suffix):
    app, sessions, *_ = b_kit
    await app.command(1, "/start")
    state = await sessions.get(1)
    before = state.model_dump()
    with pytest.raises(ValueError):
        await app.callback(1, f"{state.token}:{suffix}")
    assert (await sessions.get(1)).model_dump() == before
