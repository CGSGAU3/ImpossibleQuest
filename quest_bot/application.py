from dataclasses import dataclass, field
import logging

from . import drunk
from .checkpoints import SaveLoadManager
from .endings import report


log = logging.getLogger(__name__)
HELP = "/start: начать или продолжить\n/help: справка\n/restart: начать заново с подтверждением\n/endings: прогресс\n/save: сохранить чекпоинт\n/load: загрузить чекпоинт"


WARNING = "Хранилище недоступно. Прогресс временно хранится в памяти; /save и /load недоступны."


@dataclass
class View:
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)


class Application:
    def __init__(self, sessions):
        self.sessions = sessions
        self.story = sessions.story
        self.checkpoints = SaveLoadManager(sessions)

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

    async def command(self, uid, command):
        async with self.sessions.locks[uid]:
            if command == "/help":
                return View(HELP)
            if command not in {"/start", "/restart", "/save", "/load", "/endings"}:
                log.warning("Неизвестная команда пользователя %s", uid)
                return View("Неизвестная команда")
            state = await self.sessions.get(uid)
            if command == "/endings":
                return View(report(self.sessions.endings[uid], self.story.content))
            if command == "/save":
                try:
                    await self.checkpoints.save(uid, state)
                except ValueError as error:
                    return View(str(error))
                return View("Чекпоинт сохранен")
            if command == "/restart":
                state = state.model_copy(deep=True)
                state.restart_pending = True
                state = await self.sessions.put(uid, state)
                return View("Начать заново? Открытые концовки сохранятся.", [
                    ("Да", f"{state.token}:restart:yes"),
                    ("Нет", f"{state.token}:restart:no"),
                ])
            if command == "/load":
                try:
                    state = await self.checkpoints.load(uid, state)
                except ValueError as error:
                    return View(str(error))
            state = self.story.tick(state)
            state.restart_pending = False
            state = await self.sessions.put(uid, state)
            return self.render(uid, state)
