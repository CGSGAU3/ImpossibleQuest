from . import flags
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
        self._scene(state.scene)
        state.pre_drunk = None

    def choices(self, state):
        scene = self._scene(state.scene)
        return [
            (index, choice)
            for index, choice in enumerate(scene.choices)
            if flags.matches(state.flags, choice.flags_required)
        ]

    def choose(self, state, index):
        result = state.model_copy(deep=True)
        if result.game:
            raise ValueError("Сейчас доступны только действия мини-игры")
        available = dict(self.choices(result))
        if type(index) is not int or index not in available:
            raise ValueError("Этот вариант выбора недоступен")
        choice = available[index]
        if choice.note not in (None, "conditional", "random_choice"):
            raise ValueError("Для этого выбора нужен модуль специального режима")
        flags.apply(result.flags, choice.flags)
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
