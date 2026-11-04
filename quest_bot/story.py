from . import battle, drunk, flags
from .models import Quest, State


SECRET = "2213112312113312231"


class StoryEngine:
    def __init__(self, content: Quest, rng, clock, rules):
        self.content = content
        self.rng = rng
        self.clock = clock
        self.rules = rules

    def _scene(self, sid):
        if sid not in self.content.scenes:
            raise ValueError(f"Сцена {sid} не найдена")
        return self.content.scenes[sid]

    def new(self):
        state = State(scene=self.content.start)
        self.arrive(state)
        return state

    def arrive(self, state):
        scene = self._scene(state.scene)
        if not state.battle and any(choice.room == "drunk" for choice in scene.choices):
            state.pre_drunk = {
                "visible": [index for index, choice in enumerate(scene.choices)
                            if flags.matches(state.flags, choice.flags_required)]
            }
        else:
            state.pre_drunk = None

    def choices(self, state):
        scene = self._scene(state.scene)
        return [
            (index, choice)
            for index, choice in enumerate(scene.choices)
            if flags.matches(state.flags, choice.flags_required)
            and (not state.pre_drunk or index in state.pre_drunk["visible"])
        ]

    def choose(self, state, index):
        result = state.model_copy(deep=True)
        if result.game:
            raise ValueError("Сейчас доступны только действия мини-игры")
        if result.battle:
            result.scene, finished = battle.step(result.battle, index, self.rng)
            if finished:
                result.battle = None
            self.arrive(result)
            return result
        available = dict(self.choices(result))
        if type(index) is not int or index not in available:
            raise ValueError("Этот вариант выбора недоступен")
        choice = available[index]
        if result.pre_drunk and len(result.pre_drunk["visible"]) > 1:
            result.pre_drunk["visible"].remove(index)
            return result
        if choice.note == "minigame" and choice.room != "drunk":
            raise ValueError("Для этого выбора нужен модуль специального режима")
        flags.apply(result.flags, choice.flags)
        if choice.note == "battle":
            result.battle = battle.enter(choice)
            result.scene = choice.start_scene
            self.arrive(result)
            return result
        if choice.note == "minigame":
            result.game = drunk.enter(choice.win, choice.lose, self.clock(), self.rng)
            result.pre_drunk = None
            return result
        result.history = (result.history + str(index + 1))[-len(SECRET):]
        if result.history == SECRET:
            destination = self.content.secret_ending
        elif choice.note == "conditional":
            destination = next(
                (condition.next for condition in choice.conditions
                 if flags.matches(result.flags, condition.flags_required)),
                None,
            )
            if destination is None:
                raise ValueError("Нет подходящего условия перехода")
        elif choice.note == "random_choice":
            destination = self.rng.choice(choice.options)
        else:
            destination = choice.next
        self._scene(destination)
        result.scene = destination
        self.arrive(result)
        return result

    def play(self, state, value):
        result = state.model_copy(deep=True)
        if not result.game:
            raise ValueError("Мини-игра неактивна")
        if result.game["kind"] != "drunk":
            raise ValueError("Неизвестная мини-игра")
        destination = drunk.step(result.game, value)
        if destination is not None:
            self._scene(destination)
            result.game = None
            result.scene = destination
            self.arrive(result)
        return result

    def tick(self, state):
        result = state.model_copy(deep=True)
        now = self.clock()
        if (result.game and result.game["kind"] == "drunk"
                and now - result.game["shuffled"] >= self.rules.shuffle_interval):
            self.rng.shuffle(result.game["letters"])
            result.game["shuffled"] = now
        return result
