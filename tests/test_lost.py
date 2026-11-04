import pytest

from quest_bot import lost
from quest_bot.models import Rules, State
from quest_bot.story import StoryEngine


def begin(engine, flags=None):
    return engine.choose(State(scene=83, flags=flags or {}, history="12"), 0)


def test_lost_starts_with_shuffled_buttons_and_absolute_deadline(core_engine, core_clock):
    state = begin(core_engine)
    assert sorted(state.game["buttons"]) == sorted(lost.CODE)
    assert state.game["deadline"] == core_clock.now + 60
    assert state.game["entered"] == [] and state.history == "12"


@pytest.mark.parametrize("flag,destination", [(True, 85), (False, 98)])
def test_correct_code_routes_by_death_flag(core_engine, flag, destination):
    state = begin(core_engine, {"death_after_lost": flag})
    for number in lost.CODE:
        state = core_engine.play(state, str(number))
    assert state.scene == destination and state.game is None
    assert state.history == "12"


def test_wrong_sequence_loses_immediately(core_engine):
    original = begin(core_engine)
    result = core_engine.play(original, 8)
    assert result.scene == 86 and result.game is None
    assert original.game["entered"] == []


def test_last_number_is_accepted_just_before_deadline(core_engine, core_clock):
    state = begin(core_engine)
    for number in lost.CODE[:-1]:
        state = core_engine.play(state, number)
    core_clock.now = state.game["deadline"] - 0.001
    assert core_engine.play(state, 42).scene == 98


@pytest.mark.parametrize("delay", [0, 1])
def test_deadline_and_later_are_failure(core_engine, core_clock, delay):
    state = begin(core_engine)
    core_clock.now = state.game["deadline"] + delay
    result = core_engine.play(state, 4)
    assert result.scene == 86 and result.game is None
    assert state.game["entered"] == []


def test_tick_finishes_lost_without_player_action(core_engine, core_clock):
    state = begin(core_engine)
    core_clock.now = state.game["deadline"] - 1
    assert core_engine.tick(state) == state
    core_clock.now += 1
    assert core_engine.tick(state).scene == 86


def test_resumed_state_keeps_original_deadline(core_engine, core_clock):
    state = begin(core_engine)
    resumed = State.model_validate_json(state.model_dump_json())
    core_clock.now += 120
    assert core_engine.tick(resumed).scene == 86


@pytest.mark.parametrize("number", [True, 4.5, 99, "bad"])
def test_invalid_button_does_not_change_state(core_engine, number):
    state = begin(core_engine)
    before = state.model_dump()
    with pytest.raises(ValueError, match="числовая кнопка"):
        core_engine.play(state, number)
    assert state.model_dump() == before


def test_lost_rules_destinations_are_checked(core_engine, core_clock):
    with pytest.raises(ValueError, match="999"):
        StoryEngine(core_engine.content, core_engine.rng, core_clock, Rules(lost_win=999))
