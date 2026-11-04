from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


SceneId = Annotated[int, Field(gt=0)]
Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    flags_required: dict[str, bool]
    next: SceneId


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: Text
    next: SceneId | None = None
    note: Literal["conditional", "random_choice", "battle", "minigame"] | None = None
    flags: dict[str, bool] = Field(default_factory=dict)
    flags_required: dict[str, bool] = Field(default_factory=dict)
    conditions: list[Condition] = Field(default_factory=list)
    options: list[SceneId] = Field(default_factory=list)
    room: Literal["drunk", "lost"] | None = None
    start_scene: SceneId | None = None
    hit: SceneId | None = None
    hit_by_enemy: SceneId | None = None
    win: SceneId | None = None
    lose: SceneId | None = None

    @model_validator(mode="after")
    def check_special_fields(self):
        if self.note == "conditional" and not self.conditions:
            raise ValueError("для conditional нужен непустой список conditions")
        if self.note == "random_choice" and not self.options:
            raise ValueError("для random_choice нужен непустой список options")
        if self.note == "battle":
            required = ("start_scene", "hit", "hit_by_enemy", "win", "lose")
            missing = [name for name in required if getattr(self, name) is None]
            if missing:
                raise ValueError("для battle не заданы поля: " + ", ".join(missing))
        if self.note == "minigame":
            if self.room is None:
                raise ValueError("для minigame нужно поле room")
            if self.room == "drunk" and (self.win is None or self.lose is None):
                raise ValueError("для drunk нужны поля win и lose")
        return self


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["scene", "ending"]
    text: Text
    choices: list[Choice]
    ending_id: SceneId | None = None
    desc: str = ""

    @model_validator(mode="after")
    def check_scene_type(self):
        if self.type == "ending":
            if self.ending_id is None:
                raise ValueError("для концовки нужно поле ending_id")
            if self.choices:
                raise ValueError("у концовки не должно быть вариантов выбора")
        else:
            if not self.choices:
                raise ValueError("у обычной сцены должен быть хотя бы один вариант выбора")
            if self.ending_id is not None:
                raise ValueError("ending_id допустим только у концовки")
        return self


class Quest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    start: SceneId
    secret_ending: SceneId
    scenes: dict[SceneId, Scene]

    @property
    def endings(self) -> dict[int, str]:
        return {
            scene.ending_id: scene.desc
            for scene in self.scenes.values()
            if scene.type == "ending"
        }


class State(BaseModel):
    """Общий формат данных сессии, без правил изменения состояния."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scene: SceneId
    flags: dict[str, bool] = Field(default_factory=dict)
    history: str = ""
    battle: dict[str, Any] | None = None
    game: dict[str, Any] | None = None
    pre_drunk: dict[str, Any] | None = None

    revision: int = Field(default=0, ge=0)
    token: str = ""
    restart_pending: bool = False


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    lost_win: SceneId = 85
    lost_win_safe: SceneId = 98
    lost_lose: SceneId = 86
    lost_timeout: float = Field(default=60, gt=0, allow_inf_nan=False)
    shuffle_interval: float = Field(default=2, ge=1, allow_inf_nan=False)
