import logging

from .models import State
from .sessions import STORAGE_ERRORS


log = logging.getLogger(__name__)


class SaveLoadManager:
    def __init__(self, sessions):
        self.sessions = sessions

    async def save(self, uid, state):
        if uid in self.sessions.degraded:
            raise ValueError("Хранилище недоступно: сохранение отключено")
        scene = self.sessions.story.content.scenes[state.scene]
        if state.battle or state.game or scene.type == "ending":
            raise ValueError("Сохранение доступно только в обычной сцене")
        try:
            await self.sessions.store.save_checkpoint(uid, state)
        except STORAGE_ERRORS as error:
            self.sessions.degraded.add(uid)
            log.exception("Не удалось сохранить чекпоинт пользователя %s", uid)
            raise ValueError("Хранилище недоступно: сохранить не удалось") from error
        log.debug("Сохранен чекпоинт пользователя %s, сцена %s", uid, state.scene)

    async def load(self, uid, state):
        if uid in self.sessions.degraded:
            raise ValueError("Хранилище недоступно: загрузка отключена")
        if state.battle or state.game:
            raise ValueError("Загрузка недоступна в бою и мини-игре")
        try:
            checkpoint = await self.sessions.store.checkpoint(uid)
        except STORAGE_ERRORS as error:
            self.sessions.degraded.add(uid)
            log.exception("Не удалось загрузить чекпоинт пользователя %s", uid)
            raise ValueError("Хранилище недоступно: загрузить не удалось") from error
        if checkpoint is None:
            log.warning("У пользователя %s нет чекпоинта", uid)
            return self.sessions.story.new()
        loaded = State(scene=checkpoint[0], flags=checkpoint[1])
        log.debug("Загружен чекпоинт пользователя %s, сцена %s", uid, loaded.scene)
        self.sessions.story.arrive(loaded)
        return loaded
