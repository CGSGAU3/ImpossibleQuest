from quest_bot.models import Choice, State
from quest_bot.story import SECRET


def test_secret_sequence_opens_catalogued_ending(small_engine):
    small_engine.content.scenes[1].choices = [Choice(text=str(i), next=1) for i in range(3)]
    state = small_engine.new()
    for digit in SECRET:
        state = small_engine.choose(state, int(digit) - 1)
    assert state.scene == small_engine.content.secret_ending
    assert small_engine.content.scenes[state.scene].ending_id == 1
    assert len(small_engine.content.endings) == 1


def test_history_keeps_only_needed_suffix(small_engine):
    small_engine.content.scenes[1].choices = [Choice(text="Еще", next=1)]
    state = small_engine.new()
    for _ in range(30):
        state = small_engine.choose(state, 0)
    assert state.history == "1" * len(SECRET)
    assert state.scene == 1


def test_new_game_clears_secret_history(small_engine):
    previous = State(scene=1, history=SECRET[:-1])
    assert small_engine.new().history == ""
    assert previous.history == SECRET[:-1]


def test_regular_ending_exposes_its_id(small_engine):
    result = small_engine.choose(State(scene=2), 0)
    scene = small_engine.content.scenes[result.scene]
    assert scene.type == "ending" and scene.ending_id == 1
    assert small_engine.choices(result) == []
