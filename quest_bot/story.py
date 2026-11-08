from . import battle, flags, minigames
from .models import Quest, State


SECRET = "2213112312113312231"
WAIT_SCENE = 45
WAIT_ENDING = 46
WAIT_SECONDS = 5 * 60
WAIT_PROMPT = '"Вейт фор файв миннетс!", - крикнул он и убежал.'


def _next_history(history, index):
    return (history + str(index + 1))[-len(SECRET):]


def _conditional_destination(choice, current_flags):
    return next(
        (condition.next for condition in choice.conditions
         if flags.matches(current_flags, condition.flags_required)),
        None,
    )


class StoryEngine:
    def __init__(self, content: Quest, rng, clock, rules):
        self.content = content
        self.rng = rng
        self.clock = clock
        self.rules = rules
        has_lost = any(choice.room == "lost" for scene in content.scenes.values()
                       for choice in scene.choices)
        if has_lost:
            for sid in (rules.lost_win, rules.lost_win_safe, rules.lost_lose):
                self._scene(sid)

    def _scene(self, sid):
        if sid not in self.content.scenes:
            raise ValueError(f"Сцена {sid} не найдена")
        return self.content.scenes[sid]

    def _is_wait_scene(self, state, scene):
        if state.scene != WAIT_SCENE or state.battle or state.game:
            return False
        ending = self.content.scenes.get(WAIT_ENDING)
        return (
            scene.type == "scene" and scene.text == WAIT_PROMPT
            and ending is not None and ending.type == "ending" and ending.ending_id == 12
        )

    def new(self):
        state = State(scene=self.content.start)
        self.arrive(state)
        return state

    def arrive(self, state):
        scene = self._scene(state.scene)
        state.scene_deadline = None
        if self._is_wait_scene(state, scene):
            state.scene_deadline = self.clock() + WAIT_SECONDS
        if not state.battle and any(choice.room == "drunk" for choice in scene.choices):
            state.pre_drunk = {
                "visible": [index for index, choice in enumerate(scene.choices)
                            if flags.matches(state.flags, choice.flags_required)]
            }
        else:
            state.pre_drunk = None

    def choices(self, state):
        scene = self._scene(state.scene)
        if state.game:
            return []
        available = []
        for index, choice in enumerate(scene.choices):
            if not flags.matches(state.flags, choice.flags_required):
                continue
            if state.pre_drunk and index not in state.pre_drunk["visible"]:
                continue
            if not state.battle and choice.note == "conditional":
                next_flags = {**state.flags, **choice.flags}
                secret = _next_history(state.history, index) == SECRET
                if not secret and _conditional_destination(choice, next_flags) is None:
                    continue
            available.append((index, choice))
        return available

    def choose(self, state, index):
        result = self.tick(state)
        if state.game:
            if result.game is None:
                return result
            raise ValueError("Сейчас доступны только действия мини-игры")
        if result.scene != state.scene:
            return result
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
        flags.apply(result.flags, choice.flags)
        if choice.note == "battle":
            result.battle = battle.enter(choice)
            result.scene = choice.start_scene
            self.arrive(result)
            return result
        if choice.note == "minigame":
            result.game = minigames.enter(choice, self.clock(), self.rng, self.rules)
            result.pre_drunk = None
            result.scene_deadline = None
            return result
        result.history = _next_history(result.history, index)
        if result.history == SECRET:
            destination = self.content.secret_ending
        elif choice.note == "conditional":
            destination = _conditional_destination(choice, result.flags)
        elif choice.note == "random_choice":
            destination = self.rng.choice(choice.options)
        else:
            destination = choice.next
        self._scene(destination)
        result.scene = destination
        self.arrive(result)
        return result

    def play(self, state, value):
        result = self.tick(state)
        if state.game and result.game is None:
            return result
        if not result.game:
            raise ValueError("Мини-игра неактивна")
        destination = minigames.step(
            result.game, value, self.clock(), self.rules, result.flags,
        )
        if destination is not None:
            self._scene(destination)
            result.game = None
            result.scene = destination
            self.arrive(result)
        return result

    def tick(self, state):
        scene = self._scene(state.scene)
        result = state.model_copy(deep=True)
        now = self.clock()
        if self._is_wait_scene(result, scene):
            if result.scene_deadline is None:
                # Сессии, записанные до добавления таймера, не содержат срока.
                result.scene_deadline = now + WAIT_SECONDS
            elif now >= result.scene_deadline:
                result.scene = WAIT_ENDING
                self.arrive(result)
        elif result.game and result.game["kind"] == "lost" and now >= result.game["deadline"]:
            result.game = None
            result.scene = self.rules.lost_lose
            self.arrive(result)
        elif (result.game and result.game["kind"] == "drunk"
                and now - result.game["shuffled"] >= self.rules.shuffle_interval):
            self.rng.shuffle(result.game["letters"])
            result.game["shuffled"] = now
        return result
