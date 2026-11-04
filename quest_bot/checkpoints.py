from .models import State
from .sessions import STORAGE_ERRORS


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
            raise ValueError("Хранилище недоступно: сохранить не удалось") from error

    async def load(self, uid, state):
        if uid in self.sessions.degraded:
            raise ValueError("Хранилище недоступно: загрузка отключена")
        if state.battle or state.game:
            raise ValueError("Загрузка недоступна в бою и мини-игре")
        try:
            checkpoint = await self.sessions.store.checkpoint(uid)
        except STORAGE_ERRORS as error:
            self.sessions.degraded.add(uid)
            raise ValueError("Хранилище недоступно: загрузить не удалось") from error
        loaded = (State(scene=checkpoint[0], flags=checkpoint[1])
                  if checkpoint else self.sessions.story.new())
        self.sessions.story.arrive(loaded)
        return loaded
