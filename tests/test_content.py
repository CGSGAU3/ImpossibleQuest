import json

import pytest
from pydantic import ValidationError

from quest_bot.content import ContentError, load_content
from quest_bot.models import State


@pytest.fixture
def small_quest():
    return {
        "start": 1,
        "secret_ending": 2,
        "1": {
            "type": "scene",
            "text": "Начало",
            "choices": [{"text": "Закончить", "next": 2, "flags": {"seen": True}}],
        },
        "2": {
            "type": "ending",
            "text": "Конец",
            "choices": [],
            "ending_id": 1,
            "desc": "Первая концовка",
        },
    }


@pytest.fixture
def write_quest(tmp_path):
    def write(data):
        path = tmp_path / "quest.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    return write


def test_loads_external_map_without_changing_it(small_quest, write_quest):
    path = write_quest(small_quest)
    original = path.read_bytes()

    quest = load_content(path)

    assert quest.start == 1
    assert quest.secret_ending == 2
    assert quest.scenes[1].choices[0].flags == {"seen": True}
    assert quest.endings == {1: "Первая концовка"}
    assert path.read_bytes() == original


def test_loads_supplied_map_and_preserves_battle_actions():
    quest = load_content()

    assert len(quest.scenes) == 151
    assert len(quest.endings) == 38
    assert quest.secret_ending == 161
    assert quest.scenes[54].choices[0].next is None
    assert quest.scenes[55].choices[0].next is None
    assert quest.scenes[56].choices[0].next is None


def test_accepts_supported_transition_types(small_quest, write_quest):
    small_quest["1"]["choices"] = [
        {"text": "По условию", "note": "conditional", "conditions": [{"flags_required": {"a": True}, "next": 2}]},
        {"text": "Случайно", "note": "random_choice", "options": [2]},
        {"text": "В бой", "note": "battle", "start_scene": 3, "hit": 3, "hit_by_enemy": 3, "win": 2, "lose": 2},
        {"text": "Drunk", "note": "minigame", "room": "drunk", "win": 2, "lose": 2},
        {"text": "Lost", "note": "minigame", "room": "lost"},
    ]
    small_quest["3"] = {"type": "scene", "text": "Бой", "choices": [{"text": "Удар", "next": None}]}

    quest = load_content(write_quest(small_quest))

    assert len(quest.scenes[1].choices) == 5
    assert quest.scenes[3].choices[0].next is None


@pytest.mark.parametrize(
    "choice, field",
    [
        ({"text": "Дальше", "next": 999}, "next"),
        ({"text": "По условию", "note": "conditional", "conditions": [{"flags_required": {}, "next": 999}]}, "conditions.0.next"),
        ({"text": "Случайно", "note": "random_choice", "options": [999]}, "options.0"),
        ({"text": "Drunk", "note": "minigame", "room": "drunk", "win": 999, "lose": 2}, "win"),
        ({"text": "Drunk", "note": "minigame", "room": "drunk", "win": 2, "lose": 999}, "lose"),
        ({"text": "Lost", "note": "minigame", "room": "lost", "win": 999}, "win"),
    ],
)
def test_rejects_broken_references(small_quest, write_quest, choice, field):
    small_quest["1"]["choices"] = [choice]
    path = write_quest(small_quest)

    with pytest.raises(ContentError) as caught:
        load_content(path)

    assert str(path) in str(caught.value)
    assert f"сцена 1, choices.0.{field}" in str(caught.value)
    assert "999" in str(caught.value)


@pytest.mark.parametrize("field", ["start_scene", "hit", "hit_by_enemy", "win", "lose"])
def test_checks_every_battle_destination(small_quest, write_quest, field):
    choice = {"text": "Бой", "note": "battle", "start_scene": 1, "hit": 1, "hit_by_enemy": 1, "win": 2, "lose": 2}
    choice[field] = 999
    small_quest["1"]["choices"] = [choice]

    with pytest.raises(ContentError, match=rf"choices.0.{field}.*999"):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize(
    "choice",
    [
        {"text": "Переход без цели"},
        {"text": "По условию", "note": "conditional"},
        {"text": "Случайно", "note": "random_choice", "options": []},
        {"text": "Бой", "note": "battle", "start_scene": 1},
        {"text": "Мини-игра", "note": "minigame"},
        {"text": "Drunk", "note": "minigame", "room": "drunk", "win": 2},
        {"text": "Пустой выбор", "next": None},
        {"text": "Неверный тип ссылки", "next": "2"},
        {"text": "Неверный тип флага", "next": 2, "flags": {"seen": "true"}},
        {"text": " ", "next": 2},
    ],
)
def test_rejects_incomplete_or_invalid_choices(small_quest, write_quest, choice):
    small_quest["1"]["choices"] = [choice]

    with pytest.raises(ContentError, match="сцена 1"):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("field", ["text", "type", "choices"])
