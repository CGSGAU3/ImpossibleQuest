import json
from importlib.resources import files
from pathlib import Path

from pydantic import ValidationError

from .models import Quest, Scene


class ContentError(ValueError):
    pass


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContentError(f"повторный ключ {key!r}")
        result[key] = value
    return result


def _field_error(error: ValidationError) -> str:
    item = error.errors(include_url=False)[0]
    field = ".".join(str(part) for part in item["loc"]) or "данные"
    return f"{field}: {item['msg']}"


def _check_references(quest: Quest):
    scenes = quest.scenes
    for field in ("start", "secret_ending"):
        target = getattr(quest, field)
        if target not in scenes:
            raise ContentError(f"{field}: сцена {target} не найдена")
    if scenes[quest.start].type != "scene":
        raise ContentError("start должен указывать на обычную сцену")
    if scenes[quest.secret_ending].type != "ending":
        raise ContentError("secret_ending должен указывать на концовку")

    ending_ids = {}
    battle_scenes = set()
    for sid, scene in scenes.items():
        if scene.type == "ending":
            if scene.ending_id in ending_ids:
                previous = ending_ids[scene.ending_id]
                raise ContentError(
                    f"сцена {sid}: ending_id {scene.ending_id} уже есть у сцены {previous}"
                )
            ending_ids[scene.ending_id] = sid
        for index, choice in enumerate(scene.choices):
            refs = {
                name: getattr(choice, name)
                for name in ("next", "start_scene", "hit", "hit_by_enemy", "win", "lose")
            }
            refs.update({f"options.{i}": target for i, target in enumerate(choice.options)})
            refs.update({f"conditions.{i}.next": c.next for i, c in enumerate(choice.conditions)})
            for field, target in refs.items():
                if target is not None and target not in scenes:
                    raise ContentError(
                        f"сцена {sid}, choices.{index}.{field}: сцена {target} не найдена"
                    )
            if choice.note == "battle":
                for field in ("start_scene", "hit", "hit_by_enemy"):
                    target = getattr(choice, field)
                    action_scene = scenes[target]
                    if (
                        action_scene.type != "scene"
                        or len(action_scene.choices) != 3
                        or any(action.note is not None or action.flags_required
                               for action in action_scene.choices)
                    ):
                        raise ContentError(
                            f"сцена {sid}, choices.{index}.{field}: "
                            f"сцена боя {target} должна содержать ровно три доступных действия"
                        )
                    battle_scenes.add(target)

    for sid, scene in scenes.items():
        for index, choice in enumerate(scene.choices):
            # В сценах боя следующий шаг вычисляет боевая механика.
            if choice.note is None and choice.next is None and sid not in battle_scenes:
                raise ContentError(f"сцена {sid}, choices.{index}: не задан переход next")


def load_content(path: str | Path | None = None) -> Quest:
    source = Path(path) if path is not None else files("quest_bot").joinpath("quest.json")
    try:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ContentError(f"не удалось прочитать файл: {error}") from error
        try:
            raw = json.loads(text, object_pairs_hook=_unique_keys)
        except json.JSONDecodeError as error:
            raise ContentError(
                f"неверный JSON, строка {error.lineno}, столбец {error.colno}: {error.msg}"
            ) from error
        if not isinstance(raw, dict):
            raise ContentError("корень JSON должен быть объектом")

        metadata = {name: raw.pop(name) for name in ("start", "secret_ending") if name in raw}
        scenes = {}
        for key, value in raw.items():
            try:
                sid = int(key)
            except ValueError as error:
                raise ContentError(f"некорректный идентификатор сцены {key!r}") from error
            if sid <= 0 or str(sid) != key:
                raise ContentError(f"некорректный идентификатор сцены {key!r}")
            try:
                scenes[sid] = Scene.model_validate(value)
            except ValidationError as error:
                raise ContentError(f"сцена {sid}: {_field_error(error)}") from error
        try:
            quest = Quest.model_validate({**metadata, "scenes": scenes})
        except ValidationError as error:
            raise ContentError(_field_error(error)) from error
        _check_references(quest)
        return quest
    except ContentError as error:
        raise ContentError(f"{source}: {error}") from error
