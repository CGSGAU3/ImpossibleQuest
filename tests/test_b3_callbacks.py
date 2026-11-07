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


@pytest.mark.parametrize("button_index", [0, 1])
async def test_ending_buttons_reset_once_and_keep_unlocked_endings(b_kit, button_index):
    app, sessions, story, _, store = b_kit
    state = await position(b_kit, 5)
    payload = app.render(1, state).buttons[button_index][1]

    view = await app.callback(1, payload)

    saved, opened = await store.read(1)
    assert saved.scene == story.content.start and not saved.restart_pending
    assert opened == {2}
    if button_index == 0:
        assert view.text == story.content.scenes[saved.scene].text
        assert view.buttons
    else:
        assert view.text.startswith("Открыто 1 из 38\n\n")
        assert story.content.endings[2] in view.text
        assert not view.buttons
    with pytest.raises(ValueError, match="устарела"):
        await app.callback(1, payload)
    assert (await sessions.get(1)).scene == saved.scene


async def test_ending_action_is_unavailable_on_ordinary_scene(b_kit):
    app, sessions, *_ = b_kit
    state = await position(b_kit, 7)

    with pytest.raises(ValueError, match="Неверная кнопка концовки"):
        await app.callback(1, f"{state.token}:ending:new")

    assert (await sessions.get(1)).model_dump() == state.model_dump()
