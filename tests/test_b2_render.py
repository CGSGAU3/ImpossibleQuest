from b_support import b_kit, position

from quest_bot import drunk
from quest_bot.endings import report


async def test_scene_and_ending_views(b_kit):
    app, sessions, story, *_ = b_kit
    state = await position(b_kit, 1)
    view = app.render(1, state)
    assert view.text == story.content.scenes[1].text
    assert len(view.buttons) == len(story.content.scenes[1].choices)
    assert all(data.startswith(state.token + ":choice:") for _, data in view.buttons)
    ending = await position(b_kit, 5)
    assert app.render(1, ending).buttons == []
    assert report({2}, story.content).startswith("Открыто 1 из 38")
    assert story.content.endings[2] in report({2}, story.content)


async def test_battle_and_pregame_views(b_kit):
    app, sessions, story, *_ = b_kit
    state = await position(b_kit, 53)
    state = story.choose(state, 0)
    state = story.choose(state, 1)
    state = await sessions.put(1, state)
    assert "9" in app.render(1, state).text
    state = await position(b_kit, 118)
    assert [label for label, _ in app.render(1, state).buttons] == list(drunk.PRE_LABELS)


async def test_minigame_and_outage_views(b_kit):
    app, sessions, story, clock, _ = b_kit
    state = await position(b_kit, 118)
    for index in [0, 1, 2]:
        state = story.choose(state, index)
    state = await sessions.put(1, state)
    view = app.render(1, state)
    assert "Раунд 1/3" in view.text
    assert [label for label, _ in view.buttons] == state.game["letters"]
    state = await position(b_kit, 83)
    state = story.choose(state, 0)
    state = await sessions.put(1, state)
    clock.now += 5
    view = app.render(1, state)
    assert "55 сек" in view.text
    assert {label for label, _ in view.buttons} == {"4", "8", "15", "16", "23", "42"}
    sessions.degraded.add(1)
    assert "Хранилище недоступно" in app.render(1, state).text
