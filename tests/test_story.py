import random

import pytest
from pydantic import ValidationError

from quest_bot import flags
from quest_bot.models import Condition, Rules, State
from quest_bot.story import SECRET, StoryEngine


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


def test_unmatched_condition_is_hidden_and_rejected(small_engine):
    choice = small_engine.content.scenes[2].choices[0]
    choice.conditions = [Condition(flags_required={"other": True}, next=3)]
    state = State(scene=2)

    assert small_engine.choices(state) == []
    with pytest.raises(ValueError, match="недоступен"):
        small_engine.choose(state, 0)
    assert state == State(scene=2)


def test_conditional_visibility_includes_flags_set_by_the_choice(small_engine):
    choice = small_engine.content.scenes[2].choices[0]
    choice.conditions = [Condition(flags_required={"other": True}, next=3)]
    choice.flags = {"other": True}
    state = State(scene=2)

    assert small_engine.choices(state) == [(0, choice)]
    assert state.flags == {}
    result = small_engine.choose(state, 0)
    assert result.scene == 3
    assert result.flags == {"other": True}


def test_secret_path_keeps_precedence_over_an_unmatched_condition(small_engine):
    choice = small_engine.content.scenes[2].choices[0]
    choice.conditions = [Condition(flags_required={"other": True}, next=3)]
    state = State(scene=2, history=SECRET[:-1])

    assert small_engine.choices(state) == [(0, choice)]
    assert small_engine.choose(state, 0).scene == small_engine.content.secret_ending


def test_shared_state_fields_survive_json_roundtrip():
    state = State(scene=1, revision=3, token="test-token", restart_pending=True)
    assert State.model_validate_json(state.model_dump_json()) == state
    assert State(scene=1).revision == 0


@pytest.mark.parametrize("kwargs", [{"shuffle_interval": 0.9}, {"lost_timeout": 0}, {"lost_timeout": float("inf")}])
def test_rules_reject_invalid_timing(kwargs):
    with pytest.raises(ValidationError):
        Rules(**kwargs)


def test_scene44_parachute_choice_goes_to_scene48(core_engine):
    state = State(scene=44)
    choice_index = next(
        index for index, choice in core_engine.choices(state)
        if choice.text == "Выпутаться из парашюта"
    )

    assert core_engine.choose(state, choice_index).scene == 48


def test_scene45_wait_expires_at_exact_deadline(core_engine, core_clock):
    waiting = core_engine.choose(State(scene=44), 0)

    assert waiting.scene == 45
    assert waiting.scene_deadline == 1300.0
    assert waiting.game is None and waiting.battle is None
    assert State.model_validate_json(waiting.model_dump_json()) == waiting

    core_clock.now = 1299.9
    assert core_engine.tick(waiting) == waiting
    core_clock.now = 1300.0
    expired = core_engine.tick(waiting)
    assert expired.scene == 46
    assert expired.scene_deadline is None
    assert core_engine.tick(expired) == expired
    assert waiting.scene == 45


def test_scene45_can_leave_before_deadline(core_engine, core_clock):
    waiting = core_engine.choose(State(scene=44), 0)
    core_clock.now = 1299.9
    next_state = core_engine.choose(waiting, 0)

    assert next_state.scene == 48
    assert next_state.scene_deadline is None
    core_clock.now = 1300.0
    assert core_engine.tick(next_state) == next_state


def test_scene45_expiry_takes_priority_over_late_choice(core_engine, core_clock):
    waiting = core_engine.choose(State(scene=44), 0)
    core_clock.now = waiting.scene_deadline

    expired = core_engine.choose(waiting, 0)

    assert expired.scene == 46
    assert expired.scene_deadline is None
    assert expired.history == waiting.history
    assert expired.flags == waiting.flags


def test_scene45_fresh_arrival_starts_full_wait(core_engine, core_clock):
    previous = core_engine.choose(State(scene=44), 0)
    core_clock.now = 1100.0
    loaded = State(scene=45, flags={"saved": True})

    core_engine.arrive(loaded)

    assert loaded.scene_deadline == 1400.0
    assert previous.scene_deadline == 1300.0
    assert loaded.flags == {"saved": True}


def test_unrelated_map_keeps_scene45_ordinary(small_engine):
    small_engine.content.scenes[45] = small_engine.content.scenes[1]
    small_engine.content.scenes[46] = small_engine.content.scenes[4]
    state = State(scene=45)

    small_engine.arrive(state)

    assert state.scene_deadline is None
    assert small_engine.choose(state, 0).scene == 2



def test_old_scene45_session_gets_a_deadline_once(core_engine, core_clock):
    saved = State.model_validate_json('{"scene":45}')
    resumed = core_engine.tick(saved)

    assert resumed.scene_deadline == 1300.0
    assert saved.scene_deadline is None
    core_clock.now = 1100.0
    assert core_engine.tick(resumed).scene_deadline == 1300.0
