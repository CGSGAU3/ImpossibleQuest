from dataclasses import dataclass, field

from . import drunk


WARNING = "Хранилище недоступно. Прогресс временно хранится в памяти; /save и /load недоступны."


@dataclass
class View:
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)


class Application:
    def __init__(self, sessions):
        self.sessions = sessions
        self.story = sessions.story

    def render(self, uid, state):
        def button(label, kind, value):
            return label, f"{state.token}:{kind}:{value}"

        if state.game and state.game["kind"] == "drunk":
            game = state.game
            text = (
                f"Пьяное Поле Чудес. Раунд {game['round'] + 1}/3\n"
                f"{drunk.ROUNDS[game['round']][1]}\nСобрано: {game['word']}"
            )
            buttons = [button(letter, "game", letter) for letter in game["letters"]]
        elif state.game:
            game = state.game
            left = max(0, int(game["deadline"] - self.story.clock()))
            text = (
                f"Введите код. Осталось: {left} сек.\n"
                f"Введено: {' '.join(map(str, game['entered']))}"
            )
            buttons = [button(str(number), "game", number) for number in game["buttons"]]
        else:
            scene = self.story.content.scenes[state.scene]
            text = scene.text
            if state.battle:
                hp = state.battle["hp"] if state.scene == state.battle["miss"] else state.battle["ehp"]
                text = text.replace("{}", str(hp))
            buttons = [
                button(drunk.PRE_LABELS[index] if state.pre_drunk else choice.text, "choice", index)
                for index, choice in self.story.choices(state)
            ]
        if uid in self.sessions.degraded:
            text = WARNING + "\n\n" + text
        return View(text, buttons)
