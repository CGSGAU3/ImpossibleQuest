from itertools import permutations

import pytest

from quest_bot import drunk
from quest_bot.models import State


def begin(engine, order=(0, 1, 2)):
    state = State(scene=118, history="12")
    engine.arrive(state)
    for index in order:
        state = engine.choose(state, index)
    return state


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_pregame_clicks_remove_selected_buttons_until_last(core_engine, order):
    state = State(scene=118)
    core_engine.arrive(state)
    state = core_engine.choose(state, order[0])
    assert state.game is None and state.scene == 118
    assert order[0] not in dict(core_engine.choices(state))
    state = core_engine.choose(state, order[1])
    assert state.game is None and len(core_engine.choices(state)) == 1
    state = core_engine.choose(state, order[2])
    assert state.game["kind"] == "drunk" and state.pre_drunk is None


def test_pregame_does_not_advance_on_time(core_engine, core_clock):
    state = State(scene=118)
    core_engine.arrive(state)
    core_clock.now += 500
    assert core_engine.tick(state) == state
    assert core_engine.new().pre_drunk is None


def test_three_correct_rounds_win_without_secret_history(core_engine):
    state = begin(core_engine)
    for word, _ in drunk.ROUNDS:
        for letter in word:
            state = core_engine.play(state, letter)
    assert state.game is None and state.scene == 124
    assert state.history == "12"


def test_wrong_letter_loses_and_unknown_button_is_atomic(core_engine):
    state = begin(core_engine)
    lost = core_engine.play(state, "В")
    assert lost.game is None and lost.scene == 123
    before = state.model_dump()
    with pytest.raises(ValueError, match="буква"):
        core_engine.play(state, "X")
    assert state.model_dump() == before


def test_shuffle_obeys_interval_and_preserves_input(core_engine, core_clock):
    state = begin(core_engine)
    original = state.model_dump()
    core_clock.now += 1.9
    assert core_engine.tick(state) == state
    core_clock.now += 0.1
    updated = core_engine.tick(state)
    assert updated.game["shuffled"] == core_clock.now
    assert sorted(updated.game["letters"]) == sorted(drunk.LETTERS)
    assert state.model_dump() == original
    assert core_engine.tick(updated) == updated


def test_round_change_does_not_force_early_shuffle(core_engine, core_clock):
    state = begin(core_engine)
    original_time = state.game["shuffled"]
    for letter in "КОТ":
        state = core_engine.play(state, letter)
    assert state.game["round"] == 1 and state.game["word"] == ""
    assert state.game["shuffled"] == original_time


def test_regular_choices_are_rejected_during_drunk(core_engine):
    state = begin(core_engine)
    with pytest.raises(ValueError, match="только действия"):
        core_engine.choose(state, 0)


def test_preparation_labels_match_agreed_text():
    assert drunk.PRE_LABELS == (
        "Я пьяный?! Т-ты пьяный!",
        "А-а-а де тут туалет?",
        "А чиво все крутица?",
    )
