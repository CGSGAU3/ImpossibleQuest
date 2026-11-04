import pytest

from quest_bot.models import State


class FixedAttack:
    def randint(self, start, end):
        return 1


def begin(engine):
    engine.rng = FixedAttack()
    return engine.choose(State(scene=53, history="12"), 0)


def test_battle_starts_with_hp_and_preserves_history(core_engine):
    state = begin(core_engine)
    assert state.scene == 54
    assert state.battle["hp"] == 10 and state.battle["ehp"] == 7
    assert state.history == "12"
    assert len(core_engine.choices(state)) == 3


def test_hit_and_miss_keep_original_state(core_engine):
    state = begin(core_engine)
    hit = core_engine.choose(state, 0)
    miss = core_engine.choose(state, 1)
    assert hit.scene == 56 and hit.battle["ehp"] == 6 and hit.battle["hp"] == 10
    assert miss.scene == 55 and miss.battle["hp"] == 9 and miss.battle["ehp"] == 7
    assert state.battle["hp"] == 10 and state.battle["ehp"] == 7
    assert hit.history == miss.history == "12"


@pytest.mark.parametrize("index,rounds,destination", [(0, 7, 58), (1, 10, 57)])
def test_battle_finishes_at_zero_hp(core_engine, index, rounds, destination):
    state = begin(core_engine)
    for _ in range(rounds):
        state = core_engine.choose(state, index)
    assert state.scene == destination
    assert state.battle is None
    assert core_engine.content.scenes[state.scene].type == "ending"


@pytest.mark.parametrize("index", [-1, 3, True, "0"])
def test_invalid_attack_does_not_change_battle(core_engine, index):
    state = begin(core_engine)
    before = state.model_dump()
    with pytest.raises(ValueError, match="действие"):
        core_engine.choose(state, index)
    assert state.model_dump() == before
