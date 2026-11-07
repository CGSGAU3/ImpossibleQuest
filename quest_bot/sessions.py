import asyncio
import logging
from collections import defaultdict
from secrets import token_hex

from sqlalchemy.exc import SQLAlchemyError


STORAGE_ERRORS = (SQLAlchemyError, OSError)
log = logging.getLogger(__name__)
SESSION_METADATA = {"revision", "token", "restart_pending"}


class SessionManager:
    def __init__(self, store, story):
        self.store = store
        self.story = story
        self.states = {}
        self.endings = {}
        self.locks = defaultdict(asyncio.Lock)
        self.degraded = set()
        self.unconfirmed = {}

    async def get(self, uid):
        if uid not in self.states:
            try:
                state, endings = await self.store.read(uid)
            except STORAGE_ERRORS:
                log.error("Не удалось прочитать сессию, игра продолжается в памяти", exc_info=True)
                state, endings = self.story.new(), set()
                self.unconfirmed[uid] = state.model_dump(exclude=SESSION_METADATA)
                self.degraded.add(uid)
            self.states[uid] = state if state is not None else self.story.new()
            self.endings[uid] = endings
        return self.states[uid]

    async def put(self, uid, state):
        if uid in self.unconfirmed:
            previous = self.states[uid]
            # Подтвержденный перезапуск создает новый State без метаданных.
            restarted = previous.restart_pending and state.revision == 0 and not state.token
            changed = state.model_dump(exclude=SESSION_METADATA) != self.unconfirmed[uid]
            if restarted or changed:
                del self.unconfirmed[uid]

        try:
            if uid in self.degraded:
                await self.store.init()
                durable_state, durable_endings = await self.store.read(uid)
                self.endings[uid].update(durable_endings)
                if uid in self.unconfirmed and durable_state is not None:
                    durable_state.restart_pending = state.restart_pending
                    state = durable_state
                self.unconfirmed.pop(uid, None)
        except STORAGE_ERRORS:
            log.error("Не удалось восстановить доступ к сессии", exc_info=True)
            self._accept(uid, state)
            return state

        self._accept(uid, state)
        try:
            await self.store.write(uid, state, self.endings[uid])
            self.degraded.discard(uid)
        except STORAGE_ERRORS:
            log.error("Не удалось записать сессию, игра продолжается в памяти", exc_info=True)
            self.degraded.add(uid)
        return state

    def _accept(self, uid, state):
        state.revision += 1
        state.token = token_hex(8)
        self.states[uid] = state
        scene = self.story.content.scenes[state.scene]
        if not state.game and scene.type == "ending":
            if scene.ending_id not in self.endings[uid]:
                log.info("Открыта концовка %s", scene.ending_id)
            self.endings[uid].add(scene.ending_id)
