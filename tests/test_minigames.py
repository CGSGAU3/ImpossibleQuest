from types import SimpleNamespace

import pytest

from quest_bot import minigames
from quest_bot.models import State


def test_game_has_no_story_choices_and_unknown_actions_do_not_apply(core_engine):
    state = core_engine.choose(State(scene=83), 0)
    assert core_engine.choices(state) == []
    with pytest.raises(ValueError, match="только действия"):
        core_engine.choose(state, 0)
    assert state.game["entered"] == []


def test_inactive_game_rejects_input(core_engine):
    state = core_engine.new()
    with pytest.raises(ValueError, match="неактивна"):
        core_engine.play(state, "4")
    assert state == core_engine.new()


def test_finished_game_does_not_accept_another_button(core_engine):
    state = core_engine.choose(State(scene=83), 0)
    state = core_engine.play(state, "8")
    assert state.scene == 86 and state.game is None
    with pytest.raises(ValueError, match="неактивна"):
        core_engine.play(state, "4")


def test_expired_lost_returns_outcome_before_validating_old_button(core_engine, core_clock):
    state = core_engine.choose(State(scene=83), 0)
    core_clock.now = state.game["deadline"]
    assert core_engine.play(state, "old-button").scene == 86
    assert core_engine.choose(state, 0).scene == 86
    assert state.game is not None


def test_new_game_clears_all_special_modes(core_engine):
    state = core_engine.choose(State(scene=83), 0)
    restarted = core_engine.new()
    assert state.game is not None
    assert restarted.game is None and restarted.battle is None and restarted.pre_drunk is None


def test_unknown_game_is_reported(core_engine):
    with pytest.raises(ValueError, match="Неизвестная"):
        minigames.enter(SimpleNamespace(room="missing"), 0, core_engine.rng, core_engine.rules)
    with pytest.raises(ValueError, match="Неизвестная"):
        minigames.step({"kind": "missing"}, "4", 0, core_engine.rules)


def test_tick_does_not_clear_restart_confirmation_before_deadline(core_engine, core_clock):
    state = core_engine.choose(State(scene=83), 0)
    state.restart_pending = True
    core_clock.now += 1
    result = core_engine.tick(state)
    assert result.restart_pending is True
    assert result.game["deadline"] == state.game["deadline"]


@pytest.mark.parametrize("method,args", [("tick", ()), ("choose", (0,)), ("play", ("4",))])
def test_unknown_scene_cannot_be_recovered_by_an_action(core_engine, method, args):
    state = State(scene=999)
    before = state.model_dump()
    with pytest.raises(ValueError, match="999"):
        getattr(core_engine, method)(state, *args)
    assert state.model_dump() == before