def test_scene_fields_are_required(small_quest, write_quest, field):
    del small_quest["1"][field]

    with pytest.raises(ContentError, match=rf"сцена 1.*{field}"):
        load_content(write_quest(small_quest))


def test_regular_scene_needs_choices(small_quest, write_quest):
    small_quest["1"]["choices"] = []

    with pytest.raises(ContentError, match="хотя бы один вариант"):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize(
    "update",
    [
        {"type": "unknown"},
        {"text": ""},
        {"text": 123},
        {"ending_id": 1},
        {"unexpected": True},
    ],
)
def test_rejects_invalid_scene_fields(small_quest, write_quest, update):
    small_quest["1"].update(update)

    with pytest.raises(ContentError, match="сцена 1"):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("value", [None, 0, -1, True, "1"])
def test_ending_id_must_be_a_positive_integer(small_quest, write_quest, value):
    small_quest["2"]["ending_id"] = value

    with pytest.raises(ContentError, match="сцена 2"):
        load_content(write_quest(small_quest))


def test_ending_id_is_required(small_quest, write_quest):
    del small_quest["2"]["ending_id"]

    with pytest.raises(ContentError, match="ending_id"):
        load_content(write_quest(small_quest))


def test_ending_cannot_have_choices(small_quest, write_quest):
    small_quest["2"]["choices"] = [{"text": "Назад", "next": 1}]

    with pytest.raises(ContentError, match="у концовки не должно"):
        load_content(write_quest(small_quest))


def test_ending_ids_must_be_unique(small_quest, write_quest):
    small_quest["3"] = dict(small_quest["2"])

    with pytest.raises(ContentError, match="ending_id 1 уже есть у сцены 2"):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("field", ["start", "secret_ending"])
def test_start_and_secret_are_required(small_quest, write_quest, field):
    del small_quest[field]

    with pytest.raises(ContentError, match=field):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("field", ["start", "secret_ending"])
@pytest.mark.parametrize("value", [999, 0, True, "1"])
def test_start_and_secret_are_valid_scene_ids(small_quest, write_quest, field, value):
    small_quest[field] = value

    with pytest.raises(ContentError, match=field):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("field,value", [("start", 2), ("secret_ending", 1)])
def test_start_and_secret_point_to_correct_scene_types(small_quest, write_quest, field, value):
    small_quest[field] = value

    with pytest.raises(ContentError, match=field):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("key", ["bad", "01", "-1", "0"])
def test_scene_keys_are_positive_canonical_ids(small_quest, write_quest, key):
    small_quest[key] = small_quest.pop("1")

    with pytest.raises(ContentError, match="идентификатор сцены"):
        load_content(write_quest(small_quest))


@pytest.mark.parametrize("data", [None, [], "quest", 42])
def test_root_must_be_an_object(write_quest, data):
    with pytest.raises(ContentError, match="корень JSON"):
        load_content(write_quest(data))


def test_json_syntax_error_has_path_and_line(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{\n"start": 1,}', encoding="utf-8")

    with pytest.raises(ContentError) as caught:
        load_content(path)

    assert str(path) in str(caught.value)
    assert "строка 2" in str(caught.value)


def test_duplicate_json_keys_are_not_silently_replaced(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"start": 1, "start": 2}', encoding="utf-8")

    with pytest.raises(ContentError, match="повторный ключ 'start'"):
        load_content(path)


def test_missing_file_has_readable_error(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(ContentError) as caught:
        load_content(path)

    assert str(path) in str(caught.value)
    assert "не удалось прочитать" in str(caught.value)


def test_directory_cannot_be_loaded_as_file(tmp_path):
    with pytest.raises(ContentError, match="не удалось прочитать"):
        load_content(tmp_path)


def test_invalid_text_encoding_is_a_content_error(tmp_path):
    path = tmp_path / "bytes.json"
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(ContentError, match="не удалось прочитать"):
        load_content(path)


def test_states_have_independent_mutable_defaults():
    first = State(scene=1)
    second = State(scene=1)
    first.flags["seen"] = True

    assert second.flags == {}
    assert second.history == ""
    assert second.battle is None
    assert second.game is None


def test_state_roundtrip_keeps_mode_data():
    state = State(scene=1, flags={"seen": True}, battle={"hp": 3}, game=None)

    assert State.model_validate_json(state.model_dump_json()) == state


@pytest.mark.parametrize("scene", [0, True, "1"])
def test_state_rejects_invalid_scene_ids(scene):
    with pytest.raises(ValidationError):
        State(scene=scene)
