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

    def _storage_notice(self, uid, text):
        if uid in self.sessions.degraded:
            return WARNING + "\n\n" + text
        return text

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
        return View(self._storage_notice(uid, text), buttons)

    async def command(self, uid, command):
        async with self.sessions.locks[uid]:
            if command == "/help":
                return View(HELP)
            if command not in {"/start", "/restart", "/save", "/load", "/endings"}:
                log.warning("Неизвестная команда пользователя %s", uid)
                return View("Неизвестная команда")
            state = await self.sessions.get(uid)
            if command == "/endings":
                text = report(self.sessions.endings[uid], self.story.content)
                return View(self._storage_notice(uid, text))
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
                text = self._storage_notice(uid, "Начать заново? Открытые концовки сохранятся.")
                return View(text, [
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

    async def callback(self, uid, payload):
        async with self.sessions.locks[uid]:
            state = await self.sessions.get(uid)
            parts = payload.split(":")
            if len(parts) != 3 or not state.token or parts[0] != state.token:
                log.warning("Устаревшая кнопка пользователя %s", uid)
                raise ValueError("Эта кнопка устарела. Нажми /start")
            _, kind, value = parts
            updated = self.story.tick(state)
            if (updated.scene != state.scene or bool(updated.game) != bool(state.game)
                    or updated.pre_drunk != state.pre_drunk):
                updated.restart_pending = False
                updated = await self.sessions.put(uid, updated)
                return self.render(uid, updated)
            if kind == "restart" and state.restart_pending:
                if value not in {"yes", "no"}:
                    raise ValueError("Неверное подтверждение")
                updated = self.story.new() if value == "yes" else state.model_copy(deep=True)
                updated.restart_pending = False
            elif state.restart_pending:
                raise ValueError("Подтверди или отмени перезапуск")
            elif kind == "choice":
                updated = self.story.choose(updated, int(value))
            elif kind == "game":
                updated = self.story.play(updated, value)
            else:
                raise ValueError("Неверная кнопка")
            updated = await self.sessions.put(uid, updated)
            return self.render(uid, updated)

    async def tick(self, uid):
        async with self.sessions.locks[uid]:
            state = await self.sessions.get(uid)
            if not state.game:
                return None
            updated = self.story.tick(state)
            if updated == state and state.game["kind"] != "lost":
                return None
            if updated.scene != state.scene or bool(updated.game) != bool(state.game):
                updated.restart_pending = False
            elif state.restart_pending:
                return None
            updated = await self.sessions.put(uid, updated)
            return self.render(uid, updated)
