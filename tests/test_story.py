import random

import pytest
from pydantic import ValidationError

from quest_bot import flags
from quest_bot.models import Condition, Rules, State
from quest_bot.story import StoryEngine


def test_new_game_starts_clean(small_engine):
    first = small_engine.new()
    first.flags["seen"] = True
    second = small_engine.new()
    assert second.scene == small_engine.content.start
    assert second.flags == {}
    assert second.history == ""
    assert second.game is None and second.battle is None


def test_visible_choices_follow_flags(small_engine):
    state = small_engine.new()
    assert [index for index, _ in small_engine.choices(state)] == [0, 2]
    state.flags["seen"] = True
    assert [index for index, _ in small_engine.choices(state)] == [0, 1, 2]
    assert flags.matches({}, {"missing": False})


def test_normal_transition_sets_flags_without_mutating_input(small_engine):
    original = small_engine.new()
    result = small_engine.choose(original, 0)
    assert result.scene == 2 and result.flags == {"seen": True}
    assert original.scene == 1 and original.flags == {}


def test_conditional_transition_uses_updated_flags(small_engine):
    state = small_engine.choose(small_engine.new(), 0)
    assert small_engine.choose(state, 0).scene == 3
    assert small_engine.choose(State(scene=2), 0).scene == 4


def test_seeded_random_transition_is_repeatable(small_engine, core_clock):
    other = StoryEngine(small_engine.content, random.Random(7), core_clock, Rules())
    assert small_engine.choose(small_engine.new(), 2) == other.choose(other.new(), 2)


@pytest.mark.parametrize("index", [-1, 1, 100, True, "0"])
def test_unavailable_choice_does_not_change_state(small_engine, index):
    state = small_engine.new()
    before = state.model_dump()
    with pytest.raises(ValueError, match="недоступен"):
        small_engine.choose(state, index)
    assert state.model_dump() == before


def test_unknown_scene_is_reported_without_changes(small_engine):
    state = State(scene=999)
    with pytest.raises(ValueError, match="999"):
        small_engine.choices(state)
    assert state.scene == 999


def test_unmatched_condition_is_atomic(small_engine):
    small_engine.content.scenes[2].choices[0].conditions = [Condition(flags_required={"other": True}, next=3)]
    state = State(scene=2)
    with pytest.raises(ValueError, match="условия"):
        small_engine.choose(state, 0)
    assert state == State(scene=2)


def test_shared_state_fields_survive_json_roundtrip():
    state = State(scene=1, revision=3, token="test-token", restart_pending=True)
    assert State.model_validate_json(state.model_dump_json()) == state
    assert State(scene=1).revision == 0


@pytest.mark.parametrize("kwargs", [{"shuffle_interval": 0.9}, {"lost_timeout": 0}, {"lost_timeout": float("inf")}])
def test_rules_reject_invalid_timing(kwargs):
    with pytest.raises(ValidationError):
        Rules(**kwargs)
