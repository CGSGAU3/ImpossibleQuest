import asyncio
from collections import defaultdict
from secrets import token_hex

from sqlalchemy.exc import SQLAlchemyError


STORAGE_ERRORS = (SQLAlchemyError, OSError)


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
            state, endings = await self.store.read(uid)
            self.states[uid] = state if state is not None else self.story.new()
            self.endings[uid] = endings
        return self.states[uid]

    async def put(self, uid, state):
        state.revision += 1
        state.token = token_hex(8)
        self.states[uid] = state
        scene = self.story.content.scenes[state.scene]
        if not state.game and scene.type == "ending":
            self.endings[uid].add(scene.ending_id)
        await self.store.write(uid, state, self.endings[uid])
        return state
