import asyncio
import logging
from collections import defaultdict
from secrets import token_hex

from sqlalchemy.exc import SQLAlchemyError


STORAGE_ERRORS = (SQLAlchemyError, OSError)
log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, store, story):
        self.store = store
        self.story = story
        self.states = {}
        self.endings = {}
        self.locks = defaultdict(asyncio.Lock)
        self.degraded = set()

    async def get(self, uid):
        if uid not in self.states:
            try:
                state, endings = await self.store.read(uid)
            except STORAGE_ERRORS:
                log.error("Не удалось прочитать сессию, игра продолжается в памяти", exc_info=True)
                state, endings = None, set()
                self.degraded.add(uid)
            self.states[uid] = state if state is not None else self.story.new()
            self.endings[uid] = endings
        return self.states[uid]

    async def put(self, uid, state):
        state.revision += 1
        state.token = token_hex(8)
        self.states[uid] = state
        scene = self.story.content.scenes[state.scene]
        if not state.game and scene.type == "ending":
            if scene.ending_id not in self.endings[uid]:
                log.info("Открыта концовка %s", scene.ending_id)
            self.endings[uid].add(scene.ending_id)
        try:
            if uid in self.degraded:
                await self.store.init()
                _, durable_endings = await self.store.read(uid)
                self.endings[uid].update(durable_endings)
            await self.store.write(uid, state, self.endings[uid])
            self.degraded.discard(uid)
        except STORAGE_ERRORS:
            log.error("Не удалось записать сессию, игра продолжается в памяти", exc_info=True)
            self.degraded.add(uid)
        return state
